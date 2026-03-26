from __future__ import annotations

import argparse
import json
import logging
import io
from collections import Counter
from pathlib import Path

import torch
from PIL import Image
from sklearn.metrics import f1_score
from torch import nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import transforms

from ai_models.image.cnn_pipeline import build_backbone, resolve_device

logger = logging.getLogger(__name__)

IMAGE_SIZE = 224
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


class JpegCompression:
    def __init__(self, quality: int = 92) -> None:
        self.quality = quality

    def __call__(self, img: Image.Image) -> Image.Image:
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=self.quality)
        out.seek(0)
        return Image.open(out).convert("RGB")


class ForgeryTypeDataset(Dataset):
    def __init__(self, split_dir: Path, class_names: list[str], augment: bool) -> None:
        self.class_names = class_names
        self.class_to_idx = {c: i for i, c in enumerate(class_names)}
        self.samples: list[tuple[Path, int]] = []

        for cls in class_names:
            cls_dir = split_dir / cls
            if not cls_dir.exists():
                continue
            for p in sorted(cls_dir.rglob("*")):
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXT:
                    self.samples.append((p, self.class_to_idx[cls]))

        if not self.samples:
            raise FileNotFoundError(f"No images found in {split_dir} for classes: {class_names}")

        if augment:
            self.transform = transforms.Compose(
                [
                    JpegCompression(quality=92),
                    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
                    transforms.RandomResizedCrop(IMAGE_SIZE, scale=(0.85, 1.0), ratio=(0.9, 1.1)),
                    transforms.RandomHorizontalFlip(0.5),
                    transforms.RandomRotation(7),
                    transforms.ColorJitter(brightness=0.08, contrast=0.08, saturation=0.06, hue=0.02),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                    transforms.RandomErasing(p=0.25, scale=(0.02, 0.1), ratio=(0.3, 3.3), value="random"),
                ]
            )
        else:
            self.transform = transforms.Compose(
                [
                    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ]
            )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        path, label = self.samples[idx]
        image = Image.open(path).convert("RGB")
        return self.transform(image), label


def discover_nonempty_classes(root: Path) -> list[str]:
    train = root / "train"
    if not train.exists():
        raise FileNotFoundError(f"Missing train dir: {train}")

    classes = []
    for d in sorted(train.iterdir()):
        if not d.is_dir():
            continue
        has_files = any(p.is_file() and p.suffix.lower() in SUPPORTED_EXT for p in d.rglob("*"))
        if has_files:
            classes.append(d.name)

    if len(classes) < 2:
        raise ValueError("Need at least 2 non-empty classes for subtype training.")

    return classes


def run_epoch(model, loader, criterion, device, optimizer=None, phase: str = "train", epoch: int = 0, total_epochs: int = 0):
    is_train = optimizer is not None
    model.train(is_train)

    total_loss = 0.0
    total_correct = 0
    total = 0
    y_true: list[int] = []
    y_pred: list[int] = []
    total_batches = len(loader)
    dataset_size = len(loader.dataset)
    use_amp = torch.cuda.is_available()
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    logger.info(
        "[forgery_type][%s] epoch %d/%d starting: %d images, %d batches",
        phase,
        epoch,
        total_epochs,
        dataset_size,
        total_batches,
    )

    for batch_idx, (x, y) in enumerate(loader, start=1):
        x = x.to(device)
        y = y.to(device)

        if is_train:
            optimizer.zero_grad(set_to_none=True)

        with torch.amp.autocast("cuda", enabled=use_amp):
            logits = model(x)
            loss = criterion(logits, y)

        if is_train:
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

        pred = torch.argmax(logits, dim=1)
        total_correct += int((pred == y).sum().item())
        total_loss += float(loss.item()) * y.size(0)
        total += int(y.size(0))
        y_true.extend(y.detach().cpu().tolist())
        y_pred.extend(pred.detach().cpu().tolist())

        pct = (100.0 * total / max(dataset_size, 1))
        logger.info(
            "[forgery_type][%s] epoch %d/%d batch %d/%d images %d/%d (%.1f%%)",
            phase,
            epoch,
            total_epochs,
            batch_idx,
            total_batches,
            total,
            dataset_size,
            pct,
        )

    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0) if y_true else 0.0
    return total_loss / max(total, 1), total_correct / max(total, 1), float(macro_f1)


def train_forgery_type_model(
    data_root: Path,
    checkpoint_path: Path,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    backbone: str,
    num_workers: int,
    pretrained: bool,
    resume_from_checkpoint: bool,
) -> dict:
    classes = discover_nonempty_classes(data_root)

    train_ds = ForgeryTypeDataset(data_root / "train", classes, augment=True)
    test_ds = ForgeryTypeDataset(data_root / "test", classes, augment=False)

    train_labels = [label for _, label in train_ds.samples]
    class_counts = Counter(train_labels)
    sample_weights = [1.0 / class_counts[label] for label in train_labels]
    sampler = WeightedRandomSampler(sample_weights, num_samples=len(sample_weights), replacement=True)

    train_loader = DataLoader(train_ds, batch_size=batch_size, sampler=sampler, num_workers=num_workers)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    device = resolve_device()
    model = build_backbone(backbone, num_classes=len(classes), pretrained=pretrained).to(device)

    class_weight_tensor = torch.tensor(
        [1.0 / class_counts.get(i, 1) for i in range(len(classes))], dtype=torch.float32, device=device
    )
    class_weight_tensor = class_weight_tensor / class_weight_tensor.sum() * len(classes)

    criterion = nn.CrossEntropyLoss(weight=class_weight_tensor, label_smoothing=0.05)
    optimizer = AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=2)

    start_epoch = 1
    best_acc = -1.0
    best_f1 = -1.0
    stale_epochs = 0
    early_stop_patience = 6
    history: list[dict] = []

    if resume_from_checkpoint and checkpoint_path.exists():
        ckpt = torch.load(checkpoint_path, map_location=device)
        old_classes = ckpt.get("class_names", [])
        if old_classes != classes:
            raise ValueError(f"Class mismatch. checkpoint={old_classes}, current={classes}")
        model.load_state_dict(ckpt["model_state_dict"])
        if "optimizer_state_dict" in ckpt:
            optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        if "scheduler_state_dict" in ckpt:
            scheduler.load_state_dict(ckpt["scheduler_state_dict"])
        start_epoch = int(ckpt.get("epoch", 0)) + 1
        best_acc = float(ckpt.get("best_val_acc", -1.0))
        best_f1 = float(ckpt.get("best_val_f1", -1.0))
        history = ckpt.get("history", [])
        logger.info("[forgery_type] Resuming from epoch %d", start_epoch)
    elif resume_from_checkpoint:
        logger.info("[forgery_type] No checkpoint found, starting from epoch 1")

    if start_epoch > epochs:
        return {
            "checkpoint": str(checkpoint_path),
            "classes": classes,
            "best_val_acc": round(best_acc, 6),
            "epochs": epochs,
            "resumed": resume_from_checkpoint,
            "start_epoch": start_epoch,
            "message": "No training run because checkpoint epoch already reached requested --epochs.",
        }

    for epoch in range(start_epoch, epochs + 1):
        logger.info("[forgery_type] Progress: epoch %d/%d", epoch, epochs)
        tr_loss, tr_acc, tr_f1 = run_epoch(
            model,
            train_loader,
            criterion,
            device,
            optimizer,
            phase="train",
            epoch=epoch,
            total_epochs=epochs,
        )
        va_loss, va_acc, va_f1 = run_epoch(
            model,
            test_loader,
            criterion,
            device,
            phase="val",
            epoch=epoch,
            total_epochs=epochs,
        )
        scheduler.step(va_f1)

        row = {
            "epoch": epoch,
            "train_loss": round(tr_loss, 6),
            "train_acc": round(tr_acc, 6),
            "train_f1_macro": round(tr_f1, 6),
            "val_loss": round(va_loss, 6),
            "val_acc": round(va_acc, 6),
            "val_f1_macro": round(va_f1, 6),
        }
        history.append(row)

        logger.info(
            "[forgery_type] epoch %d/%d train_loss=%.4f train_acc=%.4f train_f1=%.4f val_loss=%.4f val_acc=%.4f val_f1=%.4f",
            epoch,
            epochs,
            tr_loss,
            tr_acc,
            tr_f1,
            va_loss,
            va_acc,
            va_f1,
        )

        improved = va_f1 > best_f1
        if improved:
            best_acc = va_acc
            best_f1 = va_f1
            stale_epochs = 0
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "scheduler_state_dict": scheduler.state_dict(),
                    "epoch": epoch,
                    "backbone": backbone,
                    "class_names": classes,
                    "best_val_acc": float(best_acc),
                    "best_val_f1": float(best_f1),
                    "history": history,
                },
                checkpoint_path,
            )
        else:
            stale_epochs += 1
            logger.info("[forgery_type] No val_f1 improvement for %d epoch(s)", stale_epochs)

        if stale_epochs >= early_stop_patience:
            logger.info("[forgery_type] Early stopping triggered at epoch %d", epoch)
            break

    return {
        "checkpoint": str(checkpoint_path),
        "classes": classes,
        "best_val_acc": round(best_acc, 6),
        "best_val_f1": round(best_f1, 6),
        "epochs": epochs,
        "resumed": resume_from_checkpoint,
        "start_epoch": start_epoch,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train forgery subtype classifier")
    parser.add_argument("--data-root", default="ai_models/data_forgery_type")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--backbone", choices=["resnet18", "efficientnet_b0"], default="resnet18")
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--checkpoint", default="ai_models/models/forgery_type_cnn.pt")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    result = train_forgery_type_model(
        data_root=Path(args.data_root),
        checkpoint_path=Path(args.checkpoint),
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        backbone=args.backbone,
        num_workers=args.num_workers,
        pretrained=True,
        resume_from_checkpoint=Path(args.checkpoint).exists(),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import torch
from PIL import Image
from torch import nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

from ai_models.image.cnn_pipeline import build_backbone, resolve_device

logger = logging.getLogger(__name__)

IMAGE_SIZE = 224
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


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
                    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
                    transforms.RandomHorizontalFlip(0.5),
                    transforms.RandomRotation(6),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
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


def run_epoch(model, loader, criterion, device, optimizer=None):
    is_train = optimizer is not None
    model.train(is_train)

    total_loss = 0.0
    total_correct = 0
    total = 0

    for x, y in loader:
        x = x.to(device)
        y = y.to(device)

        if is_train:
            optimizer.zero_grad(set_to_none=True)

        logits = model(x)
        loss = criterion(logits, y)

        if is_train:
            loss.backward()
            optimizer.step()

        pred = torch.argmax(logits, dim=1)
        total_correct += int((pred == y).sum().item())
        total_loss += float(loss.item()) * y.size(0)
        total += int(y.size(0))

    return total_loss / max(total, 1), total_correct / max(total, 1)


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

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    device = resolve_device()
    model = build_backbone(backbone, num_classes=len(classes), pretrained=pretrained).to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer, T_max=max(epochs, 1))

    start_epoch = 1
    best_acc = -1.0
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
        history = ckpt.get("history", [])
        logger.info("[forgery_type] Resuming from epoch %d", start_epoch)

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
        tr_loss, tr_acc = run_epoch(model, train_loader, criterion, device, optimizer)
        va_loss, va_acc = run_epoch(model, test_loader, criterion, device)
        scheduler.step()

        row = {
            "epoch": epoch,
            "train_loss": round(tr_loss, 6),
            "train_acc": round(tr_acc, 6),
            "val_loss": round(va_loss, 6),
            "val_acc": round(va_acc, 6),
        }
        history.append(row)

        logger.info(
            "[forgery_type] epoch %d/%d train_loss=%.4f train_acc=%.4f val_loss=%.4f val_acc=%.4f",
            epoch,
            epochs,
            tr_loss,
            tr_acc,
            va_loss,
            va_acc,
        )

        if va_acc > best_acc:
            best_acc = va_acc
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
                    "history": history,
                },
                checkpoint_path,
            )

    return {
        "checkpoint": str(checkpoint_path),
        "classes": classes,
        "best_val_acc": round(best_acc, 6),
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
    parser.add_argument("--pretrained", action="store_true")
    parser.add_argument("--resume", action="store_true")
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
        pretrained=args.pretrained,
        resume_from_checkpoint=args.resume,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

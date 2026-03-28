from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image
from sklearn.metrics import f1_score
from torch import nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms
from torchvision.models import ResNet50_Weights

from ai_models.image.cnn_pipeline import resolve_device

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
                    transforms.RandomResizedCrop(IMAGE_SIZE, scale=(0.9, 1.0), ratio=(0.95, 1.05)),
                    transforms.RandomHorizontalFlip(0.5),
                    transforms.RandomRotation(3),
                    transforms.ColorJitter(brightness=0.04, contrast=0.04, saturation=0.03, hue=0.01),
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


class FixedSRMConv(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.conv = nn.Conv2d(3, 3, kernel_size=5, stride=1, padding=2, groups=3, bias=False)

        # 5x5 SRM-like high-pass kernel to emphasize manipulation residuals.
        base = torch.tensor(
            [
                [0.0, 0.0, -1.0, 0.0, 0.0],
                [0.0, 2.0, -4.0, 2.0, 0.0],
                [-1.0, -4.0, 12.0, -4.0, -1.0],
                [0.0, 2.0, -4.0, 2.0, 0.0],
                [0.0, 0.0, -1.0, 0.0, 0.0],
            ],
            dtype=torch.float32,
        ) / 12.0
        kernel = torch.zeros((3, 1, 5, 5), dtype=torch.float32)
        kernel[0, 0] = base
        kernel[1, 0] = base
        kernel[2, 0] = base

        with torch.no_grad():
            self.conv.weight.copy_(kernel)

        for p in self.conv.parameters():
            p.requires_grad = False

        self.trunc = nn.Hardtanh(min_val=-3.0, max_val=3.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.trunc(self.conv(x))


class DualStreamResNet50SRM(nn.Module):
    def __init__(self, num_classes: int, pretrained: bool = True) -> None:
        super().__init__()
        weights = ResNet50_Weights.IMAGENET1K_V2 if pretrained else None

        self.srm = FixedSRMConv()

        self.rgb_backbone = models.resnet50(weights=weights)
        self.rgb_backbone.fc = nn.Identity()

        self.srm_backbone = models.resnet50(weights=weights)
        self.srm_backbone.fc = nn.Identity()

        self.classifier = nn.Sequential(
            nn.Linear(4096, 1024),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(1024, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        rgb_feat = self.rgb_backbone(x)
        srm_feat = self.srm_backbone(self.srm(x))
        fused = torch.cat([rgb_feat, srm_feat], dim=1)
        return self.classifier(fused)


class WeightedFocalLoss(nn.Module):
    def __init__(self, alpha: torch.Tensor, gamma: float = 2.0) -> None:
        super().__init__()
        self.register_buffer("alpha", alpha)
        self.gamma = gamma

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        log_probs = F.log_softmax(logits, dim=1)
        probs = torch.exp(log_probs)

        targets = targets.long()
        log_pt = log_probs.gather(1, targets.unsqueeze(1)).squeeze(1)
        pt = probs.gather(1, targets.unsqueeze(1)).squeeze(1)
        alpha_t = self.alpha.gather(0, targets)

        loss = -alpha_t * ((1.0 - pt).clamp(min=1e-8) ** self.gamma) * log_pt
        return loss.mean()


def build_class_weights(class_names: list[str], device: torch.device) -> torch.Tensor:
    desired = {
        "authentic": 1.0,
        "copy_move": 3.0,
        "splicing": 3.0,
    }
    weights = [float(desired.get(name, 1.0)) for name in class_names]
    return torch.tensor(weights, dtype=torch.float32, device=device)


def run_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    optimizer: AdamW | None = None,
    phase: str = "train",
    epoch: int = 0,
    total_epochs: int = 0,
) -> tuple[float, float, float]:
    is_train = optimizer is not None
    model.train(is_train)

    total_loss = 0.0
    total_correct = 0
    total = 0
    y_true: list[int] = []
    y_pred: list[int] = []

    total_batches = len(loader)
    dataset_size = len(loader.dataset)
    use_amp = device.type == "cuda"
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
        x = x.to(device, non_blocking=True)
        y = y.to(device, non_blocking=True)

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

        pct = 100.0 * total / max(dataset_size, 1)
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

    device = resolve_device()
    use_cuda = device.type == "cuda"
    effective_workers = max(4, int(num_workers))

    def _build_loaders(worker_count: int) -> tuple[DataLoader, DataLoader]:
        loader_kwargs = {
            "batch_size": batch_size,
            "num_workers": worker_count,
            "pin_memory": use_cuda,
            "persistent_workers": worker_count > 0,
        }
        if worker_count > 0:
            loader_kwargs["prefetch_factor"] = 2

        return (
            DataLoader(train_ds, shuffle=True, **loader_kwargs),
            DataLoader(test_ds, shuffle=False, **loader_kwargs),
        )

    train_loader, test_loader = _build_loaders(effective_workers)

    model = DualStreamResNet50SRM(num_classes=len(classes), pretrained=pretrained).to(device)

    alpha = build_class_weights(classes, device=device)
    criterion = WeightedFocalLoss(alpha=alpha, gamma=2.0)
    optimizer = AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=2)

    start_epoch = 1
    best_acc = -1.0
    best_f1 = -1.0
    stale_epochs = 0
    early_stop_patience = 6
    history: list[dict] = []
    expected_backbone = "dual_stream_resnet50_srm"

    def _archive_incompatible_checkpoint(path: Path, reason: str) -> None:
        candidate = path.with_suffix(path.suffix + ".legacy")
        i = 1
        while candidate.exists():
            candidate = path.with_suffix(path.suffix + f".legacy.{i}")
            i += 1
        shutil.move(str(path), str(candidate))
        logger.warning("[forgery_type] Archived incompatible checkpoint to %s (%s)", candidate, reason)

    if resume_from_checkpoint and checkpoint_path.exists():
        ckpt = torch.load(checkpoint_path, map_location=device)
        ckpt_backbone = str(ckpt.get("backbone", ""))
        if ckpt_backbone != expected_backbone:
            _archive_incompatible_checkpoint(
                checkpoint_path,
                f"backbone mismatch: checkpoint={ckpt_backbone or 'unknown'}, expected={expected_backbone}",
            )
            ckpt = None

        if ckpt is not None:
            old_classes = ckpt.get("class_names", [])
            if old_classes != classes:
                raise ValueError(f"Class mismatch. checkpoint={old_classes}, current={classes}")

            try:
                model.load_state_dict(ckpt["model_state_dict"])
            except RuntimeError as exc:
                _archive_incompatible_checkpoint(checkpoint_path, f"state_dict mismatch: {exc}")
                ckpt = None

        if ckpt is not None:
            if "optimizer_state_dict" in ckpt:
                optimizer.load_state_dict(ckpt["optimizer_state_dict"])
            if "scheduler_state_dict" in ckpt:
                scheduler.load_state_dict(ckpt["scheduler_state_dict"])
            start_epoch = int(ckpt.get("epoch", 0)) + 1
            best_acc = float(ckpt.get("best_val_acc", -1.0))
            best_f1 = float(ckpt.get("best_val_f1", -1.0))
            history = ckpt.get("history", [])
            logger.info("[forgery_type] Resuming from epoch %d", start_epoch)
        else:
            logger.info("[forgery_type] Starting fresh at epoch 1 with dual-stream model")
    elif resume_from_checkpoint:
        logger.info("[forgery_type] No checkpoint found, starting from epoch 1")

    if start_epoch > epochs:
        return {
            "checkpoint": str(checkpoint_path),
            "classes": classes,
            "best_val_acc": round(best_acc, 6),
            "best_val_f1": round(best_f1, 6),
            "epochs": epochs,
            "resumed": resume_from_checkpoint,
            "start_epoch": start_epoch,
            "message": "No training run because checkpoint epoch already reached requested --epochs.",
        }

    worker_fallback_used = False

    for epoch in range(start_epoch, epochs + 1):
        logger.info("[forgery_type] Progress: epoch %d/%d", epoch, epochs)
        try:
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
        except Exception as exc:
            if effective_workers > 0 and not worker_fallback_used:
                logger.warning(
                    "[forgery_type] DataLoader worker pipeline failed (%s). Falling back to num_workers=0.",
                    exc,
                )
                effective_workers = 0
                worker_fallback_used = True
                train_loader, test_loader = _build_loaders(effective_workers)
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
            else:
                raise
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
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        if improved:
            best_acc = va_acc
            best_f1 = va_f1
            stale_epochs = 0
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "scheduler_state_dict": scheduler.state_dict(),
                    "epoch": epoch,
                    "backbone": "dual_stream_resnet50_srm",
                    "class_names": classes,
                    "best_val_acc": float(best_acc),
                    "best_val_f1": float(best_f1),
                    "history": history,
                },
                checkpoint_path,
            )
            logger.info("[forgery_type] Saved improved checkpoint at epoch %d", epoch)
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
    parser.add_argument("--backbone", choices=["dual_resnet50_srm"], default="dual_resnet50_srm")
    parser.add_argument("--num-workers", type=int, default=4)
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

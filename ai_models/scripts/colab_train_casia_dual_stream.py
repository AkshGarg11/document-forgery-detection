"""
Colab end-to-end trainer for CASIA2.0 revised.

What this script does:
1) Extracts /content/casia2.0_revised.zip (or .tar/.tar.gz) into /content/casia_extracted.
2) Finds CASIA root containing Au/ and Tp/.
3) Builds split dataset at /content/data_forgery_type with classes:
   - authentic
   - copy_move (Tp_S_*)
   - splicing  (Tp_D_*)
4) Trains Dual-Stream ResNet50 (RGB + fixed SRM residual stream) for 8 epochs.
5) Saves best model checkpoint.
6) Evaluates on test split and writes metrics.
7) Generates plots: loss/acc/f1 curves + confusion matrix.

Run in Colab:
!python /content/colab_train_casia_dual_stream.py
(or paste into a Colab cell and run)
"""

from __future__ import annotations

import json
import os
import random
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import torch
import torch.nn.functional as F
from PIL import Image
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from torch import nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms
from torchvision.models import ResNet50_Weights


# =============================
# Config
# =============================
ARCHIVE_PATH = Path("/content/casia2.0_revised.zip")
EXTRACT_DIR = Path("/content/casia_extracted")
DATA_ROOT = Path("/content/data_forgery_type")
OUTPUT_DIR = Path("/content/model_outputs")
CHECKPOINT_PATH = OUTPUT_DIR / "forgery_type_dual_stream_resnet50_srm.pt"
METRICS_JSON = OUTPUT_DIR / "test_metrics.json"
HISTORY_PNG = OUTPUT_DIR / "train_val_curves.png"
CM_PNG = OUTPUT_DIR / "confusion_matrix.png"

EPOCHS = 8
BATCH_SIZE = 16
LR = 1e-4
NUM_WORKERS = 4
TEST_SIZE = 0.2
SEED = 42

SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


# =============================
# Utilities
# =============================
def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def extract_archive(archive_path: Path, extract_dir: Path) -> None:
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    extract_dir.mkdir(parents=True, exist_ok=True)

    if archive_path.suffix.lower() == ".aip":
        # Many custom extensions are zip payloads. Try as zip first.
        tmp_zip = archive_path.with_suffix(".zip")
        shutil.copy2(archive_path, tmp_zip)
        try:
            shutil.unpack_archive(str(tmp_zip), str(extract_dir), format="zip")
            print(f"Extracted {archive_path} as zip into {extract_dir}")
            return
        except Exception as exc:
            print(f"Zip extraction attempt failed for .aip: {exc}")
        finally:
            if tmp_zip.exists():
                tmp_zip.unlink(missing_ok=True)

    try:
        shutil.unpack_archive(str(archive_path), str(extract_dir))
        print(f"Extracted {archive_path} into {extract_dir}")
    except Exception as exc:
        raise RuntimeError(
            f"Could not unpack archive {archive_path}. "
            "If this is not a zip/tar archive, convert it to .zip and retry. "
            f"Original error: {exc}"
        )


def find_casia_root(search_root: Path) -> Path:
    if (search_root / "Au").exists() and (search_root / "Tp").exists():
        return search_root

    for p in search_root.rglob("*"):
        if p.is_dir() and (p / "Au").exists() and (p / "Tp").exists():
            return p

    raise FileNotFoundError(
        f"Could not find CASIA root with Au/ and Tp/ under {search_root}"
    )


def list_images(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted([p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXT])


def infer_tamper_type(filename: str) -> str:
    name = filename.lower()
    if name.startswith("tp_s_"):
        return "copy_move"
    if name.startswith("tp_d_"):
        return "splicing"
    # Fallback for unknown naming
    return "splicing"


def rebuild_split_dataset(casia_root: Path, out_root: Path, test_size: float, seed: int) -> dict:
    au_dir = casia_root / "Au"
    tp_dir = casia_root / "Tp"

    au_files = list_images(au_dir)
    tp_files = list_images(tp_dir)

    if not au_files or not tp_files:
        raise ValueError("Au/Tp folders are empty or not found.")

    print(f"Authentic images found: {len(au_files)}")
    print(f"Tampered images found: {len(tp_files)}")

    # Build a global stratified split by binary label (authentic vs tampered)
    all_paths = au_files + tp_files
    all_labels = [0] * len(au_files) + [1] * len(tp_files)

    idx = np.arange(len(all_paths))
    idx_train, idx_test = train_test_split(
        idx,
        test_size=test_size,
        random_state=seed,
        stratify=all_labels,
    )

    split_map = {"train": idx_train, "test": idx_test}
    classes = ["authentic", "copy_move", "splicing"]

    if out_root.exists():
        shutil.rmtree(out_root)

    for split in ("train", "test"):
        for cls in classes:
            (out_root / split / cls).mkdir(parents=True, exist_ok=True)

    counts = {
        "train": {"authentic": 0, "copy_move": 0, "splicing": 0},
        "test": {"authentic": 0, "copy_move": 0, "splicing": 0},
    }

    for split, split_idx in split_map.items():
        for i in split_idx:
            src = all_paths[int(i)]
            if int(i) < len(au_files):
                dst_cls = "authentic"
            else:
                dst_cls = infer_tamper_type(src.name)

            dst = out_root / split / dst_cls / src.name
            if dst.exists():
                dst = out_root / split / dst_cls / f"dup__{src.name}"

            shutil.copy2(src, dst)
            counts[split][dst_cls] += 1

    return counts


# =============================
# Dataset
# =============================
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
            raise FileNotFoundError(f"No samples found in {split_dir}")

        if augment:
            # Forensic-safe augmentation: preserve high-frequency traces.
            self.transform = transforms.Compose(
                [
                    transforms.RandomResizedCrop(224, scale=(0.9, 1.0), ratio=(0.95, 1.05)),
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
                    transforms.Resize((224, 224)),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ]
            )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        path, label = self.samples[idx]
        img = Image.open(path).convert("RGB")
        return self.transform(img), label


# =============================
# Model
# =============================
class FixedSRMConv(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.conv = nn.Conv2d(3, 3, kernel_size=5, stride=1, padding=2, groups=3, bias=False)

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
    def __init__(self, num_classes: int) -> None:
        super().__init__()
        weights = ResNet50_Weights.IMAGENET1K_V2

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


@dataclass
class EpochStats:
    loss: float
    acc: float
    f1_macro: float


def run_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: AdamW | None,
    device: torch.device,
    epoch: int,
    total_epochs: int,
    phase: str,
) -> EpochStats:
    is_train = optimizer is not None
    model.train(is_train)

    total = 0
    total_correct = 0
    total_loss = 0.0
    y_true: list[int] = []
    y_pred: list[int] = []

    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    n_batches = len(loader)
    print(f"[{phase}] epoch {epoch}/{total_epochs} start: {len(loader.dataset)} images, {n_batches} batches")

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
        total += y.size(0)
        total_correct += (pred == y).sum().item()
        total_loss += float(loss.item()) * y.size(0)

        y_true.extend(y.detach().cpu().tolist())
        y_pred.extend(pred.detach().cpu().tolist())

        if batch_idx == 1 or batch_idx % 25 == 0 or batch_idx == n_batches:
            pct = 100.0 * total / max(len(loader.dataset), 1)
            print(f"[{phase}] epoch {epoch}/{total_epochs} batch {batch_idx}/{n_batches} images {total}/{len(loader.dataset)} ({pct:.1f}%)")

    acc = total_correct / max(total, 1)
    loss = total_loss / max(total, 1)
    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    return EpochStats(loss=loss, acc=acc, f1_macro=macro_f1)


def plot_history(history: list[dict], out_path: Path) -> None:
    epochs = [h["epoch"] for h in history]
    train_loss = [h["train_loss"] for h in history]
    val_loss = [h["val_loss"] for h in history]
    train_acc = [h["train_acc"] for h in history]
    val_acc = [h["val_acc"] for h in history]
    train_f1 = [h["train_f1_macro"] for h in history]
    val_f1 = [h["val_f1_macro"] for h in history]

    plt.figure(figsize=(16, 4))

    plt.subplot(1, 3, 1)
    plt.plot(epochs, train_loss, label="train")
    plt.plot(epochs, val_loss, label="val")
    plt.title("Loss")
    plt.xlabel("Epoch")
    plt.legend()

    plt.subplot(1, 3, 2)
    plt.plot(epochs, train_acc, label="train")
    plt.plot(epochs, val_acc, label="val")
    plt.title("Accuracy")
    plt.xlabel("Epoch")
    plt.legend()

    plt.subplot(1, 3, 3)
    plt.plot(epochs, train_f1, label="train")
    plt.plot(epochs, val_f1, label="val")
    plt.title("Macro F1")
    plt.xlabel("Epoch")
    plt.legend()

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=160)
    plt.close()


def evaluate_on_test(model: nn.Module, loader: DataLoader, class_names: list[str], device: torch.device) -> dict:
    model.eval()

    y_true: list[int] = []
    y_pred: list[int] = []

    with torch.no_grad():
        n_batches = len(loader)
        total = 0
        for bi, (x, y) in enumerate(loader, start=1):
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)

            logits = model(x)
            pred = torch.argmax(logits, dim=1)

            y_true.extend(y.detach().cpu().tolist())
            y_pred.extend(pred.detach().cpu().tolist())
            total += y.size(0)

            if bi == 1 or bi % 25 == 0 or bi == n_batches:
                print(f"[test] batch {bi}/{n_batches} checked {total}/{len(loader.dataset)}")

    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(class_names))))

    plt.figure(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=class_names, yticklabels=class_names)
    plt.title("Confusion Matrix (Test)")
    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.tight_layout()
    CM_PNG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(CM_PNG, dpi=160)
    plt.close()

    report = classification_report(y_true, y_pred, target_names=class_names, output_dict=True, zero_division=0)

    metrics = {
        "samples": len(y_true),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "confusion_matrix": cm.tolist(),
        "classification_report": report,
        "class_names": class_names,
        "confusion_matrix_png": str(CM_PNG),
    }
    return metrics


def main() -> None:
    set_seed(SEED)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # 1) Extract archive
    print("\n=== Step 1: Extract archive ===")
    extract_archive(ARCHIVE_PATH, EXTRACT_DIR)

    # 2) Locate CASIA root
    print("\n=== Step 2: Locate CASIA root ===")
    casia_root = find_casia_root(EXTRACT_DIR)
    print(f"CASIA root: {casia_root}")

    # 3) Build train/test split folders
    print("\n=== Step 3: Build train/test dataset ===")
    split_counts = rebuild_split_dataset(casia_root, DATA_ROOT, TEST_SIZE, SEED)
    print(json.dumps(split_counts, indent=2))

    # 4) Prepare datasets/loaders
    print("\n=== Step 4: Build dataloaders ===")
    class_names = ["authentic", "copy_move", "splicing"]

    train_ds = ForgeryTypeDataset(DATA_ROOT / "train", class_names, augment=True)
    test_ds = ForgeryTypeDataset(DATA_ROOT / "test", class_names, augment=False)

    use_cuda = device.type == "cuda"
    train_loader = DataLoader(
        train_ds,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=NUM_WORKERS,
        pin_memory=use_cuda,
        persistent_workers=NUM_WORKERS > 0,
        prefetch_factor=2 if NUM_WORKERS > 0 else None,
    )
    test_loader = DataLoader(
        test_ds,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=use_cuda,
        persistent_workers=NUM_WORKERS > 0,
        prefetch_factor=2 if NUM_WORKERS > 0 else None,
    )

    # 5) Model/loss/optim
    print("\n=== Step 5: Init model ===")
    model = DualStreamResNet50SRM(num_classes=len(class_names)).to(device)

    # Requested class weights: [1.0, 3.0, 3.0] for [Authentic, Copy-Move, Splicing]
    alpha = torch.tensor([1.0, 3.0, 3.0], dtype=torch.float32, device=device)
    criterion = WeightedFocalLoss(alpha=alpha, gamma=2.0)
    optimizer = AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=2)

    # 6) Train
    print("\n=== Step 6: Train ===")
    best_f1 = -1.0
    best_acc = -1.0
    history: list[dict] = []

    for epoch in range(1, EPOCHS + 1):
        tr = run_epoch(model, train_loader, criterion, optimizer, device, epoch, EPOCHS, "train")
        va = run_epoch(model, test_loader, criterion, None, device, epoch, EPOCHS, "val")

        scheduler.step(va.f1_macro)

        row = {
            "epoch": epoch,
            "train_loss": float(tr.loss),
            "train_acc": float(tr.acc),
            "train_f1_macro": float(tr.f1_macro),
            "val_loss": float(va.loss),
            "val_acc": float(va.acc),
            "val_f1_macro": float(va.f1_macro),
        }
        history.append(row)

        print(
            f"[epoch {epoch}/{EPOCHS}] "
            f"train_loss={tr.loss:.4f} train_acc={tr.acc:.4f} train_f1={tr.f1_macro:.4f} "
            f"val_loss={va.loss:.4f} val_acc={va.acc:.4f} val_f1={va.f1_macro:.4f}"
        )

        if va.f1_macro > best_f1:
            best_f1 = va.f1_macro
            best_acc = va.acc
            CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "scheduler_state_dict": scheduler.state_dict(),
                    "epoch": epoch,
                    "backbone": "dual_stream_resnet50_srm",
                    "class_names": class_names,
                    "best_val_acc": float(best_acc),
                    "best_val_f1": float(best_f1),
                    "history": history,
                },
                CHECKPOINT_PATH,
            )
            print(f"Saved best checkpoint at epoch {epoch} -> {CHECKPOINT_PATH}")

    # 7) Curves
    print("\n=== Step 7: Save train/val curves ===")
    plot_history(history, HISTORY_PNG)
    print(f"Saved training curves: {HISTORY_PNG}")

    # 8) Load best + evaluate on test
    print("\n=== Step 8: Evaluate best model on test ===")
    ckpt = torch.load(CHECKPOINT_PATH, map_location=device)
    model.load_state_dict(ckpt["model_state_dict"])

    metrics = evaluate_on_test(model, test_loader, class_names, device)
    metrics["checkpoint"] = str(CHECKPOINT_PATH)
    metrics["history_png"] = str(HISTORY_PNG)
    metrics["split_counts"] = split_counts

    METRICS_JSON.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print(f"Saved metrics json: {METRICS_JSON}")


if __name__ == "__main__":
    main()

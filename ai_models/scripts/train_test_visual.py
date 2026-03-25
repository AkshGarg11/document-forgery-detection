from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import torch
from torch import nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader

try:
    from ai_models.image.cnn_pipeline import (
        BinaryForgeryDataset,
        build_backbone,
        preprocess_copy_move_image,
        preprocess_ela_image,
        resolve_device,
    )
except ImportError:
    from image.cnn_pipeline import (
        BinaryForgeryDataset,
        build_backbone,
        preprocess_copy_move_image,
        preprocess_ela_image,
        resolve_device,
    )

logger = logging.getLogger(__name__)


def _run_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    optimizer: AdamW | None,
) -> tuple[float, float]:
    is_train = optimizer is not None
    model.train(is_train)

    total_loss = 0.0
    total_correct = 0
    total_samples = 0

    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)

        if is_train:
            optimizer.zero_grad(set_to_none=True)

        logits = model(images)
        loss = criterion(logits, labels)

        if is_train:
            loss.backward()
            optimizer.step()

        preds = torch.argmax(logits, dim=1)
        total_correct += int((preds == labels).sum().item())
        total_loss += float(loss.item()) * labels.size(0)
        total_samples += int(labels.size(0))

    avg_loss = total_loss / max(total_samples, 1)
    avg_acc = total_correct / max(total_samples, 1)
    return avg_loss, avg_acc


def train_model(
    model_key: str,
    data_root: Path,
    checkpoint_path: Path,
    preprocessor,
    backbone: str,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    num_workers: int,
    pretrained: bool,
    resume_from_checkpoint: bool = False,
) -> dict:
    train_dir = data_root / "train"
    test_dir = data_root / "test"

    train_dataset = BinaryForgeryDataset(
        split_dir=train_dir,
        preprocessor=preprocessor,
        augment=True,
    )
    test_dataset = BinaryForgeryDataset(
        split_dir=test_dir,
        preprocessor=preprocessor,
        augment=False,
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )

    device = resolve_device()
    model = build_backbone(backbone=backbone, pretrained=pretrained)
    model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer, T_max=max(epochs, 1))

    best_acc = -1.0
    history: list[dict] = []
    start_epoch = 1

    if resume_from_checkpoint and checkpoint_path.exists():
        checkpoint = torch.load(checkpoint_path, map_location=device)
        checkpoint_backbone = checkpoint.get("backbone", backbone)
        if checkpoint_backbone != backbone:
            raise ValueError(
                f"Checkpoint backbone '{checkpoint_backbone}' does not match requested backbone '{backbone}'."
            )

        model.load_state_dict(checkpoint["model_state_dict"])

        if "optimizer_state_dict" in checkpoint:
            optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        if "scheduler_state_dict" in checkpoint:
            scheduler.load_state_dict(checkpoint["scheduler_state_dict"])

        best_acc = float(checkpoint.get("best_val_acc", -1.0))
        history = checkpoint.get("history", [])
        start_epoch = int(checkpoint.get("epoch", 0)) + 1
        logger.info(
            "[%s] Resuming from %s at epoch %d (best_val_acc=%.4f)",
            model_key,
            checkpoint_path,
            start_epoch,
            best_acc,
        )

    if start_epoch > epochs:
        logger.warning(
            "[%s] Requested epochs=%d is not greater than checkpoint epoch=%d. Nothing to train.",
            model_key,
            epochs,
            start_epoch - 1,
        )
        return {
            "model": model_key,
            "checkpoint": str(checkpoint_path),
            "best_val_acc": round(best_acc, 6),
            "epochs": epochs,
            "history": history,
            "resumed": resume_from_checkpoint,
            "start_epoch": start_epoch,
            "message": "No training run because checkpoint epoch already reached requested --epochs.",
        }

    for epoch in range(start_epoch, epochs + 1):
        train_loss, train_acc = _run_epoch(model, train_loader, criterion, device, optimizer)
        val_loss, val_acc = _run_epoch(model, test_loader, criterion, device, optimizer=None)
        scheduler.step()

        metrics = {
            "epoch": epoch,
            "train_loss": round(train_loss, 6),
            "train_acc": round(train_acc, 6),
            "val_loss": round(val_loss, 6),
            "val_acc": round(val_acc, 6),
        }
        history.append(metrics)

        logger.info(
            "[%s] Epoch %d/%d | train_loss=%.4f train_acc=%.4f | val_loss=%.4f val_acc=%.4f",
            model_key,
            epoch,
            epochs,
            train_loss,
            train_acc,
            val_loss,
            val_acc,
        )

        if val_acc > best_acc:
            best_acc = val_acc
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "scheduler_state_dict": scheduler.state_dict(),
                    "backbone": backbone,
                    "label_to_index": {"authentic": 0, "forged": 1},
                    "best_val_acc": float(best_acc),
                    "model_key": model_key,
                    "epoch": epoch,
                    "history": history,
                },
                checkpoint_path,
            )

    return {
        "model": model_key,
        "checkpoint": str(checkpoint_path),
        "best_val_acc": round(best_acc, 6),
        "epochs": epochs,
        "history": history,
        "resumed": resume_from_checkpoint,
        "start_epoch": start_epoch,
    }


def test_model(
    model_key: str,
    data_root: Path,
    checkpoint_path: Path,
    preprocessor,
    batch_size: int,
    num_workers: int,
) -> dict:
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint not found for {model_key}: {checkpoint_path}")

    try:
        from ai_models.image.cnn_pipeline import load_checkpoint_model
    except ImportError:
        from image.cnn_pipeline import load_checkpoint_model

    device = resolve_device()
    model, _checkpoint = load_checkpoint_model(checkpoint_path, device)

    test_dir = data_root / "test"
    dataset = BinaryForgeryDataset(
        split_dir=test_dir,
        preprocessor=preprocessor,
        augment=False,
    )
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )

    criterion = nn.CrossEntropyLoss()
    loss, acc = _run_epoch(model, loader, criterion, device, optimizer=None)

    logger.info("[%s] Test loss=%.4f | Test accuracy=%.4f", model_key, loss, acc)
    return {
        "model": model_key,
        "checkpoint": str(checkpoint_path),
        "test_loss": round(loss, 6),
        "test_acc": round(acc, 6),
    }


def _model_config(model_key: str, root: Path) -> tuple[Path, callable]:
    if model_key == "ela":
        return root / "models" / "ela_cnn.pt", preprocess_ela_image
    if model_key == "copy_move":
        return root / "models" / "copy_move_cnn.pt", preprocess_copy_move_image
    raise ValueError(f"Unsupported model_key: {model_key}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train/test CNN visual forgery models")
    parser.add_argument("--model", choices=["ela", "copy_move", "both"], default="both")
    parser.add_argument("--data-root", default=None, help="Path to ai_models/data")
    parser.add_argument("--train", action="store_true", help="Run training")
    parser.add_argument("--test", action="store_true", help="Run test evaluation")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--backbone", choices=["resnet18", "efficientnet_b0"], default="resnet18")
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--pretrained", action="store_true", help="Use ImageNet weights")
    parser.add_argument("--resume", action="store_true", help="Resume training from existing checkpoint")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    root = Path(__file__).resolve().parents[1]
    data_root = Path(args.data_root) if args.data_root else (root / "data")

    run_train = args.train or (not args.train and not args.test)
    run_test = args.test or (not args.train and not args.test)

    selected_models = ["ela", "copy_move"] if args.model == "both" else [args.model]

    summary: dict[str, dict] = {}
    for model_key in selected_models:
        checkpoint_path, preprocessor = _model_config(model_key, root)

        if run_train:
            summary[f"{model_key}_train"] = train_model(
                model_key=model_key,
                data_root=data_root,
                checkpoint_path=checkpoint_path,
                preprocessor=preprocessor,
                backbone=args.backbone,
                epochs=args.epochs,
                batch_size=args.batch_size,
                learning_rate=args.lr,
                num_workers=args.num_workers,
                pretrained=args.pretrained,
                resume_from_checkpoint=args.resume,
            )

        if run_test:
            summary[f"{model_key}_test"] = test_model(
                model_key=model_key,
                data_root=data_root,
                checkpoint_path=checkpoint_path,
                preprocessor=preprocessor,
                batch_size=args.batch_size,
                num_workers=args.num_workers,
            )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

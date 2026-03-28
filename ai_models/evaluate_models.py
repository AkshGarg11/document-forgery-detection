from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from ai_models.image.copy_move import run_copy_move_detection
from ai_models.image.ela import run_ela_analysis
from ai_models.image.forgery_type import CHECKPOINT_PATH as TYPE_CHECKPOINT_PATH
from ai_models.image.forgery_type import predict_forgery_type

SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
logger = logging.getLogger(__name__)


def _iter_images(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXT:
            yield p


def _count_split_classes(type_root: Path) -> dict[str, dict[str, int]]:
    class_names = ["authentic", "copy_move", "splicing"]
    out: dict[str, dict[str, int]] = {}
    for split in ("train", "test"):
        split_root = type_root / split
        split_counts = {c: 0 for c in class_names}
        if split_root.exists():
            for c in class_names:
                cls_dir = split_root / c
                split_counts[c] = sum(1 for _ in _iter_images(cls_dir)) if cls_dir.exists() else 0
        out[split] = split_counts
    return out


def evaluate_three_class_cascade(type_root: Path, threshold: float = 0.5) -> dict:
    test_root = type_root / "test"
    if not test_root.exists():
        raise FileNotFoundError(f"Missing test dir: {test_root}")

    class_names = ["authentic", "copy_move", "splicing"]
    allowed_forgery = {"copy_move", "splicing"}

    all_items: list[tuple[Path, str]] = []
    for cls_dir in sorted(test_root.iterdir()):
        if not cls_dir.is_dir():
            continue
        if cls_dir.name not in class_names:
            continue
        for p in _iter_images(cls_dir):
            all_items.append((p, cls_dir.name))

    total_images = len(all_items)
    if total_images == 0:
        raise ValueError("No test images found for 3-class evaluation.")

    logger.info("[eval][cascade] Starting 3-class cascade evaluation for %d images", total_images)

    y_true: list[str] = []
    y_pred: list[str] = []
    split_counts = Counter()

    for idx, (p, true_label) in enumerate(all_items, start=1):
        content = p.read_bytes()

        split_counts[true_label] += 1

        # Stage 1: binary gate authentic vs forged
        ela_p = float(run_ela_analysis(content))
        cm_p = float(run_copy_move_detection(content))
        fused = float(0.6 * ela_p + 0.4 * cm_p)

        pred_label = "authentic"
        if fused >= threshold:
            # Stage 2: subtype only for binary-predicted forged images
            subtype_pred, _ = predict_forgery_type(content)
            if subtype_pred in allowed_forgery:
                pred_label = subtype_pred
            else:
                pred_label = "splicing"

        y_true.append(true_label)
        y_pred.append(pred_label)

        if idx == 1 or idx % 25 == 0 or idx == total_images:
            logger.info("[eval][cascade] Checked %d/%d images", idx, total_images)

    cm = confusion_matrix(y_true, y_pred, labels=class_names)

    out_dir = Path("ai_models/models")
    out_dir.mkdir(parents=True, exist_ok=True)
    cm_png = out_dir / "confusion_matrix_cascade.png"

    split_counts = _count_split_classes(type_root)

    return {
        "samples": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "confusion_matrix": cm.tolist(),
        "classification_report": classification_report(
            y_true,
            y_pred,
            labels=class_names,
            zero_division=0,
            output_dict=True,
        ),
        "class_names": class_names,
        "confusion_matrix_png": str(cm_png),
        "checkpoint": str(TYPE_CHECKPOINT_PATH),
        "history_png": str(out_dir / "train_val_curves.png"),
        "threshold": float(threshold),
        "split_counts": split_counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate 3-class cascaded forgery performance")
    parser.add_argument("--data-root", default="ai_models/data_forgery_type", help="Subtype dataset root")
    parser.add_argument("--threshold", type=float, default=0.5, help="Binary decision threshold")
    parser.add_argument("--out", default=None, help="Optional output JSON path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    root = Path(args.data_root)

    result = evaluate_three_class_cascade(root, threshold=args.threshold)

    print(json.dumps(result, indent=2))

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

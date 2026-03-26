from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from ai_models.image.copy_move import run_copy_move_detection
from ai_models.image.ela import run_ela_analysis
from ai_models.image.forgery_type import predict_forgery_type

SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
logger = logging.getLogger(__name__)


def _iter_images(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXT:
            yield p


def evaluate_binary_from_type_root(type_root: Path, threshold: float = 0.5) -> dict:
    test_root = type_root / "test"
    if not test_root.exists():
        raise FileNotFoundError(f"Missing test dir: {test_root}")

    y_true: list[int] = []
    y_prob: list[float] = []

    all_items: list[tuple[Path, int]] = []
    for cls_dir in sorted(test_root.iterdir()):
        if not cls_dir.is_dir():
            continue
        label = 0 if cls_dir.name == "authentic" else 1
        for p in _iter_images(cls_dir):
            all_items.append((p, label))

    total_images = len(all_items)
    if total_images == 0:
        raise ValueError("No test images found for binary evaluation.")

    logger.info("[eval][binary] Starting evaluation for %d images", total_images)

    for idx, (p, label) in enumerate(all_items, start=1):
        content = p.read_bytes()
        ela_p = float(run_ela_analysis(content))
        cm_p = float(run_copy_move_detection(content))
        fused = float(0.6 * ela_p + 0.4 * cm_p)
        y_true.append(label)
        y_prob.append(fused)

        if idx == 1 or idx % 25 == 0 or idx == total_images:
            logger.info("[eval][binary] Checked %d/%d images", idx, total_images)

    y_true_arr = np.array(y_true)
    y_prob_arr = np.array(y_prob)
    y_pred_arr = (y_prob_arr >= threshold).astype(int)

    return {
        "samples": int(len(y_true_arr)),
        "threshold": float(threshold),
        "accuracy": float(accuracy_score(y_true_arr, y_pred_arr)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true_arr, y_pred_arr)),
        "precision_binary": float(precision_score(y_true_arr, y_pred_arr, zero_division=0)),
        "recall_binary": float(recall_score(y_true_arr, y_pred_arr, zero_division=0)),
        "f1_binary": float(f1_score(y_true_arr, y_pred_arr, zero_division=0)),
        "precision_macro": float(precision_score(y_true_arr, y_pred_arr, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true_arr, y_pred_arr, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true_arr, y_pred_arr, average="macro", zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true_arr, y_prob_arr)),
        "confusion_matrix": confusion_matrix(y_true_arr, y_pred_arr).tolist(),
        "classification_report": classification_report(
            y_true_arr,
            y_pred_arr,
            target_names=["authentic", "forged"],
            zero_division=0,
            output_dict=True,
        ),
    }


def evaluate_forgery_type(type_root: Path) -> dict:
    test_root = type_root / "test"
    if not test_root.exists():
        raise FileNotFoundError(f"Missing test dir: {test_root}")

    y_true: list[str] = []
    y_pred: list[str] = []

    all_items: list[tuple[Path, str]] = []
    for cls_dir in sorted(test_root.iterdir()):
        if not cls_dir.is_dir() or cls_dir.name == "authentic":
            continue
        cls_name = cls_dir.name
        for p in _iter_images(cls_dir):
            all_items.append((p, cls_name))

    total_images = len(all_items)
    if total_images == 0:
        return {
            "samples": 0,
            "message": "No subtype predictions available. Train forgery type model first.",
        }

    logger.info("[eval][type] Starting evaluation for %d forged images", total_images)

    for idx, (p, cls_name) in enumerate(all_items, start=1):
        pred, _ = predict_forgery_type(p.read_bytes())
        if pred is not None:
            y_true.append(cls_name)
            y_pred.append(pred)

        if idx == 1 or idx % 25 == 0 or idx == total_images:
            logger.info("[eval][type] Checked %d/%d images", idx, total_images)

    if not y_true:
        return {
            "samples": 0,
            "message": "No subtype predictions available. Train forgery type model first.",
        }

    labels = sorted(set(y_true) | set(y_pred))

    return {
        "samples": int(len(y_true)),
        "labels": labels,
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        "classification_report": classification_report(
            y_true,
            y_pred,
            labels=labels,
            zero_division=0,
            output_dict=True,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate binary + forgery-type performance")
    parser.add_argument("--data-root", default="ai_models/data_forgery_type", help="Subtype dataset root")
    parser.add_argument("--threshold", type=float, default=0.5, help="Binary decision threshold")
    parser.add_argument("--out", default=None, help="Optional output JSON path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    root = Path(args.data_root)

    binary_metrics = evaluate_binary_from_type_root(root, threshold=args.threshold)
    type_metrics = evaluate_forgery_type(root)

    result = {
        "binary_evaluation": binary_metrics,
        "forgery_type_evaluation": type_metrics,
        "summary": {
            "binary_accuracy": binary_metrics.get("accuracy"),
            "forgery_type_accuracy": type_metrics.get("accuracy"),
        },
    }

    print(json.dumps(result, indent=2))

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

"""CNN-based Copy-Move inference wrapper.

This module preserves the existing backend API:
- run_copy_move_detection(content: bytes) -> float

Train/test is handled by:
  python -m ai_models.scripts.train_test_visual --model copy_move --train --test
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

try:
    from .cnn_pipeline import predict_forgery_probability, preprocess_copy_move_image
except ImportError:
    from image.cnn_pipeline import predict_forgery_probability, preprocess_copy_move_image

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = _ROOT / "models" / "copy_move_cnn.pt"


def run_copy_move_detection(content: bytes) -> float:
    """Return forged-class probability using the trained Copy-Move CNN."""
    return predict_forgery_probability(
        content=content,
        checkpoint_path=MODEL_PATH,
        preprocessor=preprocess_copy_move_image,
        model_name="copy-move",
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="CNN Copy-Move forgery detector")
    parser.add_argument("--predict", metavar="IMAGE_PATH", required=True)
    args = parser.parse_args()

    with open(args.predict, "rb") as fh:
        data = fh.read()
    score = run_copy_move_detection(data)
    label = "Forged" if score > 0.6 else ("Suspicious" if score > 0.35 else "Authentic")
    print(f"Copy-Move score: {score:.4f} -> {label}")

"""CNN-based Error Level Analysis inference wrapper.

This module preserves the existing backend API:
- run_ela_analysis(content: bytes) -> float

Train/test is handled by:
  python -m ai_models.scripts.train_test_visual --model ela --train --test
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

try:
    from .cnn_pipeline import predict_forgery_probability, preprocess_ela_image
except ImportError:
    from image.cnn_pipeline import predict_forgery_probability, preprocess_ela_image

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = _ROOT / "models" / "ela_cnn.pt"


def run_ela_analysis(content: bytes) -> float:
    """Return forged-class probability using the trained ELA CNN."""
    return predict_forgery_probability(
        content=content,
        checkpoint_path=MODEL_PATH,
        preprocessor=preprocess_ela_image,
        model_name="ela",
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="CNN ELA forgery detector")
    parser.add_argument("--predict", metavar="IMAGE_PATH", required=True)
    args = parser.parse_args()

    with open(args.predict, "rb") as fh:
        data = fh.read()
    score = run_ela_analysis(data)
    label = "Forged" if score > 0.6 else ("Suspicious" if score > 0.35 else "Authentic")
    print(f"ELA score: {score:.4f} -> {label}")

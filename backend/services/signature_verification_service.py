from __future__ import annotations

import os
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.append(str(_REPO_ROOT))


_LAYOUT_MODEL = os.getenv("SIGN_LAYOUT_MODEL", str(_REPO_ROOT / "ai_models" / "models" / "layout.pt"))
_SIGN_MODEL = os.getenv("SIGN_VERIFY_MODEL", str(_REPO_ROOT / "ai_models" / "models" / "best_signature_model.pth"))

_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from ai_models.ai_detector.signature_verification import SignatureVerificationPipeline

        _pipeline = SignatureVerificationPipeline(
            layout_model_path=_LAYOUT_MODEL,
            signature_model_path=_SIGN_MODEL,
            threshold=float(os.getenv("SIGN_VERIFY_THRESHOLD", "0.5")),
        )
    return _pipeline


def predict_signature_verification(image_bytes: bytes) -> dict:
    return _get_pipeline().predict(image_bytes)

"""
services/ai_service.py
Orchestrates image & text AI modules and fuses their scores.
Replace placeholder calls with real model inference as needed.
"""

import sys
import os
import logging

# Allow importing from ai_models package (sibling directory)
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "ai_models"))

from image.ela import run_ela_analysis
from image.copy_move import run_copy_move_detection
from text.ocr import extract_text
from text.nlp_analysis import run_nlp_anomaly_detection
from fusion.confidence_score import compute_confidence

logger = logging.getLogger(__name__)


def analyze_document(content: bytes, content_type: str) -> dict:
    """
    Run full AI pipeline on document bytes.

    Returns:
        {
            "result": "Authentic" | "Suspicious" | "Forged",
            "confidence": float,
            "details": { ... }
        }
    """
    scores = {}

    if content_type.startswith("image/"):
        scores["ela"] = run_ela_analysis(content)
        scores["copy_move"] = run_copy_move_detection(content)
        logger.debug("Image scores: %s", scores)
    elif content_type == "application/pdf":
        extracted_text = extract_text(content)
        scores["nlp"] = run_nlp_anomaly_detection(extracted_text)
        logger.debug("Text scores: %s", scores)

    confidence, label = compute_confidence(scores)

    return {
        "result": label,
        "confidence": round(confidence, 4),
        "details": scores,
    }

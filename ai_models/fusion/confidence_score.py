"""
ai_models/fusion/confidence_score.py
Fuses individual module scores into a final classification verdict.

The weights below are tuned so that:
  - ELA is most reliable for image forgery
  - Copy-move catches region duplication
  - NLP catches text inconsistencies in PDFs
"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

# Configurable weights (must sum to 1.0 per relevant subset)
MODULE_WEIGHTS: dict[str, float] = {
    "ela":       0.45,
    "copy_move": 0.30,
    "nlp":       0.25,
}

THRESHOLD_FORGED     = 0.65
THRESHOLD_SUSPICIOUS = 0.38


def compute_confidence(scores: dict[str, float]) -> tuple[float, str]:
    """
    Weighted average fusion of module forgery probability scores.

    Args:
        scores: Dict mapping module name → forgery probability (0.0–1.0).
                Only modules present in the dict are included.

    Returns:
        (confidence: float, label: str)
        where label ∈ {"Authentic", "Suspicious", "Forged"}
    """
    if not scores:
        logger.warning("[FUSION] No module scores provided — defaulting to Authentic.")
        return 0.0, "Authentic"

    total_weight  = sum(MODULE_WEIGHTS.get(k, 1.0) for k in scores)
    weighted_sum  = sum(
        v * MODULE_WEIGHTS.get(k, 1.0)
        for k, v in scores.items()
        if v is not None
    )
    confidence = weighted_sum / total_weight if total_weight > 0 else 0.0

    if confidence >= THRESHOLD_FORGED:
        label = "Forged"
    elif confidence >= THRESHOLD_SUSPICIOUS:
        label = "Suspicious"
    else:
        label = "Authentic"

    logger.info("[FUSION] scores=%s  weighted_conf=%.4f  verdict=%s", scores, confidence, label)
    return round(confidence, 4), label

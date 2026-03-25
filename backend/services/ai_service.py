"""
services/ai_service.py
Orchestrates image & text AI modules and returns explainable verdict details.
"""

import os
import sys
import logging

# Allow importing from ai_models package (sibling directory)
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "ai_models"))

from image.ela import run_ela_analysis
from image.copy_move import run_copy_move_detection
from image.forgery_type import predict_forgery_type
from image.localization import localize_forgery_regions
from text.ocr import extract_text
from text.nlp_analysis import run_nlp_anomaly_detection
from fusion.confidence_score import compute_confidence

logger = logging.getLogger(__name__)


def _score_band(score: float) -> str:
    if score >= 0.65:
        return "high"
    if score >= 0.38:
        return "medium"
    return "low"


def _humanize_type(label: str | None) -> str | None:
    mapping = {
        "copy_move": "Copy-Move",
        "splicing": "Splicing",
        "removal": "Removal",
        "object_insertion": "Object Insertion",
        "ai_generated_text_based": "AI-Generated Text-Based Forgery",
        "authentic": "Authentic",
    }
    if label is None:
        return None
    return mapping.get(label, label.replace("_", " ").title())


def _build_explanation(content_type: str, scores: dict[str, float], label: str, confidence: float) -> dict:
    reasons: list[str] = []
    suspected_type: str | None = None

    ela = scores.get("ela")
    copy_move = scores.get("copy_move")
    nlp = scores.get("nlp")

    if content_type.startswith("image/"):
        if ela is not None:
            band = _score_band(ela)
            reasons.append(
                f"ELA signal is {band} ({ela:.2f}), indicating compression inconsistencies often seen in edited regions."
            )
        if copy_move is not None:
            band = _score_band(copy_move)
            reasons.append(
                f"Copy-move signal is {band} ({copy_move:.2f}), indicating possible duplicated/relocated regions in the image."
            )

        if (copy_move or 0.0) >= max((ela or 0.0), 0.5):
            suspected_type = "Copy-Move"
        elif (ela or 0.0) >= 0.5:
            suspected_type = "Splicing/Composite Edit"

    elif content_type == "application/pdf":
        if nlp is not None:
            band = _score_band(nlp)
            reasons.append(
                f"Text anomaly signal is {band} ({nlp:.2f}), indicating suspicious text patterns or inconsistent document semantics."
            )
        if (nlp or 0.0) >= 0.5:
            suspected_type = "Textual Forgery"

    if not reasons:
        reasons.append("No strong anomaly signal was detected from the available analysis modules.")

    summary = (
        f"This uploaded file is classified as {label} with confidence {confidence:.2f}. "
        f"Primary evidence comes from: {', '.join(sorted(scores.keys()))}."
    )

    return {
        "summary": summary,
        "reasons": reasons,
        "suspected_forgery_type": suspected_type,
    }


def analyze_document(content: bytes, content_type: str) -> dict:
    """Run full AI pipeline and return explainable verdict details."""
    scores: dict[str, float] = {}
    forgery_regions = None

    if content_type.startswith("image/"):
        scores["ela"] = run_ela_analysis(content)
        scores["copy_move"] = run_copy_move_detection(content)
        logger.debug("Image scores: %s", scores)
    elif content_type == "application/pdf":
        extracted_text = extract_text(content)
        scores["nlp"] = run_nlp_anomaly_detection(extracted_text)
        logger.debug("Text scores: %s", scores)

    confidence, label = compute_confidence(scores)
    explanation = _build_explanation(content_type, scores, label, confidence)

    subtype_label = None
    subtype_conf = None

    if content_type.startswith("image/") and label in {"Suspicious", "Forged"}:
        forgery_regions = localize_forgery_regions(content)
        subtype_label, subtype_conf = predict_forgery_type(content)

    if subtype_label and (subtype_conf or 0.0) >= 0.4:
        explanation["suspected_forgery_type"] = _humanize_type(subtype_label)
        explanation["reasons"].append(
            f"Subtype classifier suggests '{_humanize_type(subtype_label)}' with confidence {subtype_conf:.2f}."
        )

    return {
        "result": label,
        "confidence": round(confidence, 4),
        "module_scores": {k: round(float(v), 4) for k, v in scores.items()},
        "explanation": explanation["summary"],
        "reasons": explanation["reasons"],
        "suspected_forgery_type": explanation["suspected_forgery_type"],
        "forgery_regions": forgery_regions,
    }

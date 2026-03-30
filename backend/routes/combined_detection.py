"""Combined forgery detection route - runs signature verification and copy-move detection in parallel."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from services.blockchain_service import issue_document, verify_document
from services.doctamper_service import DocTamperService
from services.signature_verification_service import predict_signature_verification
from services.copy_move_service import CopyMoveForgeryDetectionService
from utils.hashing import compute_hash


router = APIRouter()


class SignatureBox(BaseModel):
    x: float
    y: float
    w: float
    h: float


class ForgeryRegion(BaseModel):
    label: str
    confidence: float


class CombinedDetectionResponse(BaseModel):
    """Response from combined signature + forgery detection models."""
    # Signature Verification Results
    signature_detected: bool
    signature_result: str
    signature_confidence: float
    signature_verdict: str
    signature_probabilities: dict[str, float]
    signature_box: Optional[SignatureBox]
    signature_preview: str

    # Copy-Move Forgery Detection Results
    forgery_type: str
    forgery_confidence: float
    is_forged: bool
    all_forgery_scores: dict[str, float]
    forgery_preview: str

    # DocTamper Forgery Localization Results
    doctamper_type: str
    doctamper_confidence: float
    doctamper_is_forged: bool
    doctamper_tampered_pixels_ratio: float
    doctamper_preview: str

    # Combined Analysis
    final_verdict: str
    risk_level: str  # low, medium, high
    reason: str

    # Blockchain & Hash
    hash: str
    tx_hash: Optional[str] = None
    anchor_status: Optional[str] = None
    anchor_error: Optional[str] = None
    chain_exists: Optional[bool] = None
    chain_revoked: Optional[bool] = None
    chain_timestamp: Optional[int] = None
    chain_issuer: Optional[str] = None

    # Metadata
    device: str
    weights: dict[str, str]


@router.post(
    "/combined-detection/predict",
    response_model=CombinedDetectionResponse,
    summary="Run signature verification + copy-move + DocTamper detection in parallel",
)
async def combined_detection_predict(
    image: UploadFile = File(...),
    blockchain_action: str = Form("find"),
):
    """
    Combined forgery detection endpoint that runs:
    1. Signature area detection & authenticity verification
    2. Copy-move & forgery type classification
    3. DocTamper localization (highlight tampered pixels)

    Both run in parallel for efficiency.
    """
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Only image uploads are supported.")

    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty image file.")

    action = blockchain_action.strip().lower()
    if action not in {"save", "find"}:
        raise HTTPException(status_code=422, detail="blockchain_action must be either 'save' or 'find'.")

    doc_hash = compute_hash(content)

    # Run all detection methods in parallel
    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=3) as executor:
            sig_future = loop.run_in_executor(
                executor, predict_signature_verification, content
            )
            copy_move_future = loop.run_in_executor(
                executor, CopyMoveForgeryDetectionService.predict_copy_move_forgery, content
            )
            doctamper_future = loop.run_in_executor(
                executor, DocTamperService.predict_doc_tamper, content
            )

            sig_result, copy_move_result, doctamper_result = await asyncio.gather(
                sig_future,
                copy_move_future,
                doctamper_future,
            )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Detection failed: {exc}") from exc

    # Process blockchain action
    tx_hash: str | None = None
    anchor_status: str | None = None
    anchor_error: str | None = None
    chain_exists: bool | None = None
    chain_revoked: bool | None = None
    chain_timestamp: int | None = None
    chain_issuer: str | None = None

    try:
        if action == "save":
            try:
                tx_hash = issue_document(doc_hash, doc_hash, version="combined-detection-v1")
                anchor_status = "anchored"
            except Exception as exc:
                anchor_status = "anchor_failed"
                anchor_error = str(exc)
        else:
            try:
                verification = verify_document(doc_hash)
                chain_exists = bool(verification.get("exists"))
                chain_revoked = bool(verification.get("revoked"))
                chain_timestamp = int(verification.get("timestamp") or 0)
                chain_issuer = verification.get("issuer")

                if chain_exists and not chain_revoked and verification.get("is_valid"):
                    anchor_status = "found_on_chain"
                elif chain_exists and chain_revoked:
                    anchor_status = "revoked_on_chain"
                else:
                    anchor_status = "not_found_on_chain"
            except Exception as exc:
                anchor_status = "lookup_failed"
                anchor_error = str(exc)
    except Exception as exc:
        anchor_error = str(exc)

    # Combine analysis
    sig_forged = sig_result.get("forensic_verdict") == "Forged" if sig_result.get("signature_detected") else None
    copy_move_forged = copy_move_result.get("is_forged")
    doctamper_forged = doctamper_result.get("is_forged")

    # Determine final verdict and risk level
    final_verdict = "AUTHENTIC"
    risk_level = "low"

    if sig_result.get("signature_detected") and sig_forged:
        final_verdict = "FORGED - Signature Tampering"
        risk_level = "high"
    elif doctamper_forged:
        final_verdict = "FORGED - Tampered Region Detected"
        risk_level = "high" if doctamper_result.get("confidence", 0) > 0.7 else "medium"
    elif copy_move_forged:
        forgery_type = copy_move_result.get("forgery_type", "unknown").replace("_", " ").title()
        final_verdict = f"FORGED - {forgery_type}"
        risk_level = "high" if copy_move_result.get("confidence", 0) > 0.7 else "medium"
    else:
        final_verdict = "AUTHENTIC"
        risk_level = "low"

    reason = (
        f"Signature: {sig_result.get('reason', 'N/A')} | "
        f"Copy-Move: {copy_move_result.get('forgery_type', 'N/A')} ({copy_move_result.get('confidence', 0):.1%}) | "
        f"DocTamper: {doctamper_result.get('forgery_type', 'N/A')} "
        f"({doctamper_result.get('confidence', 0):.1%}, "
        f"tampered area {doctamper_result.get('tampered_pixels_ratio', 0):.1%})"
    )

    # Extract signature box
    sig_box = None
    if sig_result.get("signature_detected") and sig_result.get("signature_box"):
        sb = sig_result["signature_box"]
        sig_box = SignatureBox(x=sb.get("x", 0), y=sb.get("y", 0), w=sb.get("w", 0), h=sb.get("h", 0))

    return CombinedDetectionResponse(
        # Signature verification
        signature_detected=sig_result.get("signature_detected", False),
        signature_result=sig_result.get("result", "Unknown"),
        signature_confidence=sig_result.get("confidence", 0.0),
        signature_verdict=sig_result.get("forensic_verdict", "Unknown"),
        signature_probabilities=sig_result.get("probabilities", {}),
        signature_box=sig_box,
        signature_preview=sig_result.get("annotated_preview", ""),
        # Copy-move detection
        forgery_type=copy_move_result.get("forgery_type", "unknown"),
        forgery_confidence=copy_move_result.get("confidence", 0.0),
        is_forged=copy_move_result.get("is_forged", False),
        all_forgery_scores=copy_move_result.get("all_scores", {}),
        forgery_preview=copy_move_result.get("annotated_preview", ""),
        # DocTamper localization
        doctamper_type=doctamper_result.get("forgery_type", "unknown"),
        doctamper_confidence=doctamper_result.get("confidence", 0.0),
        doctamper_is_forged=doctamper_result.get("is_forged", False),
        doctamper_tampered_pixels_ratio=doctamper_result.get("tampered_pixels_ratio", 0.0),
        doctamper_preview=doctamper_result.get("annotated_preview", ""),
        # Combined
        final_verdict=final_verdict,
        risk_level=risk_level,
        reason=reason,
        # Blockchain
        hash=doc_hash,
        tx_hash=tx_hash,
        anchor_status=anchor_status,
        anchor_error=anchor_error,
        chain_exists=chain_exists,
        chain_revoked=chain_revoked,
        chain_timestamp=chain_timestamp,
        chain_issuer=chain_issuer,
        # Metadata
        device=sig_result.get("device", "unknown"),
        weights=sig_result.get("weights", {}),
    )

"""
routes/upload.py
Handles document upload and orchestrates the full forgery-detection pipeline.
"""

import logging
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from pydantic import BaseModel

from services.ai_service import analyze_document
from services.blockchain_service import issue_document, verify_document, _similarity_score
from services.ipfs_service import upload_to_ipfs
from utils.hashing import compute_hash

logger = logging.getLogger(__name__)
router = APIRouter()


class ForgeryRegion(BaseModel):
    x: float
    y: float
    w: float
    h: float
    source: str | None = None
    score: float | None = None


class AnalysisResult(BaseModel):
    result: str
    confidence: float
    hash: str
    cid: str
    tx_hash: str | None = None
    anchor_status: str | None = None
    anchor_error: str | None = None
    chain_exists: bool | None = None
    chain_revoked: bool | None = None
    chain_timestamp: int | None = None
    chain_issuer: str | None = None
    forensic_verdict: str | None = None
    forensic_confidence: float | None = None
    perceptual_hash: str | None = None
    perceptual_match_score: float | None = None
    module_scores: dict[str, float] | None = None
    explanation: str | None = None
    reasons: list[str] | None = None
    suspected_forgery_type: str | None = None
    forgery_regions: list[ForgeryRegion] | None = None


@router.post("/upload", response_model=AnalysisResult, summary="Upload a document for forgery analysis")
async def upload_document(
    file: UploadFile = File(...),
    blockchain_action: str = Form("save"),
):
    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/tiff",
        "image/tif",
        "application/pdf",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{file.content_type}'. "
                "Allowed: JPEG, PNG, WEBP, TIFF, PDF."
            ),
        )

    try:
        content = await file.read()
    except Exception as exc:
        logger.error("Failed to read uploaded file: %s", exc)
        raise HTTPException(status_code=500, detail="Could not read uploaded file.") from exc

    doc_hash = compute_hash(content)
    logger.info("Document hash: %s", doc_hash)

    ai_result = analyze_document(content, file.content_type)
    logger.info("AI result: %s (confidence=%.2f)", ai_result["result"], ai_result["confidence"])

    action = blockchain_action.strip().lower()
    if action not in {"save", "find"}:
        raise HTTPException(status_code=422, detail="blockchain_action must be either 'save' or 'find'.")

    cid = upload_to_ipfs(content)
    logger.info("IPFS CID: %s", cid)

    tx_hash: str | None = None
    anchor_status = "not_anchored"
    anchor_error: str | None = None
    chain_exists: bool | None = None
    chain_revoked: bool | None = None
    chain_timestamp: int | None = None
    chain_issuer: str | None = None
    forensic_verdict: str | None = None
    forensic_confidence: float | None = None
    perceptual_hash: str | None = None
    perceptual_match_score: float | None = None

    def _mark_forged_due_to_chain(reason: str) -> None:
        ai_result["result"] = "Forged"
        ai_result["confidence"] = max(float(ai_result.get("confidence", 0.0)), 0.95)
        reasons = list(ai_result.get("reasons") or [])
        reasons.append(reason)
        ai_result["reasons"] = reasons

    if action == "save":
        try:
            perceptual_hash = ai_result.get("perceptual_hash")
            tx_hash = issue_document(
                doc_hash, 
                doc_hash, 
                version="1.0",
                perceptual_hash_hex=perceptual_hash
            )
            anchor_status = "anchored"
            forensic_verdict = "Proof of Existence Recorded"
            forensic_confidence = 1.0
            logger.info("Blockchain tx: %s (perceptual_hash: %s)", tx_hash, perceptual_hash or "none")
        except Exception as exc:
            anchor_status = "anchor_failed"
            anchor_error = str(exc)
            forensic_verdict = "Anchor Failed"
            forensic_confidence = 0.0
            logger.warning("Blockchain anchor failed: %s", exc)
    else:
        try:
            verification = verify_document(doc_hash)
            chain_exists = bool(verification.get("exists"))
            chain_revoked = bool(verification.get("revoked"))
            chain_timestamp = int(verification.get("timestamp") or 0)
            chain_issuer = verification.get("issuer")
            stored_phash = verification.get("perceptual_hash")
            perceptual_hash = ai_result.get("perceptual_hash")

            # Check if exact hash found on-chain
            if chain_exists and not chain_revoked and verification.get("is_valid"):
                anchor_status = "found_on_chain"
                forensic_verdict = "Authentic (Found on-chain)"
                forensic_confidence = 1.0
                perceptual_match_score = 100.0
            elif chain_exists and chain_revoked:
                anchor_status = "revoked_on_chain"
                forensic_verdict = "Revoked on-chain (Tampering Evidence)"
                forensic_confidence = 0.99
                _mark_forged_due_to_chain("Blockchain verification: document hash is revoked on-chain.")
            else:
                anchor_status = "not_found_on_chain"
                
                # Check perceptual hash similarity if both exist
                if stored_phash and perceptual_hash and stored_phash != "0" * 64:
                    perceptual_match_score = _similarity_score(perceptual_hash, stored_phash)
                else:
                    perceptual_match_score = None
                
                ai_conf = float(ai_result.get("confidence", 0.0))
                
                # If high perceptual similarity (>95%), flag as potential related forgery
                if perceptual_match_score and perceptual_match_score > 95:
                    forensic_verdict = f"Visually Similar to On-Chain Document ({perceptual_match_score:.1f}% match) - Possible Re-Forgery"
                    forensic_confidence = min(perceptual_match_score / 100.0, 0.95)
                    _mark_forged_due_to_chain("Perceptual hash: High visual similarity detected (>95%).")
                elif ai_conf > 0.7:
                    forensic_verdict = f"NOT on-chain + AI {ai_result['result']} ({int(ai_conf*100)}%) = Sophisticated Forgery"
                    forensic_confidence = min(ai_conf, 0.95)
                    _mark_forged_due_to_chain("Blockchain verification: document hash not found on-chain.")
                elif ai_conf > 0.4:
                    forensic_verdict = f"NOT on-chain + AI {ai_result['result']} ({int(ai_conf*100)}%) = Possible Forgery"
                    forensic_confidence = 0.75
                    _mark_forged_due_to_chain("Blockchain verification: document hash not found on-chain.")
                else:
                    forensic_verdict = "NOT on-chain + AI Low Confidence = Unverified/Unknown"
                    forensic_confidence = 0.5
        except Exception as exc:
            anchor_status = "lookup_failed"
            anchor_error = str(exc)
            forensic_verdict = "Lookup Failed"
            forensic_confidence = 0.0
            logger.warning("Blockchain lookup failed: %s", exc)

    return AnalysisResult(
        result=ai_result["result"],
        confidence=ai_result["confidence"],
        hash=doc_hash,
        cid=cid,
        tx_hash=tx_hash,
        anchor_status=anchor_status,
        anchor_error=anchor_error,
        chain_exists=chain_exists,
        chain_revoked=chain_revoked,
        chain_timestamp=chain_timestamp,
        chain_issuer=chain_issuer,
        forensic_verdict=forensic_verdict,
        forensic_confidence=forensic_confidence,
        perceptual_hash=perceptual_hash,
        perceptual_match_score=perceptual_match_score,
        module_scores=ai_result.get("module_scores"),
        explanation=ai_result.get("explanation"),
        reasons=ai_result.get("reasons"),
        suspected_forgery_type=ai_result.get("suspected_forgery_type"),
        forgery_regions=ai_result.get("forgery_regions"),
    )

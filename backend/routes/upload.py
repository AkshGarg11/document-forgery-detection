"""
routes/upload.py
Handles document upload and orchestrates the full forgery-detection pipeline.
"""

import logging
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from pydantic import BaseModel

from services.ai_service import analyze_document
from services.blockchain_service import issue_document, verify_document
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
    allowed_types = {"image/jpeg", "image/png", "application/pdf"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: JPEG, PNG, PDF.",
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

    def _mark_forged_due_to_chain(reason: str) -> None:
        ai_result["result"] = "Forged"
        ai_result["confidence"] = max(float(ai_result.get("confidence", 0.0)), 0.95)
        reasons = list(ai_result.get("reasons") or [])
        reasons.append(reason)
        ai_result["reasons"] = reasons

    if action == "save":
        try:
            tx_hash = issue_document(doc_hash, doc_hash)
            anchor_status = "anchored"
            logger.info("Blockchain tx: %s", tx_hash)
        except Exception as exc:
            anchor_status = "anchor_failed"
            anchor_error = str(exc)
            logger.warning("Blockchain anchor failed: %s", exc)
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
                _mark_forged_due_to_chain("Blockchain verification: document hash is revoked on-chain.")
            else:
                anchor_status = "not_found_on_chain"
                _mark_forged_due_to_chain("Blockchain verification: document hash not found on-chain.")
        except Exception as exc:
            anchor_status = "lookup_failed"
            anchor_error = str(exc)
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
        module_scores=ai_result.get("module_scores"),
        explanation=ai_result.get("explanation"),
        reasons=ai_result.get("reasons"),
        suspected_forgery_type=ai_result.get("suspected_forgery_type"),
        forgery_regions=ai_result.get("forgery_regions"),
    )

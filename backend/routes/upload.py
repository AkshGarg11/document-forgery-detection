"""
routes/upload.py
Handles document upload and orchestrates the full forgery-detection pipeline.
"""

import logging
from fastapi import APIRouter, File, UploadFile, HTTPException
from pydantic import BaseModel

from services.ai_service import analyze_document
from services.ipfs_service import upload_to_ipfs
from services.blockchain_service import store_on_blockchain
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
    module_scores: dict[str, float] | None = None
    explanation: str | None = None
    reasons: list[str] | None = None
    suspected_forgery_type: str | None = None
    forgery_regions: list[ForgeryRegion] | None = None


@router.post("/upload", response_model=AnalysisResult, summary="Upload a document for forgery analysis")
async def upload_document(file: UploadFile = File(...)):
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

    cid = upload_to_ipfs(content)
    logger.info("IPFS CID: %s", cid)

    tx_hash = store_on_blockchain(doc_hash, cid, ai_result["result"])
    logger.info("Blockchain tx: %s", tx_hash)

    return AnalysisResult(
        result=ai_result["result"],
        confidence=ai_result["confidence"],
        hash=doc_hash,
        cid=cid,
        tx_hash=tx_hash,
        module_scores=ai_result.get("module_scores"),
        explanation=ai_result.get("explanation"),
        reasons=ai_result.get("reasons"),
        suspected_forgery_type=ai_result.get("suspected_forgery_type"),
        forgery_regions=ai_result.get("forgery_regions"),
    )

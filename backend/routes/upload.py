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


class AnalysisResult(BaseModel):
    result: str          # "Authentic" | "Suspicious" | "Forged"
    confidence: float    # 0.0 – 1.0
    hash: str            # SHA-256 of the file
    cid: str             # IPFS Content Identifier
    tx_hash: str | None = None  # Blockchain transaction hash (optional)


@router.post("/upload", response_model=AnalysisResult, summary="Upload a document for forgery analysis")
async def upload_document(file: UploadFile = File(...)):
    """
    Pipeline:
    1. Read & hash file content
    2. Run AI forgery analysis
    3. Upload document to IPFS
    4. Record result on blockchain
    5. Return consolidated result
    """
    # --- Safety checks ---
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

    # Step 1 — Hash
    doc_hash = compute_hash(content)
    logger.info("Document hash: %s", doc_hash)

    # Step 2 — AI analysis
    ai_result = analyze_document(content, file.content_type)
    logger.info("AI result: %s (confidence=%.2f)", ai_result["result"], ai_result["confidence"])

    # Step 3 — IPFS upload
    cid = upload_to_ipfs(content)
    logger.info("IPFS CID: %s", cid)

    # Step 4 — Blockchain record
    tx_hash = store_on_blockchain(doc_hash, cid, ai_result["result"])
    logger.info("Blockchain tx: %s", tx_hash)

    return AnalysisResult(
        result=ai_result["result"],
        confidence=ai_result["confidence"],
        hash=doc_hash,
        cid=cid,
        tx_hash=tx_hash,
    )

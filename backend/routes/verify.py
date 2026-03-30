"""
routes/verify.py
Blockchain verification endpoints.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.blockchain_service import verify_document

router = APIRouter()


class VerifyRequest(BaseModel):
    file_hash: str


class VerifyResponse(BaseModel):
    exists: bool
    is_valid: bool
    revoked: bool
    timestamp: int
    issuer: str
    text_hash: str


@router.post("/verify", response_model=VerifyResponse, summary="Verify document hash on-chain")
async def verify_document_hash(payload: VerifyRequest):
    try:
        result = verify_document(payload.file_hash)
        return VerifyResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

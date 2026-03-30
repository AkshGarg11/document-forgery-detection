"""
routes/revoke.py
Blockchain revocation endpoint.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.blockchain_service import revoke_document

router = APIRouter()


class RevokeRequest(BaseModel):
    file_hash: str


class RevokeResponse(BaseModel):
    revoked_file_hash: str
    tx_hash: str


@router.post("/revoke", response_model=RevokeResponse, summary="Revoke document hash on-chain")
async def revoke_document_hash(payload: RevokeRequest):
    try:
        tx_hash = revoke_document(payload.file_hash)
        return RevokeResponse(revoked_file_hash=payload.file_hash, tx_hash=tx_hash)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

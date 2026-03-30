"""
routes/verify.py
Blockchain verification endpoints.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.blockchain_service import get_document_history, issue_document, verify_document

router = APIRouter()


class VerifyRequest(BaseModel):
    file_hash: str


class IssueHashResponse(BaseModel):
    issued_file_hash: str
    tx_hash: str


class VerifyResponse(BaseModel):
    exists: bool
    is_valid: bool
    revoked: bool
    timestamp: int
    issuer: str
    text_hash: str


class AuditEvent(BaseModel):
    event: str
    file_hash: str
    text_hash: str
    issuer: str
    timestamp: int
    block_number: int
    tx_hash: str


class AuditHistoryResponse(BaseModel):
    file_hash: str
    history: list[AuditEvent]


@router.post("/verify", response_model=VerifyResponse, summary="Verify document hash on-chain")
async def verify_document_hash(payload: VerifyRequest):
    try:
        result = verify_document(payload.file_hash)
        return VerifyResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/audit-history", response_model=AuditHistoryResponse, summary="Get blockchain audit history for a document hash")
async def get_audit_history(payload: VerifyRequest):
    try:
        history = get_document_history(payload.file_hash)
        return AuditHistoryResponse(file_hash=payload.file_hash, history=history)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/issue-hash", response_model=IssueHashResponse, summary="Issue analyzed document hash on-chain")
async def issue_document_hash(payload: VerifyRequest):
    try:
        tx_hash = issue_document(payload.file_hash, payload.file_hash, version="combined-detection-v1")
        return IssueHashResponse(issued_file_hash=payload.file_hash, tx_hash=tx_hash)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from services.blockchain_service import issue_document, verify_document
from services.signature_verification_service import predict_signature_verification
from utils.hashing import compute_hash


router = APIRouter()


class SignatureBox(BaseModel):
    x: float
    y: float
    w: float
    h: float


class SignatureVerificationResponse(BaseModel):
    result: str
    confidence: float
    forensic_verdict: str
    forensic_confidence: float
    probabilities: dict[str, float]
    signature_detected: bool
    signature_box: SignatureBox
    annotated_preview: str
    reason: str
    weights: dict[str, str]
    device: str
    hash: str
    tx_hash: str | None = None
    anchor_status: str | None = None
    anchor_error: str | None = None
    chain_exists: bool | None = None
    chain_revoked: bool | None = None
    chain_timestamp: int | None = None
    chain_issuer: str | None = None


@router.post(
    "/signature-verification/predict",
    response_model=SignatureVerificationResponse,
    summary="Detect signature area and verify authentic vs forged",
)
async def signature_verification_predict(
    image: UploadFile = File(...),
    blockchain_action: str = Form("find"),
):
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Only image uploads are supported.")

    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty image file.")

    action = blockchain_action.strip().lower()

    if action not in {"save", "find"}:
        raise HTTPException(status_code=422, detail="blockchain_action must be either 'save' or 'find'.")

    doc_hash = compute_hash(content)

    tx_hash: str | None = None
    anchor_status: str | None = None
    anchor_error: str | None = None
    chain_exists: bool | None = None
    chain_revoked: bool | None = None
    chain_timestamp: int | None = None
    chain_issuer: str | None = None

    try:
        result = predict_signature_verification(content)

        if action == "save":
            try:
                tx_hash = issue_document(doc_hash, doc_hash, version="signature-v1")
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
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Signature verification failed: {exc}") from exc

    result["hash"] = doc_hash
    result["tx_hash"] = tx_hash
    result["anchor_status"] = anchor_status
    result["anchor_error"] = anchor_error
    result["chain_exists"] = chain_exists
    result["chain_revoked"] = chain_revoked
    result["chain_timestamp"] = chain_timestamp
    result["chain_issuer"] = chain_issuer

    return SignatureVerificationResponse(**result)

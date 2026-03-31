"""Combined forgery detection route - runs signature verification and copy-move detection in parallel."""

from __future__ import annotations

import asyncio
import os
import re
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel

from services.blockchain_service import issue_document, verify_document
from services.doctamper_service import DocTamperService
from services.signature_verification_service import predict_signature_verification
from services.copy_move_service import CopyMoveForgeryDetectionService
from utils.hashing import compute_hash


router = APIRouter()
DOCTAMPER_ZERO_AREA_RATIO = 0.0005  # 0.05% => rounds to 0.0% with one decimal


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
    text_found: bool
    extracted_text_preview: str
    ocr_engine: str
    document_metadata: dict[str, Any]
    page_previews: list[str] = []
    analyzed_pages: int = 1
    selected_page_index: int = 1


def _to_json_primitive(value: Any) -> Any:
    """Convert library-specific scalar/container values into JSON-safe primitives."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value

    if isinstance(value, dict):
        return {str(k): _to_json_primitive(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_to_json_primitive(v) for v in value]

    # Pillow TIFF metadata often uses IFDRational; serialize it as numeric.
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        try:
            numeric = float(value)
            return int(numeric) if numeric.is_integer() else numeric
        except Exception:
            return str(value)

    try:
        numeric = float(value)
        return int(numeric) if numeric.is_integer() else numeric
    except Exception:
        return str(value)


def _extract_document_metadata(
    image: UploadFile,
    content: bytes,
    inferred_image_bytes: bytes | None = None,
    page_count: int | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "file_name": image.filename,
        "content_type": image.content_type,
        "size_bytes": len(content),
    }
    if page_count is not None:
        metadata["page_count"] = page_count

    image_bytes = inferred_image_bytes or content
    try:
        pil_img = Image.open(BytesIO(image_bytes))
        metadata.update(
            {
                "format": pil_img.format,
                "width": pil_img.width,
                "height": pil_img.height,
                "mode": pil_img.mode,
            }
        )
        dpi = pil_img.info.get("dpi")
        if dpi:
            metadata["dpi"] = list(dpi) if isinstance(dpi, tuple) else dpi
    except Exception:
        metadata.update(
            {
                "format": "unknown",
                "width": 0,
                "height": 0,
                "mode": "unknown",
            }
        )
    return _to_json_primitive(metadata)


def _render_pdf_pages(content: bytes, max_pages: int = 20) -> tuple[list[bytes], int]:
    """Render PDF pages to PNG bytes for image-based model pipelines."""
    try:
        import pypdfium2 as pdfium
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="PDF support requires pypdfium2. Install backend dependencies and retry.",
        ) from exc

    pdf = None
    page = None
    try:
        pdf = pdfium.PdfDocument(content)
        page_count = len(pdf)
        if page_count < 1:
            raise HTTPException(status_code=400, detail="Uploaded PDF has no pages.")

        rendered_pages: list[bytes] = []
        pages_to_render = min(page_count, max_pages)

        for idx in range(pages_to_render):
            page = pdf[idx]
            # Scale 2.0 improves OCR/model readability while keeping memory reasonable.
            pil_img = page.render(scale=2.0).to_pil().convert("RGB")
            buf = BytesIO()
            pil_img.save(buf, format="PNG")
            rendered_pages.append(buf.getvalue())
            page.close()
            page = None

        return rendered_pages, page_count
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to process PDF: {exc}") from exc
    finally:
        if page is not None:
            page.close()
        if pdf is not None:
            pdf.close()


def _normalize_doctamper_result(doctamper_result: dict[str, Any]) -> None:
    """Treat near-zero tampered area as authentic to avoid false visual positives."""
    doctamper_ratio = float(doctamper_result.get("tampered_pixels_ratio") or 0.0)
    if doctamper_ratio <= DOCTAMPER_ZERO_AREA_RATIO:
        doctamper_result["is_forged"] = False
        doctamper_result["forgery_type"] = "authentic"


def _select_preview_for_page(
    sig_result: dict[str, Any],
    copy_move_result: dict[str, Any],
    doctamper_result: dict[str, Any],
) -> str:
    if doctamper_result.get("annotated_preview"):
        return doctamper_result.get("annotated_preview", "")
    if sig_result.get("annotated_preview"):
        return sig_result.get("annotated_preview", "")
    return copy_move_result.get("annotated_preview", "")


def _page_severity_score(
    sig_result: dict[str, Any],
    copy_move_result: dict[str, Any],
    doctamper_result: dict[str, Any],
) -> float:
    verdict_text = str(sig_result.get("forensic_verdict") or "").lower()
    sig_forged = bool(sig_result.get("signature_detected")) and "forged" in verdict_text
    if sig_forged:
        return 300.0 + float(sig_result.get("confidence", 0.0))

    if doctamper_result.get("is_forged"):
        return 200.0 + float(doctamper_result.get("confidence", 0.0))

    if copy_move_result.get("is_forged"):
        return 100.0 + float(copy_move_result.get("confidence", 0.0))

    return float(doctamper_result.get("tampered_pixels_ratio", 0.0))


async def _run_detection_for_page(
    inference_content: bytes,
    text_found: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Run detection stack for one rendered page."""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=3) as executor:
        sig_future = loop.run_in_executor(
            executor, predict_signature_verification, inference_content
        )

        if text_found:
            doctamper_future = loop.run_in_executor(
                executor, DocTamperService.predict_doc_tamper, inference_content
            )
            sig_result, doctamper_result = await asyncio.gather(
                sig_future,
                doctamper_future,
            )
            copy_move_result = {
                "forgery_type": "authentic",
                "confidence": 1.0,
                "is_forged": False,
                "all_scores": {},
                "annotated_preview": "",
            }
        else:
            copy_move_future = loop.run_in_executor(
                executor,
                CopyMoveForgeryDetectionService.predict_copy_move_forgery,
                inference_content,
            )
            sig_result, copy_move_result = await asyncio.gather(
                sig_future,
                copy_move_future,
            )
            doctamper_result = {
                "forgery_type": "skipped_no_text",
                "confidence": 0.0,
                "is_forged": False,
                "tampered_pixels_ratio": 0.0,
                "annotated_preview": "",
            }

    _normalize_doctamper_result(doctamper_result)
    return sig_result, copy_move_result, doctamper_result


def _detect_text_with_ocr(content: bytes) -> tuple[bool, str, str]:
    """Return (text_found, text_preview, engine_label)."""
    try:
        import pytesseract

        tesseract_cmd = os.getenv("TESSERACT_CMD", "").strip()
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        elif os.name == "nt":
            default_win_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(default_win_cmd):
                pytesseract.pytesseract.tesseract_cmd = default_win_cmd

        pil_img = Image.open(BytesIO(content)).convert("L")
        extracted_text = pytesseract.image_to_string(pil_img, config="--psm 6")
        compact_text = " ".join(extracted_text.split())
        alnum_count = len(re.findall(r"[A-Za-z0-9]", compact_text))
        text_found = alnum_count >= 6
        preview = compact_text[:220]
        return text_found, preview, "pytesseract"
    except Exception:
        return False, "", "ocr_unavailable"


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
    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/tiff",
        "image/tif",
        "application/pdf",
    }
    if not image.content_type or image.content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail="Only JPEG, PNG, WEBP, TIFF, and PDF uploads are supported.",
        )

    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload.")

    inference_content = content
    analyzed_pages = 1
    selected_page_index = 1
    page_previews: list[str] = []
    page_count: int | None = None
    rendered_pages: list[bytes] = [content]
    if image.content_type == "application/pdf":
        rendered_pages, page_count = _render_pdf_pages(content)
        if not rendered_pages:
            raise HTTPException(status_code=400, detail="Uploaded PDF has no renderable pages.")
        inference_content = rendered_pages[0]
        analyzed_pages = len(rendered_pages)

    action = blockchain_action.strip().lower()
    if action not in {"save", "find"}:
        raise HTTPException(status_code=422, detail="blockchain_action must be either 'save' or 'find'.")

    doc_hash = compute_hash(content)
    document_metadata = _extract_document_metadata(
        image,
        content,
        inferred_image_bytes=inference_content,
        page_count=page_count,
    )
    text_found, extracted_text_preview, ocr_engine = _detect_text_with_ocr(inference_content)

    try:
        page_outputs: list[dict[str, Any]] = []
        text_found_any = False
        text_previews: list[str] = []

        for idx, page_bytes in enumerate(rendered_pages, start=1):
            page_text_found, page_text_preview, page_ocr_engine = _detect_text_with_ocr(page_bytes)
            text_found_any = text_found_any or page_text_found
            if page_text_preview:
                text_previews.append(page_text_preview)

            sig_result, copy_move_result, doctamper_result = await _run_detection_for_page(
                page_bytes,
                page_text_found,
            )

            page_outputs.append(
                {
                    "index": idx,
                    "text_found": page_text_found,
                    "ocr_engine": page_ocr_engine,
                    "sig": sig_result,
                    "copy": copy_move_result,
                    "doc": doctamper_result,
                    "preview": _select_preview_for_page(
                        sig_result,
                        copy_move_result,
                        doctamper_result,
                    ),
                    "severity": _page_severity_score(
                        sig_result,
                        copy_move_result,
                        doctamper_result,
                    ),
                }
            )

        if not page_outputs:
            raise HTTPException(status_code=500, detail="Detection produced no page outputs.")

        selected_page = max(page_outputs, key=lambda item: item["severity"])
        selected_page_index = int(selected_page["index"])
        page_previews = [item["preview"] for item in page_outputs]

        sig_result = selected_page["sig"]
        copy_move_result = selected_page["copy"]
        doctamper_result = selected_page["doc"]

        text_found = text_found_any
        extracted_text_preview = " | ".join(text_previews[:3])
        if not extracted_text_preview:
            extracted_text_preview = ""
        ocr_engine = selected_page["ocr_engine"]
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
    verdict_text = str(sig_result.get("forensic_verdict") or "").lower()
    sig_forged = bool(sig_result.get("signature_detected")) and "forged" in verdict_text
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
        f"Page: {selected_page_index}/{analyzed_pages} | "
        f"OCR: {'Text found' if text_found else 'No text found'} ({ocr_engine}) | "
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
        text_found=text_found,
        extracted_text_preview=extracted_text_preview,
        ocr_engine=ocr_engine,
        document_metadata=document_metadata,
        page_previews=page_previews,
        analyzed_pages=analyzed_pages,
        selected_page_index=selected_page_index,
    )

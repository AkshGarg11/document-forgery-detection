"""
ai_models/text/ocr.py
OCR module — extracts text from PDFs and images using real libraries.

PDF path:   PyMuPDF (fitz) — already installed
Image path: pytesseract — already installed (requires Tesseract binary)

Usage:
  from ai_models.text.ocr import extract_text
  text = extract_text(file_bytes, content_type="application/pdf")
"""

from __future__ import annotations
import io
import logging

logger = logging.getLogger(__name__)


def extract_text(content: bytes, content_type: str = "application/pdf") -> str:
    """
    Extract plain text from document bytes.

    Args:
        content:      Raw file bytes.
        content_type: MIME type ("application/pdf" or "image/*").

    Returns:
        Extracted text as a single string.
    """
    if content_type == "application/pdf":
        return _extract_from_pdf(content)
    elif content_type.startswith("image/"):
        return _extract_from_image(content)
    else:
        logger.warning("[OCR] Unsupported content_type '%s' — returning empty string.", content_type)
        return ""


def _extract_from_pdf(content: bytes) -> str:
    """Use PyMuPDF (fitz) to extract text from PDF bytes."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=content, filetype="pdf")
        pages = [page.get_text("text") for page in doc]
        text = "\n".join(pages).strip()
        logger.info("[OCR] PDF: extracted %d chars from %d pages", len(text), len(pages))
        return text
    except ImportError:
        logger.error("[OCR] PyMuPDF (fitz) not installed. Run: pip install PyMuPDF")
        return ""
    except Exception as exc:
        logger.error("[OCR] PDF extraction failed: %s", exc)
        return ""


def _extract_from_image(content: bytes) -> str:
    """Use pytesseract to extract text from image bytes."""
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(io.BytesIO(content)).convert("RGB")
        text = pytesseract.image_to_string(img, config="--psm 6").strip()
        logger.info("[OCR] Image: extracted %d chars", len(text))
        return text
    except ImportError:
        logger.error("[OCR] pytesseract or Pillow not installed.")
        return ""
    except Exception as exc:
        logger.error("[OCR] Image OCR failed: %s", exc)
        return ""

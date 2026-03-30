"""
shared/schemas/analysis_schema.py
Shared Pydantic models used across backend + any future microservices.
"""

from typing import Optional
from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    """Metadata passed alongside a file upload."""
    submitter_id: Optional[str] = Field(None, description="Optional user/session ID.")
    document_type: Optional[str] = Field(None, description="E.g. 'invoice', 'passport', 'contract'.")


class ModuleScores(BaseModel):
    """Individual AI module scores (0.0-1.0 forgery probability)."""
    ela: Optional[float] = None
    copy_move: Optional[float] = None
    nlp: Optional[float] = None


class ForgeryRegion(BaseModel):
    x: float
    y: float
    w: float
    h: float
    source: Optional[str] = None
    score: Optional[float] = None


class AnalysisResponse(BaseModel):
    """Full analysis result returned to the client."""
    result: str = Field(..., description="Authentic | Suspicious | Forged")
    confidence: float = Field(..., ge=0.0, le=1.0)
    hash: str = Field(..., description="SHA-256 of the submitted document.")
    cid: str = Field(..., description="IPFS Content Identifier.")
    tx_hash: Optional[str] = Field(None, description="Blockchain transaction hash for anchor operation.")
    anchor_status: Optional[str] = Field(None, description="anchored | anchor_failed | not_anchored")
    anchor_error: Optional[str] = Field(None, description="Anchor error details when chain write fails.")
    module_scores: Optional[ModuleScores] = None
    explanation: Optional[str] = Field(None, description="Human-readable explanation of the verdict.")
    reasons: Optional[list[str]] = Field(None, description="Evidence points from each analysis module.")
    suspected_forgery_type: Optional[str] = Field(
        None,
        description="Most likely forgery subtype, e.g., Copy-Move, Splicing/Composite Edit, Textual Forgery.",
    )
    forgery_regions: Optional[list[ForgeryRegion]] = None

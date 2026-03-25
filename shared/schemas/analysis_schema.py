"""
shared/schemas/analysis_schema.py
Shared Pydantic models used across backend + any future microservices.
"""

from pydantic import BaseModel, Field
from typing import Optional


class AnalysisRequest(BaseModel):
    """Metadata passed alongside a file upload."""
    submitter_id: Optional[str] = Field(None, description="Optional user/session ID.")
    document_type: Optional[str] = Field(None, description="E.g. 'invoice', 'passport', 'contract'.")


class ModuleScores(BaseModel):
    """Individual AI module scores (0.0–1.0 forgery probability)."""
    ela: Optional[float] = None
    copy_move: Optional[float] = None
    nlp: Optional[float] = None


class AnalysisResponse(BaseModel):
    """Full analysis result returned to the client."""
    result: str = Field(..., description="Authentic | Suspicious | Forged")
    confidence: float = Field(..., ge=0.0, le=1.0)
    hash: str = Field(..., description="SHA-256 of the submitted document.")
    cid: str = Field(..., description="IPFS Content Identifier.")
    tx_hash: Optional[str] = Field(None, description="Blockchain transaction hash.")
    module_scores: Optional[ModuleScores] = None

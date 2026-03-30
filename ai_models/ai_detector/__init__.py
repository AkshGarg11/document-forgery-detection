"""Inference package for AI-generated image detection."""

from .predictor import AiDetectorPredictor
from .signature_verification import SignatureVerificationPipeline

__all__ = ["AiDetectorPredictor", "SignatureVerificationPipeline"]

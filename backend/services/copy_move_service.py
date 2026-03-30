"""Service layer for copy-move forgery detection."""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_models.copy_move_detector import CopyMoveForgeryDetectionPipeline


class CopyMoveForgeryDetectionService:
    """Lazy-loaded service for copy-move forgery detection."""

    _pipeline = None

    @classmethod
    def _resolve_model_path(cls) -> Path:
        """Resolve path to copy_move.pth model weights."""
        model_name = "copy_move.pth"

        # Check environment variable first
        env_path = os.getenv("COPY_MOVE_MODEL_PATH")
        if env_path and Path(env_path).exists():
            return Path(env_path)

        # Check default locations (from backend/services/ perspective)
        search_dirs = [
            Path(__file__).resolve().parents[3] / "ai_models" / "models",  # d:/document-forgery-detection/ai_models/models
            Path("ai_models/models"),
            Path("../ai_models/models"),
        ]

        for directory in search_dirs:
            model_file = directory / model_name
            if model_file.exists():
                return model_file

        raise FileNotFoundError(
            f"Model weights {model_name} not found in: {', '.join(str(d) for d in search_dirs)}"
        )

    @classmethod
    def _load_pipeline(cls) -> CopyMoveForgeryDetectionPipeline:
        """Lazy-load the pipeline."""
        if cls._pipeline is None:
            model_path = cls._resolve_model_path()
            cls._pipeline = CopyMoveForgeryDetectionPipeline(
                model_path=model_path,
                threshold=0.5,
                img_size=256,
            )
        return cls._pipeline

    @classmethod
    def predict_copy_move_forgery(cls, image_bytes: bytes) -> dict:
        """
        Predict copy-move forgery for image.

        Args:
            image_bytes: Image file bytes

        Returns:
            Dict with forgery_type, confidence, all_scores, is_forged, annotated_preview
        """
        pipeline = cls._load_pipeline()
        return pipeline.predict(image_bytes)

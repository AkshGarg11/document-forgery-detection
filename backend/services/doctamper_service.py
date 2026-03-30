"""Service layer for DocTamper forgery localization."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_models.doctamper import DocTamperPipeline


class DocTamperService:
    """Lazy-loaded DocTamper inference service."""

    _pipeline: DocTamperPipeline | None = None

    @classmethod
    def _resolve_model_path(cls) -> Path:
        """Resolve path to DocTamper model weights."""
        preferred_names = [
            "doctamper_tampernet.pth",
            "doctamper_tempernet.pth",
            "doctamper_tampernet_overall_best.pth",
        ]

        env_path = os.getenv("DOCTAMPER_MODEL_PATH")
        if env_path and Path(env_path).exists():
            return Path(env_path)

        search_dirs = [
            Path(__file__).resolve().parents[3] / "ai_models" / "models",
            Path("ai_models/models"),
            Path("../ai_models/models"),
        ]

        for directory in search_dirs:
            for model_name in preferred_names:
                candidate = directory / model_name
                if candidate.exists():
                    return candidate

            # Fallback: any doctamper*.pth file.
            if directory.exists():
                matches = sorted(directory.glob("doctamper*.pth"))
                if matches:
                    return matches[0]

        looked_up = [str(d / n) for d in search_dirs for n in preferred_names]
        raise FileNotFoundError(
            "DocTamper model weights not found. Checked: " + ", ".join(looked_up)
        )

    @classmethod
    def _load_pipeline(cls) -> DocTamperPipeline:
        if cls._pipeline is None:
            model_path = cls._resolve_model_path()
            cls._pipeline = DocTamperPipeline(
                model_path=model_path,
                cls_threshold=0.5,
                mask_threshold=0.5,
                img_size=512,
            )
        return cls._pipeline

    @classmethod
    def predict_doc_tamper(cls, image_bytes: bytes) -> dict:
        pipeline = cls._load_pipeline()
        return pipeline.predict(image_bytes)

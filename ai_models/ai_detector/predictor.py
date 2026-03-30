from __future__ import annotations

import io
import os
import glob
import threading
from pathlib import Path

import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms
from transformers import CvtForImageClassification


LABEL_MAP = {0: "REAL", 1: "AI-GENERATED"}


class CustomClassifier(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.fc1 = nn.Linear(384, 256)
        self.mish1 = nn.Mish(inplace=False)
        self.norm1 = nn.BatchNorm1d(256)
        self.dropout1 = nn.Dropout(p=0.5)
        self.fc2 = nn.Linear(256, 128)
        self.mish2 = nn.Mish(inplace=False)
        self.norm2 = nn.BatchNorm1d(128)
        self.dropout2 = nn.Dropout(p=0.3)
        self.fc_out = nn.Linear(128, 2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.dropout1(self.norm1(self.mish1(self.fc1(x))))
        x = self.dropout2(self.norm2(self.mish2(self.fc2(x))))
        return self.fc_out(x)


class AiDetectorPredictor:
    """Lazy-loaded predictor for CvT-13 AI image detection."""

    def __init__(self, weights_folder: str | Path | None = None) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.weights_folder = Path(weights_folder or os.getenv("AI_DETECTOR_WEIGHTS_DIR", "./ai_models/ai_detector/models"))
        self._transform = transforms.Compose(
            [
                transforms.Resize((200, 200)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )
        self._lock = threading.Lock()
        self._model: CvtForImageClassification | None = None
        self._loaded_weight_file: str | None = None

    def _build_model(self) -> CvtForImageClassification:
        model = CvtForImageClassification.from_pretrained("microsoft/cvt-13")
        model.classifier = CustomClassifier()
        model.to(self.device)
        return model

    def _resolve_weight_file(self) -> Path:
        # Search primary configured directory first, then fallback to ai_models/models.
        search_dirs = [self.weights_folder, Path(__file__).resolve().parents[1] / "models"]

        # Remove duplicates while preserving order.
        unique_dirs: list[Path] = []
        for d in search_dirs:
            if d not in unique_dirs:
                unique_dirs.append(d)

        for directory in unique_dirs:
            exact = directory / "ai_detector.pth"
            if exact.exists():
                return exact

            epoch24 = directory / "model_epoch_24.pth"
            if epoch24.exists():
                return epoch24

            files = glob.glob(str(directory / "model_epoch_*.pth"))
            if files:
                return Path(max(files, key=os.path.getctime))

        searched = ", ".join(str(d) for d in unique_dirs)
        raise FileNotFoundError(
            "No model weights found. Expected ai_detector.pth or model_epoch_*.pth in: "
            f"{searched}"
        )

    @staticmethod
    def _clean_state_dict(state_dict: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        if not state_dict:
            return state_dict
        sample_key = next(iter(state_dict.keys()))
        if sample_key.startswith("module."):
            return {k.replace("module.", "", 1): v for k, v in state_dict.items()}
        return state_dict

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return

            model = self._build_model()
            weight_file = self._resolve_weight_file()
            checkpoint = torch.load(weight_file, map_location=self.device)

            if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
                state_dict = checkpoint["model_state_dict"]
            elif isinstance(checkpoint, dict):
                state_dict = checkpoint
            else:
                raise ValueError("Unsupported checkpoint format for ai_detector weights")

            state_dict = self._clean_state_dict(state_dict)
            model.load_state_dict(state_dict, strict=False)
            model.eval()

            self._model = model
            self._loaded_weight_file = str(weight_file)

    @property
    def loaded_weight_file(self) -> str | None:
        return self._loaded_weight_file

    def predict(self, image_bytes: bytes) -> dict:
        self.load()
        assert self._model is not None

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        tensor = self._transform(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            logits = self._model(tensor).logits
            probs = torch.nn.functional.softmax(logits, dim=1)[0]
            pred = int(logits.argmax(dim=1).item())

        return {
            "label": LABEL_MAP[pred],
            "probabilities": {
                "real": round(float(probs[0].item() * 100), 2),
                "ai_generated": round(float(probs[1].item() * 100), 2),
            },
            "device": str(self.device),
            "weights": self._loaded_weight_file,
        }

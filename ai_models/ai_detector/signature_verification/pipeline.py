from __future__ import annotations

import base64
import io
import importlib
import threading
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torchvision.models as models
from PIL import Image, ImageDraw
from torchvision import transforms


class SignatureVerificationPipeline:
    def __init__(
        self,
        layout_model_path: str | Path,
        signature_model_path: str | Path,
        threshold: float = 0.5,
    ) -> None:
        self.layout_model_path = Path(layout_model_path)
        self.signature_model_path = Path(signature_model_path)
        self.threshold = threshold

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._lock = threading.Lock()
        self._layout_model = None
        self._signature_model = None

        self._signature_tf = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

    def _load_layout_model(self):
        if self._layout_model is not None:
            return
        if not self.layout_model_path.exists():
            raise FileNotFoundError(f"layout model not found: {self.layout_model_path}")

        ultralytics_module = importlib.import_module("ultralytics")
        yolo_cls = getattr(ultralytics_module, "YOLO")
        self._layout_model = yolo_cls(str(self.layout_model_path))

    def _build_signature_model(self) -> nn.Module:
        model = models.resnet18(weights=None)
        out_features = model.fc.in_features
        model.fc = nn.Sequential(
            nn.Linear(out_features, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(inplace=True),
            nn.Dropout(p=0.5),
            nn.Linear(256, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(inplace=True),
            nn.Dropout(p=0.3),
            nn.Linear(64, 1),
        )
        return model

    def _load_signature_model(self):
        if self._signature_model is not None:
            return
        if not self.signature_model_path.exists():
            raise FileNotFoundError(f"signature model not found: {self.signature_model_path}")

        model = self._build_signature_model().to(self.device)
        state_dict = torch.load(self.signature_model_path, map_location=self.device)
        if isinstance(state_dict, dict) and "model_state_dict" in state_dict:
            state_dict = state_dict["model_state_dict"]
        model.load_state_dict(state_dict, strict=False)
        model.eval()
        self._signature_model = model

    def _load_models(self) -> None:
        with self._lock:
            self._load_layout_model()
            self._load_signature_model()

    @staticmethod
    def _clamp_bbox(x1: int, y1: int, x2: int, y2: int, w: int, h: int) -> tuple[int, int, int, int]:
        x1 = max(0, min(x1, w - 1))
        y1 = max(0, min(y1, h - 1))
        x2 = max(x1 + 1, min(x2, w))
        y2 = max(y1 + 1, min(y2, h))
        return x1, y1, x2, y2

    def _detect_signature_bbox(self, image: Image.Image) -> tuple[int, int, int, int] | None:
        assert self._layout_model is not None

        arr = np.array(image.convert("RGB"))
        results = self._layout_model.predict(source=arr, verbose=False, conf=0.15)
        if not results:
            return None

        r = results[0]
        boxes = getattr(r, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return None

        conf = boxes.conf.detach().cpu().numpy()
        xyxy = boxes.xyxy.detach().cpu().numpy()
        best_idx = int(np.argmax(conf))
        x1, y1, x2, y2 = [int(v) for v in xyxy[best_idx]]

        w, h = image.size
        return self._clamp_bbox(x1, y1, x2, y2, w, h)

    def _classify_signature_crop(self, crop: Image.Image) -> tuple[float, float, str]:
        assert self._signature_model is not None

        tensor = self._signature_tf(crop.convert("RGB")).unsqueeze(0).to(self.device)
        with torch.no_grad():
            logit = self._signature_model(tensor)
            p_auth = float(torch.sigmoid(logit).item())

        p_fake = 1.0 - p_auth
        label = "Authentic" if p_auth >= self.threshold else "Forged"
        return p_auth, p_fake, label

    @staticmethod
    def _to_data_url(image: Image.Image) -> str:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    def predict(self, image_bytes: bytes) -> dict:
        self._load_models()

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        bbox = self._detect_signature_bbox(image)

        if bbox is None:
            return {
                "result": "No Signature Detected",
                "confidence": 0.0,
                "forensic_verdict": "No signature detected by layout model",
                "forensic_confidence": 0.0,
                "probabilities": {
                    "authentic": 0.0,
                    "forged": 0.0,
                },
                "signature_detected": False,
                "signature_box": {
                    "x": 0.0,
                    "y": 0.0,
                    "w": 0.0,
                    "h": 0.0,
                },
                "annotated_preview": self._to_data_url(image),
                "reason": "Signature region not detected by layout model.",
                "weights": {
                    "layout": str(self.layout_model_path),
                    "signature": str(self.signature_model_path),
                },
                "device": str(self.device),
            }

        x1, y1, x2, y2 = bbox
        crop = image.crop((x1, y1, x2, y2))
        p_auth, p_fake, label = self._classify_signature_crop(crop)

        draw = ImageDraw.Draw(image)
        color = (22, 163, 74) if label == "Authentic" else (220, 38, 38)
        draw.rectangle([x1, y1, x2, y2], outline=color, width=4)
        draw.rectangle([x1, max(0, y1 - 22), min(image.size[0], x1 + 220), y1], fill=color)
        draw.text((x1 + 6, max(0, y1 - 18)), f"Signature: {label}", fill=(255, 255, 255))

        w, h = image.size
        box_norm = {
            "x": x1 / w,
            "y": y1 / h,
            "w": (x2 - x1) / w,
            "h": (y2 - y1) / h,
        }

        return {
            "result": label,
            "confidence": round(p_auth if label == "Authentic" else p_fake, 4),
            "forensic_verdict": f"Signature is {label}",
            "forensic_confidence": round(p_auth if label == "Authentic" else p_fake, 4),
            "probabilities": {
                "authentic": round(p_auth * 100, 2),
                "forged": round(p_fake * 100, 2),
            },
            "signature_detected": True,
            "signature_box": box_norm,
            "annotated_preview": self._to_data_url(image),
            "reason": "Signature region detected by layout model.",
            "weights": {
                "layout": str(self.layout_model_path),
                "signature": str(self.signature_model_path),
            },
            "device": str(self.device),
        }

"""DocTamper forgery localization pipeline."""

from __future__ import annotations

import base64
import io
import threading
from pathlib import Path
from typing import Any

import numpy as np
import segmentation_models_pytorch as smp
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms


class TamperNet(nn.Module):
    """Unet + classification head used by DocTamper model."""

    def __init__(self, encoder_name: str = "efficientnet-b0", encoder_weights: str | None = None):
        super().__init__()
        self.seg = smp.Unet(
            encoder_name=encoder_name,
            encoder_weights=encoder_weights,
            in_channels=3,
            classes=1,
        )
        enc_ch = self.seg.encoder.out_channels[-1]
        self.cls_head = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Dropout(0.2),
            nn.Linear(enc_ch, 1),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        features = self.seg.encoder(x)
        dec_out = self.seg.decoder(*features)
        mask_logits = self.seg.segmentation_head(dec_out)
        cls_logits = self.cls_head(features[-1])
        return mask_logits, cls_logits


class DocTamperPipeline:
    """Runs DocTamper classification + pixel-level tamper localization."""

    def __init__(
        self,
        model_path: str | Path,
        cls_threshold: float = 0.5,
        mask_threshold: float = 0.5,
        img_size: int = 512,
    ) -> None:
        self.model_path = Path(model_path)
        self.cls_threshold = cls_threshold
        self.mask_threshold = mask_threshold
        self.img_size = img_size

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._lock = threading.Lock()
        self._model: TamperNet | None = None

        self._transform = transforms.Compose(
            [
                transforms.Resize((img_size, img_size)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

    def _load_model(self) -> None:
        if self._model is not None:
            return

        if not self.model_path.exists():
            raise FileNotFoundError(f"Model weights not found: {self.model_path}")

        model = TamperNet(encoder_name="efficientnet-b0", encoder_weights=None).to(self.device)
        checkpoint: Any = torch.load(self.model_path, map_location=self.device)

        if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
            state_dict = checkpoint["model_state_dict"]
        elif isinstance(checkpoint, dict) and "state_dict" in checkpoint:
            state_dict = checkpoint["state_dict"]
        else:
            state_dict = checkpoint

        model.load_state_dict(state_dict, strict=False)
        model.eval()
        self._model = model

    @staticmethod
    def _overlay_mask(image_np: np.ndarray, mask_np: np.ndarray, alpha: float = 0.45) -> np.ndarray:
        """Blend predicted tamper mask onto image in red."""
        out = image_np.astype(np.float32).copy()
        red = np.array([220.0, 30.0, 30.0], dtype=np.float32)
        for ch in range(3):
            out[..., ch] = np.where(
                mask_np > 0,
                (1 - alpha) * out[..., ch] + alpha * red[ch],
                out[..., ch],
            )
        return out.clip(0, 255).astype(np.uint8)

    def predict(self, image_bytes: bytes) -> dict[str, Any]:
        with self._lock:
            self._load_model()

        assert self._model is not None

        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        orig_np = np.array(pil_img)
        h, w = orig_np.shape[:2]

        inp = self._transform(pil_img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            mask_logits, cls_logits = self._model(inp)
            cls_prob = float(torch.sigmoid(cls_logits).item())
            is_forged = cls_prob >= self.cls_threshold

            mask_prob = torch.sigmoid(mask_logits)
            mask_prob = F.interpolate(mask_prob, size=(h, w), mode="bilinear", align_corners=False)
            mask_prob_np = mask_prob[0, 0].cpu().numpy()
            mask_bin_np = (mask_prob_np >= self.mask_threshold).astype(np.uint8)

        tampered_pct = float(mask_bin_np.mean())
        preview_np = self._overlay_mask(orig_np, mask_bin_np)

        # Border color reflects image-level classification.
        border_color = np.array([220, 30, 30], dtype=np.uint8) if is_forged else np.array([30, 160, 30], dtype=np.uint8)
        t = 6
        preview_np[:t, :] = border_color
        preview_np[-t:, :] = border_color
        preview_np[:, :t] = border_color
        preview_np[:, -t:] = border_color

        out_pil = Image.fromarray(preview_np)
        buf = io.BytesIO()
        out_pil.save(buf, format="PNG")
        preview_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        return {
            "forgery_type": "tampered_region_detected" if is_forged else "authentic",
            "confidence": cls_prob,
            "is_forged": is_forged,
            "tampered_pixels_ratio": tampered_pct,
            "all_scores": {
                "authentic": 1.0 - cls_prob,
                "tampered_region_detected": cls_prob,
            },
            "annotated_preview": f"data:image/png;base64,{preview_b64}",
        }

"""
Copy-Move Forgery Detection Pipeline.
Uses ResNet34 encoder with ELA (Error Level Analysis) to classify images as:
- authentic (no copy-move detected)
- copy_move, splicing, removal, object_insertion (forgery types)
"""

from __future__ import annotations

import base64
import io
import threading
from pathlib import Path
from typing import Dict

import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageDraw, ImageChops, ImageEnhance
from torchvision import transforms


FORGERY_TYPES = {
    0: "authentic",
    1: "forged_detected",
}

FORGERY_COLORS = {
    "authentic": "#00DD00",  # Green
    "copy_move": "#FF0000",  # Red
    "splicing": "#FF6600",   # Orange
    "removal": "#FF00FF",    # Magenta
    "object_insertion": "#FFFF00",  # Yellow
}


class CopyMoveForgeryDetectionPipeline:
    """Detects copy-move and other forgery types using ResNet34 + ELA."""

    def __init__(
        self,
        model_path: str | Path,
        threshold: float = 0.5,
        img_size: int = 256,
    ) -> None:
        self.model_path = Path(model_path)
        self.threshold = threshold
        self.img_size = img_size

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._lock = threading.Lock()
        self._model = None

        self._transform = transforms.Compose(
            [
                transforms.Resize((img_size, img_size)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

    def _build_model(self) -> nn.Module:
        """Build ResNet34-based classifier for 6-channel input (RGB + ELA).
        
        Matches the checkpoint structure with encoder + classification head.
        """
        from torchvision.models import resnet34
        
        # Create ResNet34 with 6-channel input
        encoder = resnet34(weights=None)
        # Replace first layer to accept 6 channels instead of 3
        encoder.conv1 = nn.Conv2d(6, 64, kernel_size=7, stride=2, padding=3, bias=False)
        
        # Build classification head for 2 classes (authentic vs forged)
        enc_out_ch = 512  # ResNet34 output channels
        cls_head = nn.Sequential(
            nn.Linear(enc_out_ch, 256),
            nn.ReLU(),
            nn.Dropout(0.4),
            nn.Linear(256, 2),  # Binary: authentic vs forged
        )

        # Create combined model
        model = nn.Module()
        model.encoder = encoder
        model.cls_head = cls_head
        return model

    def _load_model(self) -> None:
        """Lazy-load model with thread safety."""
        if self._model is not None:
            return

        if not self.model_path.exists():
            raise FileNotFoundError(f"Model weights not found: {self.model_path}")

        model = self._build_model().to(self.device)
        checkpoint = torch.load(self.model_path, map_location=self.device)

        # Handle both full checkpoint and raw state_dict
        if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
            state_dict = checkpoint["model_state_dict"]
        else:
            state_dict = checkpoint

        model.load_state_dict(state_dict, strict=False)
        model.eval()
        self._model = model

    @staticmethod
    def _compute_ela(image_path: str | Path, quality: int = 90) -> np.ndarray:
        """Compute Error Level Analysis (ELA) from image."""
        try:
            image = Image.open(image_path).convert("RGB")
            buf = io.BytesIO()
            image.save(buf, "JPEG", quality=quality)
            buf.seek(0)
            temp = Image.open(buf).copy()
            ela = ImageChops.difference(image, temp)
            extrema = ela.getextrema()
            max_diff = max(ex[1] for ex in extrema) or 1
            ela = ImageEnhance.Brightness(ela).enhance(255.0 / max_diff)
            ela_arr = np.array(ela)
            return cv2.resize(ela_arr, (self.img_size, self.img_size))
        except Exception as e:
            print(f"ELA computation error: {e}")
            return np.zeros((self.img_size, self.img_size, 3), dtype=np.uint8)

    def _preprocess_image(
        self, image_bytes: bytes
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Preprocess image: RGB + ELA concatenation."""
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image_arr = np.array(image)
        image_arr = cv2.resize(image_arr, (self.img_size, self.img_size))

        # Compute ELA (use image buffer instead of file)
        temp_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        buf = io.BytesIO()
        temp_pil.save(buf, "JPEG", quality=90)
        buf.seek(0)
        temp_img = Image.open(buf).copy()
        ela = ImageChops.difference(temp_pil, temp_img)
        extrema = ela.getextrema()
        max_diff = max(ex[1] for ex in extrema) or 1
        ela = ImageEnhance.Brightness(ela).enhance(255.0 / max_diff)
        ela_arr = np.array(ela)
        ela_arr = cv2.resize(ela_arr, (self.img_size, self.img_size))

        return image_arr, ela_arr, np.array(image)

    def predict(self, image_bytes: bytes) -> Dict:
        """
        Predict forgery type for image.

        Returns:
            Dict with keys:
            - forgery_type: str (authentic/copy_move/splicing/removal/object_insertion)
            - confidence: float
            - all_scores: dict of scores for each class
            - is_forged: bool
            - preview: data URL with annotated image
        """
        with self._lock:
            self._load_model()

        assert self._model is not None

        # Preprocess
        rgb_arr, ela_arr, orig_arr = self._preprocess_image(image_bytes)

        # Normalize
        rgb_tensor = self._transform(Image.fromarray(rgb_arr))
        ela_tensor = self._transform(Image.fromarray(ela_arr))

        # Concatenate RGB + ELA (6 channels)
        inp = torch.cat([rgb_tensor, ela_tensor], dim=0).unsqueeze(0).to(self.device)

        with torch.no_grad():
            # Get encoder features
            # ResNet forward returns: x -> conv1 -> bn1 -> relu -> maxpool -> layer1-4 -> avgpool -> flatten
            # But we want just before the flattening
            x = inp
            x = self._model.encoder.conv1(x)
            x = self._model.encoder.bn1(x)
            x = self._model.encoder.relu(x)
            x = self._model.encoder.maxpool(x)
            x = self._model.encoder.layer1(x)
            x = self._model.encoder.layer2(x)
            x = self._model.encoder.layer3(x)
            x = self._model.encoder.layer4(x)
            
            # Apply adaptive average pooling and flatten
            x = self._model.encoder.avgpool(x)
            x = torch.flatten(x, 1)
            
            # Pass through classification head
            logits = self._model.cls_head(x)

        probs = torch.softmax(logits, dim=1)[0]
        pred_class = int(probs.argmax().item())
        confidence = float(probs[pred_class].item())

        forgery_type = FORGERY_TYPES.get(pred_class, "unknown")
        is_forged = forgery_type != "authentic"

        # Generate annotated preview
        color_map = {
            "authentic": (0, 255, 0),  # Green BGR
            "forged_detected": (0, 0, 255),  # Red
        }

        color = color_map.get(forgery_type, (128, 128, 128))
        preview_arr = orig_arr.copy()

        # Draw border indicating forgery type
        h, w = preview_arr.shape[:2]
        border_thickness = 5
        cv2.rectangle(
            preview_arr,
            (0, 0),
            (w - 1, h - 1),
            color,
            border_thickness,
        )

        # Add text label
        text = f"{forgery_type.replace('_', ' ').title()} ({confidence:.2%})"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        thickness = 2
        (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)

        cv2.rectangle(
            preview_arr,
            (10, 10),
            (10 + text_w + 10, 10 + text_h + 10),
            (0, 0, 0),
            -1,
        )
        cv2.putText(
            preview_arr,
            text,
            (15, 10 + text_h),
            font,
            font_scale,
            (255, 255, 255),
            thickness,
        )

        # Convert to data URL
        preview_pil = Image.fromarray(cv2.cvtColor(preview_arr, cv2.COLOR_BGR2RGB))
        buf = io.BytesIO()
        preview_pil.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        preview_url = f"data:image/png;base64,{b64}"

        # Score mapping
        all_scores = {
            FORGERY_TYPES[i]: float(probs[i].item()) for i in range(len(FORGERY_TYPES))
        }

        return {
            "forgery_type": forgery_type,
            "confidence": confidence,
            "all_scores": all_scores,
            "is_forged": is_forged,
            "annotated_preview": preview_url,
        }

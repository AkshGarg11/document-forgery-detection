from __future__ import annotations

import io
import logging
from pathlib import Path

import torch
from PIL import Image
from torchvision import transforms

try:
    from .cnn_pipeline import build_backbone, resolve_device
except ImportError:
    from image.cnn_pipeline import build_backbone, resolve_device

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_PATH = _ROOT / "models" / "forgery_type_cnn.pt"
IMAGE_SIZE = 224


def predict_forgery_type(content: bytes) -> tuple[str | None, float | None]:
    """Predict forgery subtype from image bytes, if subtype checkpoint exists."""
    if not CHECKPOINT_PATH.exists():
        return None, None

    try:
        device = resolve_device()
        checkpoint = torch.load(CHECKPOINT_PATH, map_location=device)

        backbone = checkpoint.get("backbone", "resnet18")
        class_names: list[str] = checkpoint.get("class_names", [])
        if not class_names:
            return None, None

        model = build_backbone(backbone=backbone, num_classes=len(class_names), pretrained=False)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.to(device)
        model.eval()

        transform = transforms.Compose(
            [
                transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

        image = Image.open(io.BytesIO(content)).convert("RGB")
        tensor = transform(image).unsqueeze(0).to(device)

        with torch.no_grad():
            logits = model(tensor)
            probs = torch.softmax(logits, dim=1)[0]

        idx = int(torch.argmax(probs).item())
        pred = class_names[idx]
        conf = float(probs[idx].item())
        return pred, conf
    except Exception as exc:
        logger.error("[FORGERY-TYPE] prediction error: %s", exc)
        return None, None

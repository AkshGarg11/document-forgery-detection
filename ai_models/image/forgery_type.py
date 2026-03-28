from __future__ import annotations

import io
import logging
from pathlib import Path

import torch
from PIL import Image
from torch import nn
from torchvision import models
from torchvision import transforms
from torchvision.models import ResNet50_Weights

try:
    from .cnn_pipeline import resolve_device
except ImportError:
    from image.cnn_pipeline import resolve_device

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_PATH = _ROOT / "models" / "forgery_type_cnn.pt"
IMAGE_SIZE = 224


class FixedSRMConv(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.conv = nn.Conv2d(3, 3, kernel_size=5, stride=1, padding=2, groups=3, bias=False)

        base = torch.tensor(
            [
                [0.0, 0.0, -1.0, 0.0, 0.0],
                [0.0, 2.0, -4.0, 2.0, 0.0],
                [-1.0, -4.0, 12.0, -4.0, -1.0],
                [0.0, 2.0, -4.0, 2.0, 0.0],
                [0.0, 0.0, -1.0, 0.0, 0.0],
            ],
            dtype=torch.float32,
        ) / 12.0
        kernel = torch.zeros((3, 1, 5, 5), dtype=torch.float32)
        kernel[0, 0] = base
        kernel[1, 0] = base
        kernel[2, 0] = base

        with torch.no_grad():
            self.conv.weight.copy_(kernel)

        for p in self.conv.parameters():
            p.requires_grad = False

        self.trunc = nn.Hardtanh(min_val=-3.0, max_val=3.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.trunc(self.conv(x))


class DualStreamResNet50SRM(nn.Module):
    def __init__(self, num_classes: int, pretrained: bool = False) -> None:
        super().__init__()
        weights = ResNet50_Weights.IMAGENET1K_V2 if pretrained else None

        self.srm = FixedSRMConv()
        self.rgb_backbone = models.resnet50(weights=weights)
        self.rgb_backbone.fc = nn.Identity()
        self.srm_backbone = models.resnet50(weights=weights)
        self.srm_backbone.fc = nn.Identity()
        self.classifier = nn.Sequential(
            nn.Linear(4096, 1024),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(1024, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        rgb_feat = self.rgb_backbone(x)
        srm_feat = self.srm_backbone(self.srm(x))
        return self.classifier(torch.cat([rgb_feat, srm_feat], dim=1))


def predict_forgery_type(content: bytes) -> tuple[str | None, float | None]:
    """Predict forgery subtype from image bytes, if subtype checkpoint exists."""
    if not CHECKPOINT_PATH.exists():
        return None, None

    try:
        device = resolve_device()
        checkpoint = torch.load(CHECKPOINT_PATH, map_location=device)

        backbone = checkpoint.get("backbone", "dual_stream_resnet50_srm")
        class_names: list[str] = checkpoint.get("class_names", [])
        if not class_names:
            return None, None

        if backbone == "dual_stream_resnet50_srm":
            model = DualStreamResNet50SRM(num_classes=len(class_names), pretrained=False)
        else:
            logger.error("[FORGERY-TYPE] Unsupported checkpoint backbone: %s", backbone)
            return None, None

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
        tensor = transform(image).unsqueeze(0).to(device, non_blocking=True)

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

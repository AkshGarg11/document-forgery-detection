from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Callable

import imagehash
import numpy as np
import torch
from PIL import Image, ImageChops, ImageDraw
from torch import nn
from torch.utils.data import Dataset
from torchvision import models, transforms

logger = logging.getLogger(__name__)


IMAGE_SIZE = 224
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


Preprocessor = Callable[[bytes], Image.Image]


def compute_perceptual_hash(content: bytes) -> str:
    """
    Compute perceptual hash (pHash) of image using average hash.
    Returns 64-character hex string representing visual fingerprint.
    """
    try:
        image = Image.open(io.BytesIO(content)).convert("RGB")
        # Compute perceptual hash using average method (8x8 basis = 64 bits)
        phash = imagehash.average_hash(image, hash_size=8)
        return str(phash)
    except Exception as exc:
        logger.error("Perceptual hash computation failed: %s", exc)
        return "0" * 64


def preprocess_ela_image(content: bytes, quality: int = 75) -> Image.Image:
    """Build an ELA residual image from raw input bytes."""
    original = Image.open(io.BytesIO(content)).convert("RGB")

    tmp = io.BytesIO()
    original.save(tmp, format="JPEG", quality=quality)
    tmp.seek(0)
    recompressed = Image.open(tmp).convert("RGB")

    diff = ImageChops.difference(original, recompressed)
    ela = np.asarray(diff, dtype=np.float32)

    max_val = float(ela.max())
    if max_val > 0:
        ela = np.clip((ela * (255.0 / max_val)), 0, 255)

    return Image.fromarray(ela.astype(np.uint8), mode="RGB")


def preprocess_copy_move_image(content: bytes) -> Image.Image:
    """Create a keypoint heatmap image for copy-move training/inference."""
    import cv2

    arr = np.frombuffer(content, dtype=np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("Could not decode image bytes.")

    orb = cv2.ORB_create(nfeatures=1200)
    keypoints, descriptors = orb.detectAndCompute(gray, None)

    heatmap = Image.fromarray(gray).convert("RGB")
    draw = ImageDraw.Draw(heatmap)

    if descriptors is not None and keypoints:
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        matches = bf.knnMatch(descriptors, descriptors, k=2)

        for pair in matches:
            if len(pair) < 2:
                continue
            m, n = pair
            if m.queryIdx == m.trainIdx:
                continue
            if m.distance < 0.75 * n.distance:
                x, y = keypoints[m.queryIdx].pt
                # Draw local match intensity markers as CNN-friendly signal.
                draw.ellipse((x - 3, y - 3, x + 3, y + 3), outline=(255, 0, 0), width=1)

    return heatmap


def _load_image_paths(split_dir: Path) -> list[tuple[Path, int]]:
    """Return list of (path, label) where authentic=0 and forged=1."""
    authentic_dir = split_dir / "authentic"
    forged_dir = split_dir / "forged"

    if not authentic_dir.exists() or not forged_dir.exists():
        raise FileNotFoundError(
            f"Expected class folders missing in {split_dir}. "
            "Required: authentic/ and forged/."
        )

    items: list[tuple[Path, int]] = []

    for path in sorted(authentic_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            items.append((path, 0))

    for path in sorted(forged_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            items.append((path, 1))

    if not items:
        raise FileNotFoundError(f"No supported image files found under {split_dir}.")

    return items


class BinaryForgeryDataset(Dataset):
    def __init__(
        self,
        split_dir: Path,
        preprocessor: Preprocessor,
        augment: bool,
    ) -> None:
        self.samples = _load_image_paths(split_dir)
        self.preprocessor = preprocessor

        if augment:
            self.transform = transforms.Compose(
                [
                    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
                    transforms.RandomHorizontalFlip(p=0.5),
                    transforms.RandomRotation(degrees=6),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ]
            )
        else:
            self.transform = transforms.Compose(
                [
                    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ]
            )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        path, label = self.samples[idx]
        content = path.read_bytes()
        image = self.preprocessor(content)
        tensor = self.transform(image)
        return tensor, label


def build_backbone(backbone: str, num_classes: int = 2, pretrained: bool = False) -> nn.Module:
    """Build a torchvision backbone with a binary classification head."""
    if backbone == "resnet18":
        weights = models.ResNet18_Weights.DEFAULT if pretrained else None
        model = models.resnet18(weights=weights)
        in_features = model.fc.in_features
        model.fc = nn.Linear(in_features, num_classes)
        return model

    if backbone == "efficientnet_b0":
        weights = models.EfficientNet_B0_Weights.DEFAULT if pretrained else None
        model = models.efficientnet_b0(weights=weights)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, num_classes)
        return model

    raise ValueError(f"Unsupported backbone '{backbone}'.")


def resolve_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_checkpoint_model(checkpoint_path: Path, device: torch.device) -> tuple[nn.Module, dict]:
    checkpoint = torch.load(checkpoint_path, map_location=device)
    backbone = checkpoint.get("backbone", "resnet18")

    model = build_backbone(backbone=backbone, num_classes=2, pretrained=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()
    return model, checkpoint


def predict_forgery_probability(
    content: bytes,
    checkpoint_path: Path,
    preprocessor: Preprocessor,
    model_name: str,
) -> float:
    """Run binary model inference and return forged-class probability."""
    try:
        if not checkpoint_path.exists():
            logger.warning("[%s] Missing checkpoint: %s", model_name.upper(), checkpoint_path)
            return 0.5

        device = resolve_device()
        model, checkpoint = load_checkpoint_model(checkpoint_path, device)

        transform = transforms.Compose(
            [
                transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

        image = preprocessor(content)
        tensor = transform(image).unsqueeze(0).to(device)

        with torch.no_grad():
            logits = model(tensor)
            probs = torch.softmax(logits, dim=1)[0]

        label_to_index = checkpoint.get("label_to_index", {"authentic": 0, "forged": 1})
        forged_index = int(label_to_index.get("forged", 1))
        prob = float(probs[forged_index].item())
        logger.info("[%s] Forgery probability: %.4f", model_name.upper(), prob)
        return prob
    except Exception as exc:
        logger.error("[%s] Inference error: %s", model_name.upper(), exc)
        return 0.5

from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image, ImageChops


def _to_normalized_box(x: int, y: int, w: int, h: int, width: int, height: int, source: str, score: float) -> dict[str, Any]:
    return {
        "x": round(x / max(width, 1), 4),
        "y": round(y / max(height, 1), 4),
        "w": round(w / max(width, 1), 4),
        "h": round(h / max(height, 1), 4),
        "source": source,
        "score": round(float(score), 4),
    }


def _ela_boxes(content: bytes) -> list[dict[str, Any]]:
    import cv2

    original = Image.open(io.BytesIO(content)).convert("RGB")
    width, height = original.size

    buf = io.BytesIO()
    original.save(buf, format="JPEG", quality=75)
    buf.seek(0)
    recompressed = Image.open(buf).convert("RGB")

    diff = ImageChops.difference(original, recompressed)
    arr = np.asarray(diff, dtype=np.float32).mean(axis=2)

    if arr.max() <= 0:
        return []

    threshold = np.percentile(arr, 97)
    mask = (arr >= threshold).astype(np.uint8) * 255

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.dilate(mask, kernel, iterations=1)

    n_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    boxes: list[dict[str, Any]] = []
    min_area = max(32, int(0.0008 * width * height))

    for idx in range(1, n_labels):
        x, y, w, h, area = stats[idx]
        if area < min_area:
            continue
        local = arr[y : y + h, x : x + w]
        score = float(local.mean() / (arr.max() + 1e-6))
        boxes.append(_to_normalized_box(int(x), int(y), int(w), int(h), width, height, "ela", score))

    boxes.sort(key=lambda b: b["score"], reverse=True)
    return boxes[:5]


def _copy_move_boxes(content: bytes) -> list[dict[str, Any]]:
    import cv2

    arr = np.frombuffer(content, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return []

    height, width = img.shape[:2]
    orb = cv2.ORB_create(nfeatures=1200)
    keypoints, descriptors = orb.detectAndCompute(img, None)

    if descriptors is None or not keypoints:
        return []

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = bf.knnMatch(descriptors, descriptors, k=2)

    pts = []
    for pair in matches:
        if len(pair) < 2:
            continue
        m, n = pair
        if m.queryIdx == m.trainIdx:
            continue
        if m.distance < 0.75 * n.distance:
            p1 = np.array(keypoints[m.queryIdx].pt)
            p2 = np.array(keypoints[m.trainIdx].pt)
            if np.linalg.norm(p1 - p2) > 20:
                pts.append(p1)
                pts.append(p2)

    if len(pts) < 10:
        return []

    pts_arr = np.array(pts, dtype=np.float32)
    x, y, w, h = cv2.boundingRect(pts_arr)
    score = min(1.0, len(pts) / 300.0)

    return [_to_normalized_box(int(x), int(y), int(w), int(h), width, height, "copy_move", score)]


def localize_forgery_regions(content: bytes) -> list[dict[str, Any]]:
    """Return approximate forgery regions as normalized bounding boxes."""
    regions = []
    regions.extend(_ela_boxes(content))
    regions.extend(_copy_move_boxes(content))

    regions.sort(key=lambda b: b["score"], reverse=True)
    return regions[:6]

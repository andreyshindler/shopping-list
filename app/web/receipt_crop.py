"""Best-effort automatic cropping of an uploaded receipt photo.

A receipt is a bright region on a darker background. We threshold to that bright region,
close it into one blob (so a thin/angled strip stays connected), take the largest
contour's bounding rectangle, and crop to it — a plain rectangular crop, no perspective
correction. Everything is guarded: on any failure, or when detection isn't confident, the
original bytes are returned unchanged, so an upload is never broken or wrongly cropped.
"""

from __future__ import annotations

# Analysis is done on a downscaled copy for speed; the crop is applied to the full image.
_ANALYZE_MAX = 1000
# Cap the stored image's long side to keep the DB row small.
_OUTPUT_MAX = 2000
_JPEG_QUALITY = 85
_PADDING_FRAC = 0.02  # grow the detected box slightly so nothing is clipped

# Confidence gates: the detected box must be a plausible receipt, and cropping must
# actually remove a meaningful margin — otherwise keep the original.
_MIN_AREA_FRAC = 0.03
_MAX_AREA_FRAC = 0.92
_MIN_REDUCTION = 0.15  # cropped area must be <= 85% of the original


def process_receipt(data: bytes, mime: str) -> tuple[bytes, str]:
    """Return ``(cropped_jpeg, "image/jpeg")`` or the original ``(data, mime)`` unchanged.

    Never raises: any decode/processing error falls back to the original.
    """
    try:
        import cv2
        import numpy as np

        buf = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None:
            return data, mime

        rect = _detect_receipt_rect(img, cv2, np)
        if rect is None:
            return _encode(_fit(img, cv2), cv2), "image/jpeg"

        x, y, w, h = rect
        cropped = img[y : y + h, x : x + w]
        if cropped.size == 0:
            return data, mime
        return _encode(_fit(cropped, cv2), cv2), "image/jpeg"
    except Exception:
        return data, mime


def _detect_receipt_rect(img, cv2, np):
    """Bounding rectangle of the receipt in ``img`` (full-res coords), or None."""
    H, W = img.shape[:2]
    scale = min(1.0, _ANALYZE_MAX / max(H, W))
    small = cv2.resize(img, (max(1, int(W * scale)), max(1, int(H * scale)))) if scale < 1 else img
    sh, sw = small.shape[:2]

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    # Otsu picks the bright/dark split automatically; the receipt is the bright side.
    _thr, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Bridge text gaps / the thin angled strip into a single blob.
    k = max(3, int(round(min(sh, sw) * 0.03)) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest)

    img_area = float(sw * sh)
    box_area = float(w * h)
    frac = box_area / img_area
    if frac < _MIN_AREA_FRAC or frac > _MAX_AREA_FRAC:
        return None
    if frac > (1.0 - _MIN_REDUCTION):  # crop wouldn't remove enough to bother
        return None

    # Pad, clamp, and scale back up to full-resolution coordinates.
    pad = int(round(max(sw, sh) * _PADDING_FRAC))
    x = max(0, x - pad)
    y = max(0, y - pad)
    w = min(sw - x, w + 2 * pad)
    h = min(sh - y, h + 2 * pad)
    inv = 1.0 / scale if scale < 1 else 1.0
    return (int(x * inv), int(y * inv), int(w * inv), int(h * inv))


def _fit(img, cv2):
    """Downscale so the long side is at most ``_OUTPUT_MAX``."""
    h, w = img.shape[:2]
    long_side = max(h, w)
    if long_side <= _OUTPUT_MAX:
        return img
    s = _OUTPUT_MAX / long_side
    return cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)


def _encode(img, cv2) -> bytes:
    ok, out = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
    if not ok:
        raise ValueError("jpeg encode failed")
    return out.tobytes()

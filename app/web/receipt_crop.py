"""Best-effort automatic cropping of an uploaded receipt photo (Pillow-based).

A receipt is a bright region on a darker background. We threshold to that bright region,
take the bounding box of the bright pixels, and crop to it — a plain rectangular crop, no
perspective correction. Everything is guarded and memory-frugal (big JPEGs are decoded at a
reduced size via ``Image.draft``), so a huge phone photo can't hang or OOM the request. On
any failure, or when detection isn't confident, the (normalized) image is returned so an
upload is never broken.
"""

from __future__ import annotations

from io import BytesIO

# Analysis is done on a downscaled copy; the crop is applied to the (still downscaled) image.
_ANALYZE_MAX = 1000
_OUTPUT_MAX = 2000
_JPEG_QUALITY = 85
_PADDING_FRAC = 0.02
_BRIGHT_THRESHOLD = 220  # receipts are near-white; high enough to exclude a light floor/couch

# Confidence gates: the detected box must be a plausible receipt, and cropping must
# actually remove a meaningful margin — otherwise keep the whole (normalized) image.
_MIN_AREA_FRAC = 0.03
_MAX_AREA_FRAC = 0.92
_MIN_REDUCTION = 0.15  # cropped area must be <= 85% of the original


_heif_ready = False


def _register_heif() -> None:
    """Register the HEIF/HEIC opener with Pillow once (iPhone photos are HEIC).

    Best-effort: if pillow-heif isn't installed/usable, HEIC simply stays unsupported and
    such an upload is skipped rather than crashing.
    """
    global _heif_ready
    if _heif_ready:
        return
    _heif_ready = True
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except Exception:
        pass


def _sniff_mime(data: bytes) -> str:
    """Best-effort image mime from magic bytes (used only when Pillow is unavailable)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def process_receipt(data: bytes) -> tuple[bytes, str] | None:
    """Crop/normalize a receipt photo.

    Returns ``(jpeg_bytes, "image/jpeg")`` on success, or ``None`` when the bytes aren't a
    decodable image (so the caller stores nothing). Never raises. If Pillow is unavailable
    the bytes are passed through with a sniffed mime (best effort, no crop).
    """
    if not data:
        return None
    try:
        from PIL import Image, ImageOps
    except Exception:
        return data, _sniff_mime(data)

    _register_heif()  # let Pillow open iPhone HEIC/HEIF photos (best-effort)

    # Decode (forced via convert) — this is what tells us whether it's really an image.
    try:
        img = Image.open(BytesIO(data))
        img.draft("RGB", (_OUTPUT_MAX, _OUTPUT_MAX))  # big JPEGs decode at reduced size
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        return None  # not a decodable image -> caller stores nothing

    # Crop + re-encode. If anything here fails, fall back to the original bytes.
    try:
        box = _detect_receipt_box(img, Image)
        if box is not None:
            img = img.crop(box)
        img.thumbnail((_OUTPUT_MAX, _OUTPUT_MAX))
        out = BytesIO()
        img.save(out, format="JPEG", quality=_JPEG_QUALITY)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return data, _sniff_mime(data)


def _detect_receipt_box(img, Image):
    """Bounding box ``(l, t, r, b)`` of the receipt in full-image coords, or None."""
    W, H = img.size
    small = img.copy()
    small.thumbnail((_ANALYZE_MAX, _ANALYZE_MAX))
    sw, sh = small.size

    mask = small.convert("L").point(lambda p: 255 if p > _BRIGHT_THRESHOLD else 0)
    bbox = mask.getbbox()  # (l, t, r, b) of non-zero (bright) pixels, or None
    if bbox is None:
        return None

    l, t, r, b = bbox
    area_frac = ((r - l) * (b - t)) / float(sw * sh)
    if area_frac < _MIN_AREA_FRAC or area_frac > (1.0 - _MIN_REDUCTION):
        return None  # too small, or wouldn't remove enough to bother
    if area_frac > _MAX_AREA_FRAC:
        return None

    pad = int(round(max(sw, sh) * _PADDING_FRAC))
    l = max(0, l - pad)
    t = max(0, t - pad)
    r = min(sw, r + pad)
    b = min(sh, b + pad)

    # Map back to full-resolution coordinates.
    fx, fy = W / sw, H / sh
    return (int(l * fx), int(t * fy), int(r * fx), int(b * fy))

"""Best-effort automatic cropping of an uploaded receipt photo (Pillow-based).

A receipt is a bright region on a darker background. We pick an adaptive brightness
threshold per photo (Otsu), then find the longest contiguous run of rows and of columns
that are *mostly* bright — the receipt — and crop to that rectangle (no perspective
correction). Working from bright *fractions* per row/column, and taking the longest run,
ignores sparse specks and separate bright blobs (a floor tile, a hand). Everything is
guarded and memory-frugal (big JPEGs are decoded at a reduced size via ``Image.draft``),
so a huge phone photo can't hang or OOM the request. On any failure, or when detection
isn't confident, the (normalized) image is returned so an upload is never broken.
"""

from __future__ import annotations

from io import BytesIO

# Analysis is done on a downscaled copy; the crop is applied to the full (normalized) image.
_ANALYZE_MAX = 600
_OUTPUT_MAX = 2000
_JPEG_QUALITY = 85
_PADDING_FRAC = 0.02
# A row/column counts as "receipt" when at least this fraction of its pixels are bright
# (above the adaptive Otsu threshold). Using a fraction — not any single bright pixel —
# ignores sparse specks (a hand, a floor tile) that would otherwise inflate the box.
_LINE_FRAC = 0.12
_MIN_DESKEW_DEG = 3  # don't bother rotating for a nearly-straight receipt

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

    # Deskew (straighten a tilted receipt) then crop + re-encode. If anything here fails,
    # fall back to the original bytes.
    try:
        angle = _deskew_angle(img, Image)
        if abs(angle) >= _MIN_DESKEW_DEG:
            # Black fill so the added corners read as background to the re-detection below.
            img = img.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0))
        box = _detect_receipt_box(img, Image)
        if box is not None:
            img = img.crop(box)
        img.thumbnail((_OUTPUT_MAX, _OUTPUT_MAX))
        out = BytesIO()
        img.save(out, format="JPEG", quality=_JPEG_QUALITY)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return data, _sniff_mime(data)


def _otsu_threshold(gray) -> int:
    """Otsu's method: the grayscale value that best splits dark bg from bright receipt.

    Adaptive per-photo (unlike a fixed threshold), so it works in bright or dim lighting.
    """
    hist = gray.histogram()[:256]
    total = sum(hist)
    if total == 0:
        return 127
    sum_all = sum(i * hist[i] for i in range(256))
    w_b = 0
    sum_b = 0
    best_var = -1.0
    thr = 127
    for i in range(256):
        w_b += hist[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * hist[i]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
        if between > best_var:
            best_var = between
            thr = i
    return thr


def _longest_run(values, cutoff, max_gap):
    """Longest run of consecutive indices with value > cutoff (inclusive), or None.

    Small dips (gaps up to ``max_gap``, e.g. blank bands on the receipt) don't break a run,
    but a large low stretch does — so a separate bright blob (a floor tile, a hand) forms
    its own shorter run and loses to the receipt's.
    """
    best = None
    best_len = 0
    start = last = None
    for i, v in enumerate(values):
        if v > cutoff:
            if start is None:
                start = i
            last = i
        elif start is not None and (i - last) > max_gap:
            if last - start + 1 > best_len:
                best_len = last - start + 1
                best = (start, last)
            start = last = None
    if start is not None and last - start + 1 > best_len:
        best = (start, last)
    return best


def _receipt_mask(img, Image):
    """Downscaled Otsu bright mask of ``img``; returns (mask, small_w, small_h)."""
    small = img.copy()
    small.thumbnail((_ANALYZE_MAX, _ANALYZE_MAX))
    sw, sh = small.size
    gray = small.convert("L")
    thr = _otsu_threshold(gray)
    return gray.point(lambda p: 255 if p > thr else 0), sw, sh


def _rough_span(mask, sw, sh, Image):
    """Receipt box (l, t, r, b) in mask coords via per-row/column bright-fraction runs."""
    rows = list(mask.resize((1, sh), Image.BOX).getdata())
    cols = list(mask.resize((sw, 1), Image.BOX).getdata())
    cutoff = _LINE_FRAC * 255
    vspan = _longest_run(rows, cutoff, max(2, int(sh * 0.03)))
    hspan = _longest_run(cols, cutoff, max(2, int(sw * 0.03)))
    if vspan is None or hspan is None:
        return None
    return (hspan[0], vspan[0], hspan[1] + 1, vspan[1] + 1)


def _detect_receipt_box(img, Image):
    """Bounding box ``(l, t, r, b)`` of the receipt in full-image coords, or None.

    Adaptive threshold (Otsu) → bright mask → per-row/column bright-fraction projection →
    the longest run of rows/columns that are mostly receipt. Ignores sparse specks.
    """
    W, H = img.size
    mask, sw, sh = _receipt_mask(img, Image)
    span = _rough_span(mask, sw, sh, Image)
    if span is None:
        return None
    l, t, r, b = span

    area_frac = ((r - l) * (b - t)) / float(sw * sh)
    if area_frac < _MIN_AREA_FRAC or area_frac > _MAX_AREA_FRAC:
        return None
    if area_frac > (1.0 - _MIN_REDUCTION):
        return None  # wouldn't remove enough to bother

    pad = int(round(max(sw, sh) * _PADDING_FRAC))
    l = max(0, l - pad)
    t = max(0, t - pad)
    r = min(sw, r + pad)
    b = min(sh, b + pad)

    fx, fy = W / sw, H / sh
    return (int(l * fx), int(t * fy), int(r * fx), int(b * fy))


def _deskew_angle(img, Image):
    """Degrees to rotate ``img`` (as ``Image.rotate``) so the receipt becomes upright, or 0.

    Brute-force minimum-area rectangle: rotate the (rough-cropped) bright mask through a
    range of angles and keep the one whose bright bounding box is smallest — that's when the
    receipt's edges line up with the axes. Self-consistent (we apply the same rotation we
    searched), so there's no sign ambiguity.
    """
    mask, sw, sh = _receipt_mask(img, Image)
    span = _rough_span(mask, sw, sh, Image)
    if span is None:
        return 0.0
    mr = mask.crop(span)
    if mr.width < 12 or mr.height < 12:
        return 0.0

    def area_at(a):
        r = mr.rotate(a, expand=True, resample=Image.NEAREST, fillcolor=0) if a else mr
        bb = r.getbbox()
        return None if bb is None else (bb[2] - bb[0]) * (bb[3] - bb[1])

    best_a = 0.0
    best_area = area_at(0.0)
    for a in range(-45, 46, 5):
        ar = area_at(a)
        if ar is not None and (best_area is None or ar < best_area):
            best_area, best_a = ar, float(a)
    for a in (best_a + d for d in (-4, -3, -2, -1, 1, 2, 3, 4)):
        ar = area_at(a)
        if ar is not None and (best_area is None or ar < best_area):
            best_area, best_a = ar, a
    return best_a

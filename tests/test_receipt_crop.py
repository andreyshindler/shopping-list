from io import BytesIO

from PIL import Image, ImageDraw

from app.web.receipt_crop import process_receipt


def _png(img: Image.Image) -> bytes:
    b = BytesIO()
    img.save(b, format="PNG")
    return b.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data))


def test_crops_bright_rectangle_on_dark_background():
    W, H = 600, 800
    img = Image.new("RGB", (W, H), (20, 20, 20))  # dark background
    ImageDraw.Draw(img).rectangle([220, 150, 380, 620], fill=(245, 245, 245))  # bright strip

    out, mime = process_receipt(_png(img))
    assert mime == "image/jpeg"

    crop = _open(out)
    cw, ch = crop.size
    assert cw < W and ch < H  # actually cropped
    assert abs(cw - (380 - 220)) < 90  # ~ the rectangle (plus a little padding)
    assert abs(ch - (620 - 150)) < 90


def test_heic_iphone_photo_is_decoded():
    # iPhone camera photos are HEIC; they must be decoded (not dropped) and re-encoded.
    import pillow_heif

    buf = BytesIO()
    img = Image.new("RGB", (400, 600), (20, 20, 20))
    ImageDraw.Draw(img).rectangle([120, 100, 280, 500], fill=(240, 240, 240))
    pillow_heif.from_pillow(img).save(buf, quality=80)

    result = process_receipt(buf.getvalue())
    assert result is not None  # not dropped
    out, mime = result
    assert mime == "image/jpeg"
    assert _open(out).size[0] > 0


def test_undecodable_bytes_return_none():
    assert process_receipt(b"\x89PNG\r\n\x1a\n definitely not an image") is None
    assert process_receipt(b"") is None


def test_full_frame_bright_not_overcropped():
    # Whole frame bright -> box ~ whole image -> gate rejects -> dimensions preserved.
    img = Image.new("RGB", (500, 500), (240, 240, 240))
    out, _mime = process_receipt(_png(img))
    assert _open(out).size == (500, 500)

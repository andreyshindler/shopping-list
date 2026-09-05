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


def test_deskews_a_tilted_receipt():
    # A long bright receipt rotated 22° on a dark background: the result should be
    # straightened (upright/portrait) and tightly cropped, not a loose diagonal box.
    base = Image.new("RGB", (900, 1200), (60, 60, 63))
    receipt = Image.new("RGB", (230, 760), (240, 240, 238))
    rd = ImageDraw.Draw(receipt)
    for y in range(20, 760, 26):
        rd.line([(20, y), (210, y)], fill=(60, 60, 60), width=2)
    base.paste(receipt.rotate(22, expand=True, fillcolor=(60, 60, 63)), (330, 210))

    out, mime = process_receipt(_png(base))
    assert mime == "image/jpeg"
    w, h = _open(out).size
    assert h > w              # upright
    assert h / w > 2.0        # long & narrow like the receipt (~3.3)
    assert w * h < 900 * 1200 * 0.35  # tight — background corners removed


def test_undecodable_bytes_return_none():
    assert process_receipt(b"\x89PNG\r\n\x1a\n definitely not an image") is None
    assert process_receipt(b"") is None


def test_full_frame_bright_not_overcropped():
    # Whole frame bright -> box ~ whole image -> gate rejects -> dimensions preserved.
    img = Image.new("RGB", (500, 500), (240, 240, 240))
    out, _mime = process_receipt(_png(img))
    assert _open(out).size == (500, 500)

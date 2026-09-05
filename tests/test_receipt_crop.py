import cv2
import numpy as np

from app.web.receipt_crop import process_receipt


def _png(img) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _decode(data: bytes):
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def test_crops_bright_rectangle_on_dark_background():
    H, W = 800, 600
    img = np.full((H, W, 3), 20, np.uint8)  # dark background
    y0, y1, x0, x1 = 150, 620, 220, 380  # bright "receipt" (470 x 160)
    img[y0:y1, x0:x1] = 245

    out, mime = process_receipt(_png(img), "image/png")
    assert mime == "image/jpeg"

    crop = _decode(out)
    ch, cw = crop.shape[:2]
    assert ch < H and cw < W  # actually cropped
    # Close to the rectangle (plus a little padding).
    assert abs(ch - (y1 - y0)) < 80
    assert abs(cw - (x1 - x0)) < 80


def test_garbage_bytes_returned_unchanged():
    data = b"\x89PNG\r\n\x1a\n definitely not an image"
    assert process_receipt(data, "image/png") == (data, "image/png")


def test_full_frame_bright_not_overcropped():
    # Almost the whole frame is bright -> box ~ whole image -> confidence gate rejects it,
    # so the image keeps its dimensions (just re-encoded).
    img = np.full((500, 500, 3), 240, np.uint8)
    out, _mime = process_receipt(_png(img), "image/png")
    crop = _decode(out)
    assert crop.shape[0] == 500 and crop.shape[1] == 500

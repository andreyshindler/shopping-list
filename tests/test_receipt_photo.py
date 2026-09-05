from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.models import Base, ShoppingList
from app.services import create_list_from_text, get_or_create_user
from app.web.main import app


def _image_bytes() -> bytes:
    """A small but real PNG (decodable by the server's image pipeline)."""
    buf = BytesIO()
    Image.new("RGB", (40, 60), (210, 210, 210)).save(buf, format="PNG")
    return buf.getvalue()


IMG = _image_bytes()


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_session():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app, follow_redirects=False) as c:
        c.session_factory = TestSession
        yield c
    app.dependency_overrides.clear()


def _seed(client):
    with client.session_factory() as s:
        user = get_or_create_user(s, 42, "T", "ILS")
        sl = create_list_from_text(s, user, "milk\nbread")
        s.commit()
        return sl.web_token


def _get_receipt(client, token):
    return client.get(f"/list/{token}/receipt")


def test_complete_with_receipt_stores_and_serves(client):
    token = _seed(client)
    r = client.post(
        f"/api/lists/{token}/complete",
        data={"real_total": "50"},
        files={"receipt": ("receipt.png", IMG, "image/png")},
    )
    assert r.status_code == 303

    got = _get_receipt(client, token)
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("image/")
    assert len(got.content) > 0

    with client.session_factory() as s:
        sl = s.query(ShoppingList).filter_by(web_token=token).one()
        assert sl.status == "completed"
        assert sl.real_total == 50.0
        assert sl.has_receipt


def test_octet_stream_content_type_is_accepted(client):
    # Mobile/Telegram webviews often send camera photos as application/octet-stream.
    # It must still be stored (validated by decoding, not by the declared content type).
    token = _seed(client)
    client.post(f"/api/lists/{token}/complete", data={"real_total": "10"})
    r = client.post(
        f"/api/lists/{token}/receipt",
        files={"receipt": ("photo", IMG, "application/octet-stream")},
    )
    assert r.status_code == 303
    assert _get_receipt(client, token).status_code == 200


def test_complete_without_receipt_leaves_none(client):
    token = _seed(client)
    r = client.post(f"/api/lists/{token}/complete", data={"real_total": "20"})
    assert r.status_code == 303
    assert _get_receipt(client, token).status_code == 404


def test_update_total_after_completion(client):
    token = _seed(client)
    client.post(f"/api/lists/{token}/complete", data={"real_total": "20"})
    r = client.post(f"/api/lists/{token}/receipt", data={"real_total": "37.5"})
    assert r.status_code == 303
    with client.session_factory() as s:
        sl = s.query(ShoppingList).filter_by(web_token=token).one()
        assert sl.real_total == 37.5


def test_update_total_and_photo_together(client):
    token = _seed(client)
    client.post(f"/api/lists/{token}/complete", data={"real_total": "20"})
    r = client.post(
        f"/api/lists/{token}/receipt",
        data={"real_total": "88.25"},
        files={"receipt": ("photo", IMG, "application/octet-stream")},
    )
    assert r.status_code == 303
    with client.session_factory() as s:
        sl = s.query(ShoppingList).filter_by(web_token=token).one()
        assert sl.real_total == 88.25
        assert sl.has_receipt


def test_two_inputs_picks_the_filled_one(client):
    token = _seed(client)
    r = client.post(
        f"/api/lists/{token}/receipt",
        files=[
            ("receipt", ("", b"", "application/octet-stream")),  # empty camera input
            ("receipt", ("r.png", IMG, "image/png")),           # chosen file
        ],
    )
    assert r.status_code == 303
    assert _get_receipt(client, token).status_code == 200


def test_non_image_is_ignored_not_fatal(client):
    # A non-image upload must not error the request; it's simply not stored.
    token = _seed(client)
    r = client.post(
        f"/api/lists/{token}/receipt",
        files={"receipt": ("note.txt", b"not an image at all", "text/plain")},
    )
    assert r.status_code == 303
    assert _get_receipt(client, token).status_code == 404

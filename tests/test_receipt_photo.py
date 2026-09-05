import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.models import Base, ShoppingList
from app.services import create_list_from_text, get_or_create_user
from app.web.main import app

# Bytes that start with the PNG signature. Content is never image-validated (only the
# content type and size are checked), so this is enough to exercise store + serve.
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(32)) * 4


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


def test_complete_with_receipt_stores_and_serves(client):
    token = _seed(client)
    r = client.post(
        f"/api/lists/{token}/complete",
        data={"real_total": "50"},
        files={"receipt": ("receipt.png", PNG, "image/png")},
    )
    assert r.status_code == 303

    got = client.get(f"/list/{token}/receipt")
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("image/png")
    assert got.content == PNG

    with client.session_factory() as s:
        sl = s.query(ShoppingList).filter_by(web_token=token).one()
        assert sl.status == "completed"
        assert sl.real_total == 50.0
        assert sl.has_receipt


def test_complete_without_receipt_leaves_none(client):
    token = _seed(client)
    r = client.post(f"/api/lists/{token}/complete", data={"real_total": "20"})
    assert r.status_code == 303
    assert client.get(f"/list/{token}/receipt").status_code == 404


def test_upload_receipt_after_completion(client):
    token = _seed(client)
    client.post(f"/api/lists/{token}/complete", data={"real_total": "20"})
    assert client.get(f"/list/{token}/receipt").status_code == 404

    r = client.post(
        f"/api/lists/{token}/receipt",
        files={"receipt": ("r.png", PNG, "image/png")},
    )
    assert r.status_code == 303
    assert client.get(f"/list/{token}/receipt").content == PNG


def test_two_inputs_picks_the_filled_one(client):
    # The page sends two "receipt" fields (take-photo + choose-file); only one is
    # filled. The server must pick whichever carries a file.
    token = _seed(client)
    r = client.post(
        f"/api/lists/{token}/receipt",
        files=[
            ("receipt", ("", b"", "application/octet-stream")),  # empty camera input
            ("receipt", ("r.png", PNG, "image/png")),           # chosen file
        ],
    )
    assert r.status_code == 303
    assert client.get(f"/list/{token}/receipt").content == PNG


def test_update_total_after_completion(client):
    token = _seed(client)
    client.post(f"/api/lists/{token}/complete", data={"real_total": "20"})
    # Correct the total on the completed list (no receipt attached).
    r = client.post(f"/api/lists/{token}/receipt", data={"real_total": "37.5"})
    assert r.status_code == 303
    with client.session_factory() as s:
        sl = s.query(ShoppingList).filter_by(web_token=token).one()
        assert sl.real_total == 37.5


def test_reject_non_image(client):
    token = _seed(client)
    r = client.post(
        f"/api/lists/{token}/receipt",
        files={"receipt": ("note.txt", b"not an image", "text/plain")},
    )
    assert r.status_code == 400
    assert client.get(f"/list/{token}/receipt").status_code == 404

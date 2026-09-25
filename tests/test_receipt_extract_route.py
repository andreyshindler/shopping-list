from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.models import Base, Item, PriceHistory, ShoppingList
from app.receipts import ReceiptData, ReceiptItem, ReceiptParseError
from app.services import create_list_from_text, get_or_create_user
from app.web import routes as routes_module
from app.web.main import app


def _image_bytes() -> bytes:
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


def _seed_with_receipt(client, text="milk\nbread"):
    with client.session_factory() as s:
        user = get_or_create_user(s, 42, "T", "ILS")
        sl = create_list_from_text(s, user, text)
        s.commit()
        token = sl.web_token
    client.post(
        f"/api/lists/{token}/complete",
        data={"real_total": "10"},
        files={"receipt": ("r.png", IMG, "image/png")},
    )
    return token


def test_no_receipt_redirects_without_calling_parse(client, monkeypatch):
    with client.session_factory() as s:
        user = get_or_create_user(s, 1, "T", "ILS")
        sl = create_list_from_text(s, user, "milk")
        s.commit()
        token = sl.web_token

    called = []
    monkeypatch.setattr(routes_module, "parse_receipt", lambda *a, **k: called.append(1))
    r = client.post(f"/api/lists/{token}/receipt/extract")
    assert r.status_code == 303
    assert not called


class _Cfg:
    def __init__(self, api_key="", model="claude-haiku-4-5-20251001"):
        self.anthropic_api_key = api_key
        self.anthropic_model = model


def test_unconfigured_api_key_redirects_unavailable(client, monkeypatch):
    token = _seed_with_receipt(client)

    def _raise(*a, **k):
        raise ReceiptParseError("receipt scanning is not configured")

    monkeypatch.setattr(routes_module, "parse_receipt", _raise)
    monkeypatch.setattr(routes_module, "_get_settings", lambda: _Cfg(api_key=""))
    r = client.post(f"/api/lists/{token}/receipt/extract")
    assert r.status_code == 303
    assert "receipt_extract=unavailable" in r.headers["location"]


def test_successful_extract_fills_prices_and_redirects_ok(client, monkeypatch):
    token = _seed_with_receipt(client, "milk\nbread")

    def _fake_parse(image_bytes, *, api_key, model, mime_type):
        return ReceiptData(items=[
            ReceiptItem(name="milk", quantity=1, price=7.5),
            ReceiptItem(name="bread", quantity=1, price=6.0),
        ])

    monkeypatch.setattr(routes_module, "parse_receipt", _fake_parse)
    r = client.post(f"/api/lists/{token}/receipt/extract")
    assert r.status_code == 303
    loc = r.headers["location"]
    assert "receipt_extract=ok" in loc
    assert "matched=2" in loc
    assert "unmatched=0" in loc

    with client.session_factory() as s:
        sl = s.query(ShoppingList).filter_by(web_token=token).one()
        prices = {i.raw_name: i.real_price for i in sl.items}
        assert prices == {"milk": 7.5, "bread": 6.0}
        assert s.query(PriceHistory).count() == 2

    # the flash notice actually renders on the list page
    page = client.get(f"/list/{token}", params={"receipt_extract": "ok", "matched": 2, "unmatched": 0})
    assert page.status_code == 200
    assert "2" in page.text


def test_extract_with_unmatched_line_reports_it(client, monkeypatch):
    token = _seed_with_receipt(client, "milk")

    def _fake_parse(image_bytes, *, api_key, model, mime_type):
        return ReceiptData(items=[
            ReceiptItem(name="milk", quantity=1, price=7.5),
            ReceiptItem(name="chocolate", quantity=1, price=12.0),
        ])

    monkeypatch.setattr(routes_module, "parse_receipt", _fake_parse)
    r = client.post(f"/api/lists/{token}/receipt/extract")
    loc = r.headers["location"]
    assert "matched=1" in loc
    assert "unmatched=1" in loc

    with client.session_factory() as s:
        # unmatched receipt line is reported, not added as a new Item
        assert s.query(Item).count() == 1


def test_parse_error_redirects_failed_when_key_present(client, monkeypatch):
    token = _seed_with_receipt(client)

    def _raise(*a, **k):
        raise ReceiptParseError("model returned invalid JSON")

    monkeypatch.setattr(routes_module, "parse_receipt", _raise)
    monkeypatch.setattr(routes_module, "_get_settings", lambda: _Cfg(api_key="sk-test"))
    r = client.post(f"/api/lists/{token}/receipt/extract")
    assert "receipt_extract=failed" in r.headers["location"]


def test_empty_receipt_redirects_empty(client, monkeypatch):
    token = _seed_with_receipt(client)
    monkeypatch.setattr(
        routes_module, "parse_receipt", lambda *a, **k: ReceiptData(items=[])
    )
    r = client.post(f"/api/lists/{token}/receipt/extract")
    assert "receipt_extract=empty" in r.headers["location"]

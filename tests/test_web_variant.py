import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.models import Base, GlobalProduct
from app.services import create_list_from_text, get_or_create_user
from app.web.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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
    # Follow_redirects off so we can assert the 303 back to the list.
    with TestClient(app, follow_redirects=False) as c:
        c.session_factory = TestSession
        yield c
    app.dependency_overrides.clear()


def _seed_list(client):
    with client.session_factory() as s:
        s.add_all(
            [
                GlobalProduct(name="פלפל אדום", normalized_name="פלפל אדום", price=10.0),
                GlobalProduct(name="פלפל צהוב", normalized_name="פלפל צהוב", price=14.0),
            ]
        )
        user = get_or_create_user(s, 9, "T", "ILS")
        sl = create_list_from_text(s, user, "פלפל")
        s.commit()
        item = sl.items[0]
        return sl.web_token, item.id, [sug.id for sug in item.suggestions]


def test_choose_variant_resolves_item(client):
    token, item_id, suggestion_ids = _seed_list(client)

    res = client.post(
        f"/api/items/{item_id}/choose-variant",
        data={"suggestion_id": suggestion_ids[0]},
    )
    assert res.status_code == 303
    assert res.headers["location"] == f"/list/{token}"

    # The list page no longer shows the picker for that item.
    page = client.get(f"/list/{token}")
    assert "needs-choice" not in page.text


def test_choose_variant_unknown_item_404(client):
    _seed_list(client)
    res = client.post("/api/items/9999/choose-variant", data={"suggestion_id": 1})
    assert res.status_code == 404

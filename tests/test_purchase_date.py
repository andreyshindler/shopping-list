from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.models import Base, PriceHistory, ShoppingList
from app.services import create_list_from_text, get_or_create_user
from app.web.main import app


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


def _seed(client, text="milk"):
    with client.session_factory() as s:
        user = get_or_create_user(s, 1, "T", "ILS")
        sl = create_list_from_text(s, user, text)
        s.commit()
        return sl.web_token, sl.items[0].id


def test_complete_with_purchased_on_backdates_trip_and_history(client):
    token, item_id = _seed(client)
    r = client.post(
        f"/api/lists/{token}/complete",
        data={"real_total": "7.5", f"price_{item_id}": "7.5", "purchased_on": "2026-09-29"},
    )
    assert r.status_code == 303
    with client.session_factory() as s:
        sl = s.query(ShoppingList).filter_by(web_token=token).one()
        assert sl.completed_at.date() == date(2026, 9, 29)
        history = s.query(PriceHistory).one()
        assert history.recorded_at.date() == date(2026, 9, 29)


def test_complete_without_purchased_on_defaults_to_today(client):
    token, item_id = _seed(client)
    r = client.post(
        f"/api/lists/{token}/complete",
        data={"real_total": "7.5", f"price_{item_id}": "7.5"},
    )
    assert r.status_code == 303
    with client.session_factory() as s:
        sl = s.query(ShoppingList).filter_by(web_token=token).one()
        assert sl.completed_at.date() == date.today()


def test_complete_with_invalid_purchased_on_falls_back_to_today(client):
    token, item_id = _seed(client)
    r = client.post(
        f"/api/lists/{token}/complete",
        data={"real_total": "7.5", f"price_{item_id}": "7.5", "purchased_on": "not-a-date"},
    )
    assert r.status_code == 303
    with client.session_factory() as s:
        sl = s.query(ShoppingList).filter_by(web_token=token).one()
        assert sl.completed_at.date() == date.today()


def test_post_completion_edit_corrects_the_date(client):
    token, item_id = _seed(client)
    client.post(
        f"/api/lists/{token}/complete",
        data={"real_total": "7.5", f"price_{item_id}": "7.5"},
    )
    r = client.post(f"/api/lists/{token}/receipt", data={"purchased_on": "2026-09-29"})
    assert r.status_code == 303
    with client.session_factory() as s:
        sl = s.query(ShoppingList).filter_by(web_token=token).one()
        assert sl.completed_at.date() == date(2026, 9, 29)
        # real_total wasn't resent -> stays as it was, confirming the date-only edit
        # doesn't clobber other fields.
        assert sl.real_total == 7.5
        # the post-completion route never writes PriceHistory, so correcting the date
        # here does not touch the row already written at completion time.
        history = s.query(PriceHistory).one()
        assert history.recorded_at.date() == date.today()


def test_post_completion_edit_without_date_leaves_it_unchanged(client):
    token, item_id = _seed(client)
    client.post(
        f"/api/lists/{token}/complete",
        data={"real_total": "7.5", f"price_{item_id}": "7.5", "purchased_on": "2026-09-29"},
    )
    client.post(f"/api/lists/{token}/receipt", data={"real_total": "9.0"})
    with client.session_factory() as s:
        sl = s.query(ShoppingList).filter_by(web_token=token).one()
        assert sl.completed_at.date() == date(2026, 9, 29)
        assert sl.real_total == 9.0

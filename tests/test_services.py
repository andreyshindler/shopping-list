import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.services import (
    complete_list,
    create_list_from_text,
    get_or_create_user,
    list_totals,
    toggle_item,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_create_list_categorizes_and_no_prices_first_time(session):
    user = get_or_create_user(session, 111, "Test", "USD")
    sl = create_list_from_text(session, user, "2 milk\nbread\ntomatoes x3")
    assert sl is not None
    assert len(sl.items) == 3
    cats = {i.raw_name: i.category for i in sl.items}
    assert cats["milk"] == "Dairy & Eggs"
    assert cats["bread"] == "Bakery"
    assert cats["tomatoes"] == "Produce"
    # No purchase history yet -> no predicted prices.
    assert all(i.predicted_price is None for i in sl.items)
    assert sl.predicted_total == 0.0


def test_create_list_empty_returns_none(session):
    user = get_or_create_user(session, 111, "Test", "USD")
    assert create_list_from_text(session, user, "   \n\n") is None


def test_complete_feeds_predictions_for_next_list(session):
    user = get_or_create_user(session, 222, "Test", "USD")
    sl1 = create_list_from_text(session, user, "milk\nbread")
    for item in sl1.items:
        toggle_item(session, item)
    prices = {i.id: 3.0 for i in sl1.items}
    complete_list(session, sl1, real_total=6.0, item_prices=prices)
    session.flush()

    assert sl1.status == "completed"
    assert sl1.real_total == 6.0

    # A new list with the same items should now carry learned predictions.
    sl2 = create_list_from_text(session, user, "milk\nbread")
    assert all(i.predicted_price == 3.0 for i in sl2.items)
    assert sl2.predicted_total == 6.0


def test_list_totals_tracks_bought(session):
    user = get_or_create_user(session, 333, "Test", "USD")
    sl = create_list_from_text(session, user, "milk\nbread\neggs")
    toggle_item(session, sl.items[0])
    totals = list_totals(sl)
    assert totals["bought_count"] == 1
    assert totals["total_count"] == 3


def test_get_or_create_user_is_idempotent(session):
    u1 = get_or_create_user(session, 444, "Name", "USD")
    session.flush()
    u2 = get_or_create_user(session, 444, "Name", "USD")
    assert u1.id == u2.id

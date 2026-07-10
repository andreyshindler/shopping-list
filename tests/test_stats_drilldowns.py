from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, PriceHistory
from app.services import create_list_from_text, get_or_create_user
from app.stats import (
    get_category_spend,
    get_item_history,
    get_top_trips,
    get_trips,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _completed(session, user, when, real_total, items="milk\nbread"):
    sl = create_list_from_text(session, user, items)
    session.flush()
    for item in sl.items:
        item.is_bought = True
    sl.status = "completed"
    sl.completed_at = when
    sl.real_total = real_total
    session.flush()
    return sl


def test_get_trips_year_filter(session):
    u = get_or_create_user(session, 1, "T", "ILS")
    _completed(session, u, datetime(2026, 6, 10, tzinfo=timezone.utc), 50.0)
    _completed(session, u, datetime(2025, 12, 5, tzinfo=timezone.utc), 20.0)

    y2026 = get_trips(session, u.id, year="2026")
    assert [(g.year, g.month) for g in y2026] == [(2026, 6)]
    assert y2026[0].trips[0].real_total == 50.0


def test_get_top_trips_sorted_by_paid(session):
    u = get_or_create_user(session, 2, "T", "ILS")
    _completed(session, u, datetime(2026, 6, 10, tzinfo=timezone.utc), 30.0)
    _completed(session, u, datetime(2026, 6, 20, tzinfo=timezone.utc), 90.0)
    _completed(session, u, datetime(2026, 5, 5, tzinfo=timezone.utc), 60.0)

    top = get_top_trips(session, u.id)
    assert [t.real_total for t in top] == [90.0, 60.0, 30.0]
    assert get_top_trips(session, u.id, limit=2) == top[:2]


def test_category_spend_uses_predicted_fallback_and_sorts(session):
    u = get_or_create_user(session, 3, "T", "ILS")
    sl = _completed(session, u, datetime(2026, 6, 1, tzinfo=timezone.utc), 0.0, "milk\napple")
    by_name = {i.normalized_name: i for i in sl.items}
    milk = by_name["milk"]
    apple = by_name["apple"]
    # milk: explicit real price; apple: no real price -> predicted * quantity fallback.
    milk.real_price = 10.0
    apple.real_price = None
    apple.predicted_price = 4.0
    apple.quantity = 2.0
    session.flush()

    rows = get_category_spend(session, u.id)
    spend = {r.category: r.total for r in rows}
    assert spend[milk.category] == 10.0
    assert spend[apple.category] == 8.0  # 4.0 * 2
    # Sorted biggest first.
    assert [r.total for r in rows] == sorted((r.total for r in rows), reverse=True)


def test_item_history_orders_points_and_counts(session):
    u = get_or_create_user(session, 4, "T", "ILS")
    _completed(session, u, datetime(2026, 6, 1, tzinfo=timezone.utc), 10.0, "milk")
    _completed(session, u, datetime(2026, 6, 20, tzinfo=timezone.utc), 10.0, "milk")
    session.add_all(
        [
            PriceHistory(user_id=u.id, normalized_name="milk", price=6.0,
                         recorded_at=datetime(2026, 6, 1, tzinfo=timezone.utc)),
            PriceHistory(user_id=u.id, normalized_name="milk", price=5.0,
                         recorded_at=datetime(2026, 5, 1, tzinfo=timezone.utc)),
            PriceHistory(user_id=u.id, normalized_name="milk", price=7.0,
                         recorded_at=datetime(2026, 6, 20, tzinfo=timezone.utc)),
        ]
    )
    session.flush()

    hist = get_item_history(session, u.id, "milk")
    assert [p.price for p in hist.points] == [5.0, 6.0, 7.0]  # ordered by recorded_at
    assert hist.latest_price == 7.0
    assert hist.lowest_price == 5.0
    assert hist.highest_price == 7.0
    assert hist.times_bought == 2  # two bought "milk" item rows


def test_item_history_empty(session):
    u = get_or_create_user(session, 5, "T", "ILS")
    hist = get_item_history(session, u.id, "ghost")
    assert hist.points == []
    assert hist.times_bought == 0
    assert hist.latest_price is None

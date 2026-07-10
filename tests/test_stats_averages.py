from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.services import create_list_from_text, get_or_create_user
from app.stats import get_trip_averages


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


NOW = datetime(2026, 7, 15, tzinfo=timezone.utc)


def test_averages_across_trips(session):
    u = get_or_create_user(session, 1, "T", "ILS")
    _completed(session, u, datetime(2026, 7, 1, tzinfo=timezone.utc), 40.0, "milk\nbread")
    _completed(session, u, datetime(2026, 6, 20, tzinfo=timezone.utc), 60.0, "eggs\nrice\ntea")

    avg = get_trip_averages(session, u.id, now=NOW)
    assert avg.avg_trip_cost == 50.0  # (40 + 60) / 2
    assert avg.avg_basket_size == 2.5  # (2 + 3) / 2 bought items


def test_this_vs_last_month(session):
    u = get_or_create_user(session, 2, "T", "ILS")
    _completed(session, u, datetime(2026, 7, 5, tzinfo=timezone.utc), 30.0)
    _completed(session, u, datetime(2026, 7, 9, tzinfo=timezone.utc), 20.0)
    _completed(session, u, datetime(2026, 6, 10, tzinfo=timezone.utc), 40.0)

    avg = get_trip_averages(session, u.id, now=NOW)
    assert avg.this_month_total == 50.0
    assert avg.last_month_total == 40.0
    assert avg.month_delta_pct == 25.0  # (50 - 40) / 40 -> +25%


def test_month_delta_none_without_baseline(session):
    u = get_or_create_user(session, 3, "T", "ILS")
    _completed(session, u, datetime(2026, 7, 5, tzinfo=timezone.utc), 30.0)

    avg = get_trip_averages(session, u.id, now=NOW)
    assert avg.this_month_total == 30.0
    assert avg.last_month_total == 0.0
    assert avg.month_delta_pct is None


def test_january_looks_back_to_december(session):
    u = get_or_create_user(session, 4, "T", "ILS")
    _completed(session, u, datetime(2026, 1, 5, tzinfo=timezone.utc), 30.0)
    _completed(session, u, datetime(2025, 12, 20, tzinfo=timezone.utc), 60.0)

    avg = get_trip_averages(session, u.id, now=datetime(2026, 1, 15, tzinfo=timezone.utc))
    assert avg.this_month_total == 30.0
    assert avg.last_month_total == 60.0
    assert avg.month_delta_pct == -50.0


def test_empty_user(session):
    u = get_or_create_user(session, 5, "T", "ILS")
    avg = get_trip_averages(session, u.id, now=NOW)
    assert avg.avg_trip_cost == 0.0
    assert avg.avg_basket_size == 0.0
    assert avg.this_month_total == 0.0
    assert avg.month_delta_pct is None

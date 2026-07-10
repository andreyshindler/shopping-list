from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.services import create_list_from_text, get_or_create_user
from app.stats import get_trips


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _completed(session, user, when, real_total, items="milk\nbread"):
    sl = create_list_from_text(session, user, items)
    session.flush()
    sl.status = "completed"
    sl.completed_at = when
    sl.real_total = real_total
    session.flush()
    return sl


def test_get_trips_groups_by_month_newest_first(session):
    u = get_or_create_user(session, 1, "T", "ILS")
    _completed(session, u, datetime(2026, 6, 10, tzinfo=timezone.utc), 50.0)
    _completed(session, u, datetime(2026, 6, 20, tzinfo=timezone.utc), 30.0)
    _completed(session, u, datetime(2026, 5, 5, tzinfo=timezone.utc), 20.0)

    groups = get_trips(session, u.id)
    assert [(g.year, g.month) for g in groups] == [(2026, 6), (2026, 5)]
    assert groups[0].total == 80.0
    assert len(groups[0].trips) == 2
    assert groups[0].trips[0].completed_at.day == 20  # newest first within month
    assert groups[0].trips[0].item_count == 2


def test_get_trips_month_filter(session):
    u = get_or_create_user(session, 2, "T", "ILS")
    _completed(session, u, datetime(2026, 6, 10, tzinfo=timezone.utc), 50.0)
    _completed(session, u, datetime(2026, 5, 5, tzinfo=timezone.utc), 20.0)

    may = get_trips(session, u.id, month="2026-05")
    assert len(may) == 1 and may[0].month == 5
    assert may[0].trips[0].real_total == 20.0


def test_trip_variance(session):
    u = get_or_create_user(session, 3, "T", "ILS")
    sl = _completed(session, u, datetime(2026, 6, 1, tzinfo=timezone.utc), 40.0)
    sl.predicted_total = 30.0
    session.flush()
    trip = get_trips(session, u.id)[0].trips[0]
    assert trip.variance == 10.0  # paid 40, predicted 30 -> +10


def test_get_trips_ignores_incomplete(session):
    u = get_or_create_user(session, 4, "T", "ILS")
    create_list_from_text(session, u, "milk")  # active, not completed
    session.flush()
    assert get_trips(session, u.id) == []

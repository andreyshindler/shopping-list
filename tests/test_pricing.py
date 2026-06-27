import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, PriceHistory
from app.pricing import normalize_name, predicted_price, record_price


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  Milk  ", "milk"),
        ("Tomatoes", "tomato"),
        ("Apples", "apple"),
        ("Boxes", "box"),
        ("Glass", "glass"),  # 'ss' should not be stripped
        ("Berries", "berry"),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


def test_predicted_price_none_without_history(session):
    assert predicted_price(session, user_id=1, normalized_name="milk") is None


def test_predicted_price_uses_most_recent(session):
    # The latest paid price wins, so a corrected price takes effect immediately.
    for price in (2.0, 3.0, 4.0):
        record_price(session, user_id=1, normalized_name="milk", price=price, currency="USD")
    session.flush()
    assert predicted_price(session, user_id=1, normalized_name="milk") == 4.0


def test_predicted_price_scoped_per_user(session):
    record_price(session, user_id=1, normalized_name="milk", price=2.0, currency="USD")
    session.flush()
    assert predicted_price(session, user_id=2, normalized_name="milk") is None

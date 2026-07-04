import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.categories import is_weighed
from app.models import Base, PriceHistory
from app.pricing import predicted_price
from app.services import (
    complete_list,
    create_list_from_text,
    get_or_create_user,
    toggle_item,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_is_weighed():
    assert is_weighed("Produce")
    assert is_weighed("Meat & Fish")
    assert not is_weighed("Pantry")
    assert not is_weighed("Dairy & Eggs")


def test_complete_stores_per_kg_and_predicts_line_total(session):
    user = get_or_create_user(session, 1, "T", "ILS")
    sl = create_list_from_text(session, user, "2 cucumber")  # 2 kg
    session.flush()
    item = sl.items[0]
    assert item.quantity == 2.0
    toggle_item(session, item)
    session.flush()

    # User paid 8 ILS for the 2 kg line.
    complete_list(session, sl, real_total=8.0, item_prices={item.id: 8.0})
    session.flush()

    # Stored history is PER KG (8 / 2 = 4), not the line total.
    stored = session.scalar(
        PriceHistory.__table__.select().where(
            PriceHistory.normalized_name == item.normalized_name
        )
    )
    assert predicted_price(session, user.id, item.normalized_name) == 4.0

    # A new "2 cucumber" list predicts 4/kg -> line total 8.
    sl2 = create_list_from_text(session, user, "2 cucumber")
    session.flush()
    assert sl2.items[0].predicted_price == 4.0
    assert sl2.predicted_total == 8.0


def test_per_unit_unchanged_for_quantity_one(session):
    user = get_or_create_user(session, 2, "T", "ILS")
    sl = create_list_from_text(session, user, "milk")  # qty 1, not weighed
    session.flush()
    item = sl.items[0]
    toggle_item(session, item)
    session.flush()
    complete_list(session, sl, real_total=6.0, item_prices={item.id: 6.0})
    session.flush()
    # qty 1 -> per-unit == entered price
    assert predicted_price(session, user.id, item.normalized_name) == 6.0

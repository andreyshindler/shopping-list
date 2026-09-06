import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.services import create_list_from_text, get_or_create_user
from app.web.routes import _grouped_items


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_orphaned_category_falls_back_to_other(session):
    """A category removed from CATEGORY_ORDER (e.g. the retired "Canned") must not make
    already-stored items vanish from the page — they should surface under "Other" instead
    of being silently dropped while still counting toward total_count."""
    user = get_or_create_user(session, 1, "T", "ILS")
    sl = create_list_from_text(session, user, "milk\nbread")
    session.flush()
    sl.items[0].category = "Canned"  # simulate a category retired after this item was stored

    groups = _grouped_items(sl)
    all_grouped = [i for members in groups.values() for i in members]
    assert sl.items[0] in all_grouped
    assert sl.items[0] in groups["Other"]
    # total across groups must match the not-yet-bought item count — nothing lost.
    assert len(all_grouped) == sum(1 for i in sl.items if not i.is_bought)


def test_known_categories_still_group_normally(session):
    user = get_or_create_user(session, 2, "T", "ILS")
    sl = create_list_from_text(session, user, "milk\nbread")
    session.flush()

    groups = _grouped_items(sl)
    by_name = {i.raw_name: cat for cat, members in groups.items() for i in members}
    assert by_name["milk"] == "Dairy & Eggs"
    assert by_name["bread"] == "Bakery"

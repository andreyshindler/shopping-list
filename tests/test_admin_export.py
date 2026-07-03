import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.services import create_list_from_text, get_or_create_user, toggle_item


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_list_to_txt_contains_debug_fields(session):
    from app.bot.handlers import _list_to_txt

    user = get_or_create_user(session, 5, "Tester", "ILS")
    sl = create_list_from_text(session, user, "2 milk\nbread")
    session.flush()
    toggle_item(session, sl.items[0])
    session.flush()

    txt = _list_to_txt(sl)
    assert f"list_id       : {sl.id}" in txt
    assert "telegram_id=5" in txt
    assert "milk" in txt and "bread" in txt
    assert "category" in txt          # column header present
    assert "✓" in txt            # bought marker for the toggled item
    assert txt.endswith("\n")


def test_admin_user_lists_view_lists_and_back(session):
    from app.bot.handlers import _admin_user_lists_view

    user = get_or_create_user(session, 7, "Owner", "ILS")
    create_list_from_text(session, user, "milk")
    create_list_from_text(session, user, "bread")
    session.flush()

    text, kb = _admin_user_lists_view(session, user, "en")
    assert "Owner" in text
    # one export button per list + a back button
    flat = [b for row in kb.inline_keyboard for b in row]
    assert sum(1 for b in flat if b.callback_data.startswith("usr:txt:")) == 2
    assert any(b.callback_data == "usr:list" for b in flat)


def test_admin_user_lists_view_empty(session):
    from app.bot.handlers import _admin_user_lists_view

    user = get_or_create_user(session, 8, "Empty", "ILS")
    session.flush()
    text, kb = _admin_user_lists_view(session, user, "en")
    assert "No lists" in text
    flat = [b for row in kb.inline_keyboard for b in row]
    assert flat and all(b.callback_data == "usr:list" for b in flat)

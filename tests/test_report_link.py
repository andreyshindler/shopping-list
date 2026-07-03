import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.services import create_list_from_text, get_or_create_user


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_latest_list_picks_most_recent(session):
    from app.bot.handlers import _latest_list

    user = get_or_create_user(session, 10, "R", "ILS")
    create_list_from_text(session, user, "milk")
    newer = create_list_from_text(session, user, "bread")
    session.flush()
    assert _latest_list(session, user.id).id == newer.id


def test_latest_list_none_when_no_lists(session):
    from app.bot.handlers import _latest_list

    user = get_or_create_user(session, 11, "R", "ILS")
    session.flush()
    assert _latest_list(session, user.id) is None


def test_latest_list_scoped_per_user(session):
    from app.bot.handlers import _latest_list

    u1 = get_or_create_user(session, 12, "A", "ILS")
    u2 = get_or_create_user(session, 13, "B", "ILS")
    create_list_from_text(session, u1, "milk")
    session.flush()
    assert _latest_list(session, u2.id) is None

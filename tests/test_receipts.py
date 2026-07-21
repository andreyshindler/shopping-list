from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, PriceHistory
from app.receipts import (
    ReceiptData,
    ReceiptItem,
    ReceiptParseError,
    extract_receipt_json,
    receipt_from_json,
    receipt_to_json,
)
from app.services import (
    apply_receipt,
    create_list_from_text,
    get_active_list,
    get_or_create_user,
    load_receipt_draft,
    match_receipt,
    receipt_from_draft,
    save_receipt_draft,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# --- parsing -------------------------------------------------------------------


def test_extract_receipt_json_strips_fence_and_coerces():
    text = """```json
    {"store": "שופרסל", "date": "2026-07-01", "total": 24.9,
     "items": [{"name": "חלב 3%", "quantity": 2, "price": 12.4},
               {"name": "לחם", "price": "7.50 ₪"}]}
    ```"""
    r = extract_receipt_json(text)
    assert r.store == "שופרסל"
    assert r.purchased_on == date(2026, 7, 1)
    assert [(i.name, i.quantity, i.price) for i in r.items] == [
        ("חלב 3%", 2.0, 12.4),
        ("לחם", 1.0, 7.5),  # quantity defaults to 1; price parsed out of the string
    ]
    assert r.computed_total == 24.9


def test_extract_receipt_json_skips_bad_rows_and_computes_total():
    r = extract_receipt_json(
        '{"items": [{"name": "מלח", "price": 5}, {"name": "", "price": 9}, '
        '{"price": 3}, {"name": "סוכר", "price": 6}]}'
    )
    assert [i.name for i in r.items] == ["מלח", "סוכר"]
    assert r.total is None
    assert r.computed_total == 11.0  # falls back to sum of line prices


def test_extract_receipt_json_raises_on_garbage():
    with pytest.raises(ReceiptParseError):
        extract_receipt_json("sorry, I can't read this")


def test_receipt_json_roundtrip():
    r = ReceiptData(
        items=[ReceiptItem("חלב", 1.0, 6.0)],
        store="רמי לוי",
        purchased_on=date(2026, 6, 5),
        total=6.0,
    )
    back = receipt_from_json(receipt_to_json(r))
    assert back.store == "רמי לוי"
    assert back.purchased_on == date(2026, 6, 5)
    assert [(i.name, i.price) for i in back.items] == [("חלב", 6.0)]


# --- matching ------------------------------------------------------------------


def test_match_receipt_splits_matched_new_unmatched(session):
    u = get_or_create_user(session, 1, "T", "ILS")
    sl = create_list_from_text(session, u, "חלב\nלחם\nתפוח")
    session.flush()
    receipt = ReceiptData(
        items=[ReceiptItem("חלב 3%", 1.0, 6.0), ReceiptItem("קולה", 1.0, 8.0)]
    )
    plan = match_receipt(session, sl, receipt)
    assert [m.item.raw_name for m in plan.matched] == ["חלב"]  # "חלב" ⊆ "חלב 3%"
    assert [r.name for r in plan.new_items] == ["קולה"]
    assert sorted(i.raw_name for i in plan.unmatched_items) == ["לחם", "תפוח"]


def test_match_receipt_no_active_list_all_new(session):
    receipt = ReceiptData(items=[ReceiptItem("חלב", 1.0, 6.0)])
    plan = match_receipt(session, None, receipt)
    assert plan.matched == []
    assert [r.name for r in plan.new_items] == ["חלב"]


# --- applying ------------------------------------------------------------------


def test_apply_receipt_prices_new_items_and_completes(session):
    u = get_or_create_user(session, 2, "T", "ILS")
    sl = create_list_from_text(session, u, "חלב\nלחם")
    session.flush()
    receipt = ReceiptData(
        items=[
            ReceiptItem("חלב", 2.0, 12.0),  # matches "חלב" -> per-unit 6.0
            ReceiptItem("קולה", 1.0, 8.0),  # new bought item
        ],
        purchased_on=date(2026, 6, 10),
        total=20.0,
    )
    apply_receipt(session, sl, receipt)

    assert sl.status == "completed"
    assert sl.real_total == 20.0
    assert sl.completed_at == datetime(2026, 6, 10, tzinfo=timezone.utc)

    by_name = {i.raw_name: i for i in sl.items}
    assert by_name["חלב"].is_bought and by_name["חלב"].real_price == 12.0
    assert not by_name["לחם"].is_bought  # not on the receipt -> left as-is
    assert "קולה" in by_name and by_name["קולה"].is_bought and by_name["קולה"].real_price == 8.0

    # Price history: per-unit, dated to the purchase.
    milk = session.scalar(
        select(PriceHistory).where(PriceHistory.normalized_name == by_name["חלב"].normalized_name)
    )
    assert milk.price == 6.0  # 12.0 / quantity 2
    # SQLite drops tzinfo on read (Postgres keeps it); compare the calendar date.
    assert milk.recorded_at.date() == date(2026, 6, 10)


def test_draft_persist_reload_apply_roundtrip(session):
    """The exact path the Confirm callback runs: save draft -> reload -> apply."""
    u = get_or_create_user(session, 4, "T", "ILS")
    sl = create_list_from_text(session, u, "חלב")
    session.flush()
    receipt = ReceiptData(
        items=[ReceiptItem("חלב", 1.0, 6.0), ReceiptItem("קולה", 1.0, 8.0)],
        purchased_on=date(2026, 5, 1),
        total=14.0,
    )
    draft = save_receipt_draft(session, u.id, sl.id, receipt)
    session.expire_all()  # force a real reload from the DB, like a new request would

    reloaded = load_receipt_draft(session, draft.id, u.id)
    assert reloaded is not None
    assert load_receipt_draft(session, draft.id, user_id=999) is None  # owner-scoped

    parsed = receipt_from_draft(reloaded)
    target = session.get(type(sl), reloaded.list_id)
    apply_receipt(session, target, parsed)

    assert target.status == "completed"
    assert target.real_total == 14.0
    names = {i.raw_name: i for i in target.items}
    assert names["חלב"].is_bought and names["חלב"].real_price == 6.0
    assert names["קולה"].is_bought and names["קולה"].real_price == 8.0


def test_get_active_list_returns_latest_active(session):
    u = get_or_create_user(session, 3, "T", "ILS")
    old = create_list_from_text(session, u, "milk")
    session.flush()
    old.status = "completed"
    new = create_list_from_text(session, u, "bread")
    session.flush()
    assert get_active_list(session, u.id).id == new.id

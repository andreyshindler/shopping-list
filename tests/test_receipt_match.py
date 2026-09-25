import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, PriceHistory
from app.receipts import ReceiptData, ReceiptItem
from app.services import (
    apply_receipt_prices,
    create_list_from_text,
    get_or_create_user,
    match_receipt,
    toggle_item,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _list(session, text="milk\nbread"):
    user = get_or_create_user(session, 1, "T", "ILS")
    sl = create_list_from_text(session, user, text)
    session.flush()
    return sl


def test_match_receipt_matches_exact_names(session):
    sl = _list(session, "milk\nbread")
    receipt = ReceiptData(items=[
        ReceiptItem(name="milk", quantity=1, price=7.5),
        ReceiptItem(name="bread", quantity=1, price=6.0),
    ])
    plan = match_receipt(sl, receipt)
    assert len(plan.matched) == 2
    assert not plan.new_items


def test_match_receipt_subset_names(session):
    # "milk 3%" (receipt) should match plain "milk" (list item) via subset tokens.
    sl = _list(session, "milk")
    receipt = ReceiptData(items=[ReceiptItem(name="milk 3%", quantity=1, price=8.0)])
    plan = match_receipt(sl, receipt)
    assert len(plan.matched) == 1
    assert plan.matched[0].item.raw_name == "milk"


def test_match_receipt_does_not_cross_match_different_words(session):
    # שוקו (chocolate milk) must never match שוקולד (chocolate) even though both
    # start with the same letters -- whole-word token matching only.
    sl = _list(session, "שוקולד")
    receipt = ReceiptData(items=[ReceiptItem(name="שוקו", quantity=1, price=5.0)])
    plan = match_receipt(sl, receipt)
    assert not plan.matched
    assert len(plan.new_items) == 1


def test_match_receipt_each_list_item_matched_once(session):
    sl = _list(session, "milk\nmilk")  # two separate "milk" items
    receipt = ReceiptData(items=[ReceiptItem(name="milk", quantity=1, price=7.0)])
    plan = match_receipt(sl, receipt)
    assert len(plan.matched) == 1  # only one line, only one item consumed


def test_match_receipt_unmatched_line_becomes_new_item(session):
    sl = _list(session, "milk")
    receipt = ReceiptData(items=[
        ReceiptItem(name="milk", quantity=1, price=7.0),
        ReceiptItem(name="chocolate", quantity=1, price=12.0),
    ])
    plan = match_receipt(sl, receipt)
    assert len(plan.matched) == 1
    assert [i.name for i in plan.new_items] == ["chocolate"]


def test_apply_receipt_prices_sets_real_price_and_bought(session):
    sl = _list(session, "milk\nbread")
    receipt = ReceiptData(items=[
        ReceiptItem(name="milk", quantity=1, price=7.5),
        ReceiptItem(name="bread", quantity=1, price=6.0),
    ])
    plan = match_receipt(sl, receipt)
    matched = apply_receipt_prices(session, sl, plan)
    session.commit()

    assert matched == 2
    by_name = {i.raw_name: i for i in sl.items}
    assert by_name["milk"].real_price == 7.5
    assert by_name["milk"].is_bought is True
    assert by_name["bread"].real_price == 6.0

    history = session.query(PriceHistory).all()
    assert {h.normalized_name: h.price for h in history} == {"milk": 7.5, "bread": 6.0}


def test_apply_receipt_prices_divides_by_quantity_for_history(session):
    sl = _list(session, "2 milk")
    receipt = ReceiptData(items=[ReceiptItem(name="milk", quantity=2, price=15.0)])
    plan = match_receipt(sl, receipt)
    apply_receipt_prices(session, sl, plan)
    session.commit()

    item = sl.items[0]
    assert item.real_price == 15.0  # line total, unchanged
    history = session.query(PriceHistory).one()
    assert history.price == 7.5  # per-unit: 15.0 / 2


def test_apply_receipt_prices_preserves_bought_at_if_already_bought(session):
    sl = _list(session, "milk")
    item = sl.items[0]
    toggle_item(session, item)  # already checked off by the user beforehand
    session.flush()
    original_bought_at = item.bought_at
    assert original_bought_at is not None

    receipt = ReceiptData(items=[ReceiptItem(name="milk", quantity=1, price=7.5)])
    plan = match_receipt(sl, receipt)
    apply_receipt_prices(session, sl, plan)

    assert item.bought_at == original_bought_at


def test_apply_receipt_prices_does_not_touch_status_or_total(session):
    sl = _list(session, "milk")
    assert sl.status == "active"
    receipt = ReceiptData(items=[ReceiptItem(name="milk", quantity=1, price=7.5)])
    plan = match_receipt(sl, receipt)
    apply_receipt_prices(session, sl, plan)
    assert sl.status == "active"
    assert sl.real_total is None


def test_apply_receipt_prices_does_not_add_new_items(session):
    sl = _list(session, "milk")
    receipt = ReceiptData(items=[
        ReceiptItem(name="milk", quantity=1, price=7.5),
        ReceiptItem(name="chocolate", quantity=1, price=12.0),
    ])
    plan = match_receipt(sl, receipt)
    apply_receipt_prices(session, sl, plan)
    assert len(sl.items) == 1  # "chocolate" is reported via plan.new_items, not added

import pytest

from app.receipts import ReceiptParseError, extract_receipt_json


def test_parses_well_formed_json():
    text = (
        '{"store": "שופרסל", "date": "2026-09-20", "total": 45.5, '
        '"items": [{"name": "חלב", "quantity": 1, "price": 7.35}, '
        '{"name": "בננות", "quantity": 1.2, "price": 9.6}]}'
    )
    receipt = extract_receipt_json(text)
    assert receipt.store == "שופרסל"
    assert receipt.purchased_on.isoformat() == "2026-09-20"
    assert receipt.total == 45.5
    assert len(receipt.items) == 2
    assert receipt.items[0].name == "חלב"
    assert receipt.items[0].price == 7.35
    assert receipt.items[1].quantity == 1.2


def test_computed_total_falls_back_to_sum_of_items():
    text = '{"items": [{"name": "a", "quantity": 1, "price": 3}, {"name": "b", "quantity": 1, "price": 4.5}]}'
    receipt = extract_receipt_json(text)
    assert receipt.total is None
    assert receipt.computed_total == 7.5


def test_strips_code_fence():
    text = '```json\n{"items": [{"name": "milk", "quantity": 1, "price": 5}]}\n```'
    receipt = extract_receipt_json(text)
    assert receipt.items[0].name == "milk"


def test_grabs_first_json_block_amid_stray_text():
    text = 'Sure, here you go:\n{"items": [{"name": "bread", "quantity": 1, "price": 6}]}\nHope that helps!'
    receipt = extract_receipt_json(text)
    assert receipt.items[0].name == "bread"


def test_drops_rows_missing_name_or_price():
    text = (
        '{"items": ['
        '{"name": "", "quantity": 1, "price": 5}, '
        '{"name": "no price"}, '
        '{"name": "ok", "quantity": 1, "price": 3}'
        "]}"
    )
    receipt = extract_receipt_json(text)
    assert [i.name for i in receipt.items] == ["ok"]


def test_quantity_defaults_to_one_when_missing():
    text = '{"items": [{"name": "x", "price": 2}]}'
    receipt = extract_receipt_json(text)
    assert receipt.items[0].quantity == 1.0


def test_empty_items_when_receipt_unreadable():
    text = '{"store": null, "date": null, "total": null, "items": []}'
    receipt = extract_receipt_json(text)
    assert receipt.items == []
    assert receipt.computed_total == 0.0


def test_not_json_raises_parse_error():
    with pytest.raises(ReceiptParseError):
        extract_receipt_json("this is not json at all")


def test_json_but_not_an_object_raises():
    with pytest.raises(ReceiptParseError):
        extract_receipt_json("[1, 2, 3]")


def test_price_with_comma_and_currency_symbol_is_coerced():
    text = '{"items": [{"name": "x", "quantity": 1, "price": "1,234.50"}]}'
    receipt = extract_receipt_json(text)
    assert receipt.items[0].price == 1234.5

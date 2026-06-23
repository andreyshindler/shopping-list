from app.parsing import parse_message


def test_basic_lines():
    items = parse_message("milk\nbread\neggs")
    assert [i.name for i in items] == ["milk", "bread", "eggs"]
    assert all(i.quantity == 1.0 for i in items)


def test_strips_bullets_and_numbering():
    items = parse_message("- milk\n* bread\n1. eggs\n2) butter")
    assert [i.name for i in items] == ["milk", "bread", "eggs", "butter"]


def test_quantity_patterns():
    items = {i.name: i.quantity for i in parse_message("2 milk\ntomatoes x3\nbread - 2\napples")}
    assert items["milk"] == 2.0
    assert items["tomatoes"] == 3.0
    assert items["bread"] == 2.0
    assert items["apples"] == 1.0


def test_comma_separated_single_line():
    items = parse_message("milk, bread, eggs")
    assert [i.name for i in items] == ["milk", "bread", "eggs"]


def test_dedup_and_blank_lines():
    items = parse_message("milk\n\nMilk\n  \nbread")
    assert [i.name for i in items] == ["milk", "bread"]


def test_empty():
    assert parse_message("   \n\n") == []

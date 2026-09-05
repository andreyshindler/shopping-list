import pytest

from app.categories import CATEGORY_ORDER, categorize
from app.pricing import normalize_name


@pytest.mark.parametrize(
    "name,expected",
    [
        ("tomato", "Vegetables"),
        ("tomatoes", "Vegetables"),
        ("cucumber", "Vegetables"),
        ("apple", "Fruit"),
        ("banana", "Fruit"),
        ("milk", "Dairy & Eggs"),
        ("cheddar cheese", "Dairy & Eggs"),
        ("chicken breast", "Meat & Fish"),
        ("salmon", "Meat & Fish"),
        ("bread", "Bakery"),
        ("rice", "Pantry"),
        ("מלפפון במלח", "Pantry"),
        ("תירס שימורים", "Pantry"),
        ("טונה שימורים", "Meat & Fish"),  # strong head noun wins over "שימורים"
        ("frozen pizza", "Frozen"),
        ("orange juice", "Beverages"),
        ("chocolate", "Snacks"),
        ("toilet paper", "Household"),
        ("toothpaste", "Personal Care"),
        ("flux capacitor", "Other"),
    ],
)
def test_categorize(name, expected):
    assert categorize(normalize_name(name)) == expected


def test_all_categories_known():
    for name in ["milk", "bread", "widget"]:
        assert categorize(normalize_name(name)) in CATEGORY_ORDER

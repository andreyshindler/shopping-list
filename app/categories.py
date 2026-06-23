"""Rule-based categorization of shopping items via a keyword map."""

from __future__ import annotations

import re

# Display/sort order for categories on the web page.
CATEGORY_ORDER: list[str] = [
    "Produce",
    "Dairy & Eggs",
    "Meat & Fish",
    "Bakery",
    "Pantry",
    "Frozen",
    "Beverages",
    "Snacks",
    "Household",
    "Personal Care",
    "Other",
]

# Category -> keywords. Matching is substring-based on the normalized name, so plurals
# and minor variations ("tomatoes", "tomato") are covered by the singular keyword.
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Produce": [
        "apple", "banana", "orange", "lemon", "lime", "grape", "berry", "strawberr",
        "blueberr", "melon", "watermelon", "mango", "avocado", "tomato", "potato",
        "onion", "garlic", "carrot", "lettuce", "spinach", "kale", "cucumber",
        "pepper", "broccoli", "cauliflower", "mushroom", "celery", "zucchini",
        "cabbage", "corn", "pear", "peach", "plum", "cherry", "herb", "parsley",
        "cilantro", "ginger", "salad", "fruit", "vegetable", "veggie",
    ],
    "Dairy & Eggs": [
        "milk", "egg", "cheese", "butter", "yogurt", "yoghurt", "cream", "sour cream",
        "cottage", "margarine", "kefir", "mozzarella", "cheddar", "parmesan", "feta",
    ],
    "Meat & Fish": [
        "chicken", "beef", "pork", "lamb", "turkey", "bacon", "sausage", "ham",
        "steak", "mince", "ground", "fish", "salmon", "tuna", "shrimp", "prawn",
        "cod", "meat", "fillet", "ribs", "wing",
    ],
    "Bakery": [
        "bread", "bun", "bagel", "roll", "baguette", "croissant", "muffin", "cake",
        "pastry", "pita", "tortilla", "toast", "donut", "doughnut",
    ],
    "Pantry": [
        "rice", "pasta", "spaghetti", "noodle", "flour", "sugar", "salt", "pepper",
        "oil", "olive oil", "vinegar", "sauce", "ketchup", "mustard", "mayo",
        "mayonnaise", "bean", "lentil", "chickpea", "can", "canned", "soup",
        "cereal", "oat", "honey", "jam", "peanut butter", "spice", "stock",
        "broth", "tomato sauce",
    ],
    "Frozen": [
        "frozen", "ice cream", "pizza", "fries", "ice-cream",
    ],
    "Beverages": [
        "water", "juice", "soda", "cola", "coffee", "tea", "beer", "wine", "drink",
        "lemonade", "sparkling", "smoothie", "milkshake",
    ],
    "Snacks": [
        "chip", "crisp", "cracker", "cookie", "biscuit", "chocolate", "candy",
        "sweets", "popcorn", "nut", "pretzel", "snack", "granola bar", "bar",
    ],
    "Household": [
        "paper towel", "toilet paper", "tissue", "napkin", "detergent", "soap",
        "dish", "cleaner", "bleach", "sponge", "trash", "garbage", "bag", "foil",
        "wrap", "battery", "bulb", "candle", "laundry", "softener",
    ],
    "Personal Care": [
        "shampoo", "conditioner", "toothpaste", "toothbrush", "deodorant", "razor",
        "shaving", "lotion", "sunscreen", "makeup", "cosmetic", "floss", "bandage",
        "vitamin", "medicine", "tampon", "pad", "diaper", "wipe", "hand soap",
    ],
}


# Build, once, a lookup of single-word keywords and a list of multi-word phrases.
_PHRASE_KEYWORDS: list[tuple[str, str]] = []  # (phrase, category)
_WORD_KEYWORDS: list[tuple[str, str]] = []  # (word, category), in category order
for _cat in CATEGORY_ORDER:
    for _kw in CATEGORY_KEYWORDS.get(_cat, []):
        if " " in _kw or "-" in _kw:
            _PHRASE_KEYWORDS.append((_kw, _cat))
        else:
            _WORD_KEYWORDS.append((_kw, _cat))

_WORD_RE = re.compile(r"[a-z]+")


def categorize(normalized_name: str) -> str:
    """Return the category for a normalized item name, or ``Other`` if unknown.

    Multi-word keywords ("toilet paper", "olive oil") are matched first as whole
    phrases. Otherwise single words are checked from right to left, so the head noun
    wins for compounds like "orange juice" (juice -> Beverages, not orange -> Produce).
    Whole-word matching avoids false hits like "oil" inside "toilet".
    """
    name = normalized_name.lower()

    for phrase, category in _PHRASE_KEYWORDS:
        if re.search(rf"\b{re.escape(phrase)}\b", name):
            return category

    words = _WORD_RE.findall(name)
    for word in reversed(words):
        for keyword, category in _WORD_KEYWORDS:
            if word == keyword or word.startswith(keyword):
                return category
    return "Other"

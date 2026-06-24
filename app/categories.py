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
    "Baby & Kids",
    "Pet Supplies",
    "Other",
]

# Category -> keywords. Matching is substring-based on the normalized name, so plurals
# and minor variations ("tomatoes", "tomato") are covered by the singular keyword.
# Multi-word entries (with a space or hyphen) are matched as whole phrases first.
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Produce": [
        "apple", "banana", "orange", "lemon", "lime", "grape", "grapes", "berry",
        "strawberr", "strawberry", "blueberr", "melon", "watermelon", "mango", "avocado",
        "tomato", "potato", "sweet potato", "onion", "green onion", "garlic", "carrot",
        "lettuce", "romaine lettuce", "spinach", "baby spinach", "kale", "arugula",
        "cucumber", "pepper", "bell pepper", "broccoli", "cauliflower", "mushroom",
        "mushrooms", "celery", "zucchini", "cabbage", "corn", "pear", "peach", "plum",
        "cherry", "herb", "parsley", "cilantro", "dill", "ginger", "salad", "fruit",
        "vegetable", "veggie", "beetroot", "beet", "radish", "leek", "clementine",
        "pomelo", "kiwi", "pineapple", "artichoke", "dates", "eggplant",
        # Hebrew
        "תפוח", "תפוח עץ", "תפוחים", "בננה", "בננות", "תפוז", "תפוזים", "לימון", "לימונים",
        "ענב", "ענבים", "תות", "תות שדה", "תותים", "אבטיח", "מלון", "מנגו", "אבוקדו",
        "עגבניה", "עגבנייה", "עגבניות", "תפוח אדמה", "בטטה", "בטטות", "בצל", "בצל ירוק",
        "שום", "גזר", "גזרים", "חסה", "תרד", "עלי תרד", "רוקט", "מלפפון", "מלפפונים",
        "פלפל", "פלפל אדום", "פלפל צהוב", "פלפל ירוק", "ברוקולי", "כרובית", "כרוב",
        "פטריות", "סלרי", "תירס", "אגס", "אגסים", "אפרסק", "שזיף", "דובדבן", "דובדבנים",
        "פטרוזיליה", "כוסברה", "שמיר", "ג'ינג'ר", "סלט", "ירקות", "פירות", "חציל",
        "קישוא", "קישואים", "סלק", "צנון", "כרישה", "קלמנטינה", "פומלית", "קיווי",
        "אננס", "ארטישוק", "תמר",
    ],
    "Dairy & Eggs": [
        "milk", "whole milk", "skim milk", "lactose-free milk", "oat milk", "almond milk",
        "cheese", "cheddar cheese", "cheddar", "mozzarella", "parmesan", "brie",
        "cottage cheese", "cottage", "yogurt", "yoghurt", "greek yogurt", "plain yogurt",
        "fruit yogurt", "cream", "sour cream", "heavy cream", "cooking cream",
        "whipped cream", "cream cheese", "string cheese", "butter", "egg", "eggs",
        "kefir", "ricotta", "mascarpone", "feta", "margarine",
        # Hebrew
        "חלב", "חלב ללא לקטוז", "חלב שיבולת שועל", "חלב שקדים", "גבינה", "גבינה צהובה",
        "גבינה לבנה", "גבינה מחוטים", "מוצרלה", "פרמזן", "ברי", "קוטג'", "יוגורט",
        "יוגורט יווני", "יוגורט טבעי", "יוגורט פירות", "שמנת", "שמנת חמוצה", "שמנת מתוקה",
        "שמנת בישול", "שמנת מוקצפת", "חמאה", "ביצה", "ביצים", "קפיר", "ריקוטה",
        "מסקרפונה", "פטה", "לבן", "אשל",
    ],
    "Meat & Fish": [
        "chicken", "chicken breast", "ground chicken", "ground beef", "beef",
        "chicken thighs", "chicken drumsticks", "chicken wings", "ribeye steak", "steak",
        "beef fillet", "fillet", "lamb chops", "lamb", "chicken liver", "liver",
        "hot dog", "hot dogs", "sausage", "sausages", "beef sausages", "kebab", "burger",
        "burger patties", "corned beef", "bacon", "salmon", "salmon fillet", "sea bass",
        "cod", "cod fillet", "tuna", "fresh tuna", "shrimp", "prawn", "tilapia", "halibut",
        "sardines", "fish", "pork", "turkey", "ham", "mince", "ribs", "wing", "meat",
        "hamburger", "schnitzel",
        # Hebrew
        "עוף", "חזה עוף", "טחון עוף", "טחון בקר", "בקר", "פרגית", "פרגיות", "שוק עוף",
        "כרעיים", "כנפיים", "אנטריקוט", "פילה בקר", "פילה", "צוואר כבש", "כבש", "כבד עוף",
        "כבד", "נקניק", "נקניקיות", "נקניקיות עוף", "נקניקיות בקר", "קבב", "המבורגר",
        "קורנדביף", "בייקון", "סלמון", "דג דניס", "דניס", "פילה בקלה", "בקלה", "טונה",
        "טונה טרייה", "שרימפס", "אמנון", "הליבוט", "סרדינים", "דג", "דגים", "בשר",
        "חזיר", "הודו", "סטייק", "שניצל",
    ],
    "Bakery": [
        "bread", "white bread", "whole wheat bread", "sourdough bread", "sourdough",
        "rye bread", "gluten-free bread", "olive bread", "flatbread", "pita bread", "pita",
        "dinner rolls", "roll", "rolls", "croissant", "challah", "bagel", "flour tortillas",
        "tortilla", "focaccia", "cheese pastry", "pastry", "cinnamon roll", "danish pastry",
        "danish", "brioche", "english muffin", "muffin", "hamburger buns", "hot dog buns",
        "bun", "buns", "baguette", "pretzel", "toast", "donut", "doughnut",
        # Hebrew
        "לחם", "לחם שחור", "לחם לבן", "לחם מלא", "לחם שיפון", "לחם ללא גלוטן", "לחם שטוח",
        "לחם זיתים", "פיתה", "פיתות", "לחמניה", "לחמניות", "לחמניית המבורגר",
        "לחמניית הוט-דוג", "קרואסון", "חלה", "חלות", "בייגל", "טורטייה", "פוקאצ'ה",
        "מאפה", "מאפה גבינה", "רוגלך", "דנמרק", "בריוש", "מאפין", "מאפין אנגלי", "באגט",
        "פרצל",
    ],
    "Pantry": [
        "rice", "white rice", "basmati rice", "brown rice", "spaghetti", "penne",
        "fusilli", "pasta", "noodle", "noodles", "flour", "all-purpose flour",
        "whole wheat flour", "oil", "olive oil", "canola oil", "tomato paste",
        "crushed tomatoes", "canned beans", "bean", "canned chickpeas", "chickpea",
        "red lentils", "lentil", "tuna in oil", "tuna in water", "sugar", "brown sugar",
        "salt", "black pepper", "cumin", "paprika", "turmeric", "cinnamon", "vinegar",
        "soy sauce", "sauce", "ketchup", "mustard", "mayonnaise", "mayo", "tahini", "jam",
        "honey", "pickles", "olives", "ground coffee", "instant coffee", "coffee",
        "black tea", "herbal tea", "tea", "cocoa", "yeast", "baking powder",
        "vanilla extract", "vanilla", "baking chocolate", "granola", "oatmeal",
        "cornflakes", "cereal", "oat", "maple syrup", "syrup", "peanut butter",
        "almond butter", "can", "canned", "soup", "spice", "stock", "broth",
        # Hebrew
        "אורז", "אורז לבן", "אורז בסמטי", "אורז מלא", "פסטה", "פסטה ספגטי", "פסטה פנה",
        "פסטה פוסילי", "ספגטי", "אטריות", "קמח", "קמח לבן", "קמח מלא", "שמן", "שמן זית",
        "שמן קנולה", "רסק עגבניות", "עגבניות מרוסקות", "שעועית", "שעועית משומרת", "חומוס",
        "חומוס משומר", "עדשים", "עדשים אדומות", "טונה בשמן", "טונה במים", "סוכר",
        "סוכר חום", "מלח", "פלפל שחור", "כמון", "פפריקה", "כורכום", "קינמון", "ויניגר",
        "חומץ", "רוטב", "רוטב סויה", "קטשופ", "חרדל", "מיונז", "טחינה", "ריבה", "דבש",
        "פיקלס", "זיתים", "קפה", "קפה טחון", "קפה נמס", "תה", "תה שחור", "תה צמחים",
        "קקאו", "שמרים", "אבקת אפייה", "וניל", "שוקולד אפייה", "גרנולה", "קוורקר",
        "קורנפלקס", "סירופ מייפל", "חמאת בוטנים", "חמאת שקדים", "קוסקוס", "פתיתים",
        "תבלין", "תבלינים",
    ],
    "Frozen": [
        "frozen", "frozen pizza", "pizza", "mixed vegetables", "frozen corn",
        "frozen peas", "frozen green beans", "frozen broccoli", "vanilla ice cream",
        "chocolate ice cream", "ice cream", "ice-cream", "ice lolly", "chicken nuggets",
        "nuggets", "fish fingers", "meatballs", "frozen burger", "frozen fish fillet",
        "frozen shrimp", "phyllo dough", "puff pastry", "frozen soup", "edamame",
        "frozen crepes", "frozen waffles", "waffle", "frozen fries", "fries",
        "frozen burritos", "burrito",
        # Hebrew
        "קפוא", "קפואה", "קפואים", "פיצה קפואה", "פיצה", "ירקות מעורבים", "תירס קפוא",
        "אפונה", "אפונה קפואה", "שעועית ירוקה קפואה", "ברוקולי קפוא", "גלידה", "גלידת וניל",
        "גלידת שוקולד", "ארטיק", "שניצלון", "פינגר", "כדורי עוף", "כדורי בשר", "בורגר קפוא",
        "דג קפוא", "שרימפס קפוא", "פילו קפוא", "בצק עלים", "מרק קפוא", "אדמאמה", "קרפ קפוא",
        "וופל קפוא", "צ'יפס קפוא", "בוריטו קפוא",
    ],
    "Beverages": [
        "orange juice", "fresh orange juice", "juice", "grape juice", "apple juice",
        "grapefruit juice", "peach juice", "cola", "diet cola", "sprite", "fanta",
        "ginger ale", "red bull", "still water", "water", "sparkling water",
        "mineral water", "strawberry milkshake", "milkshake", "chocolate milk", "iced tea",
        "cold brew coffee", "lemonade", "coconut water", "tonic water", "tonic", "beer",
        "red wine", "white wine", "rosé wine", "wine", "kombucha", "soda", "drink",
        "smoothie", "sparkling",
        # Hebrew
        "מיץ", "מיץ תפוזים", "מיץ ענבים", "מיץ תפוחים", "מיץ אשכוליות", "מיץ אפרסק", "קולה",
        "קולה זירו", "ספרייט", "פנטה", "ג'ינג'ר אייל", "רד בול", "מים", "מים מינרלים",
        "מים מוגזים", "שייק", "שייק תות", "שוקו", "תה קר", "קפה קר", "לימונדה", "מי קוקוס",
        "טוניק", "בירה", "יין", "יין אדום", "יין לבן", "יין רוזה", "קומבוצ'ה", "סודה",
        "משקה", "משקאות",
    ],
    "Snacks": [
        "pretzels", "potato chips", "chip", "chips", "pringles", "popcorn", "rice cakes",
        "cracker", "crackers", "dark chocolate", "milk chocolate", "white chocolate",
        "chocolate", "kinder", "snickers", "twix", "mars", "mentos", "oreo", "gummy bears",
        "gummy", "candy", "sweets", "chocolate chip cookies", "cookie", "cookies",
        "oat cookies", "trail mix", "salted peanuts", "peanut", "peanuts", "pistachio",
        "almond", "almonds", "walnut", "walnuts", "cashew", "cashews", "dried fruits",
        "granola bar", "protein bar", "bar", "fruit leather", "nut", "biscuit", "snack",
        # Hebrew
        "פרצלים", "צ'יפס", "פרינגלס", "פופקורן", "פופקורן חמאה", "פופקורן מלוח",
        "עוגות אורז", "קרקר", "קרקרים", "שוקולד", "שוקולד מריר", "שוקולד חלב", "שוקולד לבן",
        "קינדר", "סניקרס", "טוויקס", "מארס", "מנטוס", "אוראו", "גומי", "גומי דובים",
        "סוכריה", "סוכריות", "עוגיה", "עוגיות", "עוגיות שוקולד צ'יפס", "עוגיות שיבולת שועל",
        "תערובת גרגירים", "בוטנים", "בוטנים מלוחים", "פיסטוק", "שקדים", "אגוזי מלך", "קשיו",
        "פירות יבשים", "גרנולה בר", "חטיף חלבון", "חטיף", "חטיפים", "עור פרי", "במבה",
        "ביסלי", "ופל", "ופלים",
    ],
    "Household": [
        "laundry detergent", "detergent", "liquid detergent", "fabric softener", "softener",
        "dish soap", "dishwasher tablets", "bleach", "bathroom cleaner", "toilet gel",
        "multi-surface spray", "all-purpose cleaner", "cleaner", "toilet paper",
        "paper towel", "paper towels", "tissue", "tissues", "trash bags", "trash",
        "garbage", "cling wrap", "stretch wrap", "wrap", "aluminum foil", "foil",
        "freezer bags", "bag", "bags", "dish sponge", "sponge", "mop", "rubber gloves",
        "gloves", "dryer sheets", "cleaning wipes", "broom", "dustpan", "soap", "dish",
        "napkin", "battery", "bulb", "candle", "laundry",
        # Hebrew
        "אבקת כביסה", "נוזל כביסה", "מרכך כביסה", "סבון כלים", "טבליות מדיח", "מדיח",
        "אקונומיקה", "נוזל ניקוי אמבטיה", "ג'ל אסלה", "ספריי ניקוי", "נוזל ניקוי כללי",
        "נייר טואלט", "מגבות נייר", "ממחטות נייר", "שקיות אשפה", "שקיות אשפה גדולות",
        "שקיות אשפה קטנות", "ניילון נצמד", "ניילון מתיחה", "נייר אלומיניום", "שקיות פריזר",
        "ספוג כלים", "ספוג", "ספוגים", "מגב רצפה", "מגב", "כפפות גומי", "יריעות מייבש",
        "ווייפ ניקוי", "מטאטא", "יד מגב", "סבון", "שקיות", "ניילון", "סוללה", "סוללות",
        "נורה", "נר", "נרות",
    ],
    "Personal Care": [
        "shampoo", "dry shampoo", "conditioner", "body wash", "hand soap", "shower gel",
        "face wash", "face moisturizer", "moisturizer", "body lotion", "lotion",
        "sunscreen", "deodorant", "lip balm", "toothpaste", "toothbrush", "dental floss",
        "floss", "razor", "shaving foam", "shaving", "sanitary pads", "pad", "pads",
        "tampons", "tampon", "wet wipes", "wipe", "wipes", "hand cream", "cotton pads",
        "cotton swabs", "cotton", "nail polish remover", "nail polish", "hair oil", "cream",
        "makeup", "cosmetic", "bandage", "vitamin", "medicine",
        # Hebrew
        "שמפו", "שמפו יבש", "מרכך שיער", "מרכך", "סבון גוף", "סבון ידיים", "סבון פנים",
        "ג'ל רחצה", "קרם לחות פנים", "קרם לחות גוף", "קרם לחות", "קרם שיזוף", "קרם ידיים",
        "דאודורנט", "מיצג שפתיים", "משחת שיניים", "מברשת שיניים", "חוט דנטלי", "מכונת גילוח",
        "קצף גילוח", "תחבושות היגייניות", "טמפקס", "טמפון", "טמפונים", "ממחטות לח", "צמר גפן",
        "מוצצי אוזניים", "אצטון", "לק", "שמן שיער", "קרם", "תחליב", "איפור", "ויטמין",
        "ויטמינים", "מגבון", "מגבונים",
    ],
    "Baby & Kids": [
        "diaper", "diapers", "diaper rash cream", "baby wipes", "baby powder",
        "baby shampoo", "baby wash", "baby lotion", "baby food", "baby cereal",
        "baby snacks", "baby juice", "baby bottle", "formula", "pacifier", "teether",
        "baby nail clippers", "pull-ups", "training pants",
        # Hebrew
        "תינוק", "חיתול", "חיתולים", "חיתולי לילה", "חיתולי אימון", "מגבונים לחים",
        "קרם פצעי חיתול", "אבקת תינוק", "שמפו תינוק", "סבון תינוק", "קרם תינוק", "פורמולה",
        "מזון תינוק", "דייסת תינוק", "חטיפים לתינוק", "מיץ פירות לתינוק", "בקבוק תינוק",
        "מוצץ", "מחבט לשיניים", "מספריים לתינוק", "סוללות למוניטור", "טיולון",
    ],
    "Pet Supplies": [
        "dog food", "dry dog food", "wet dog food", "cat food", "dry cat food",
        "wet cat food", "dog treats", "cat treats", "cat litter", "dog shampoo",
        "chew bones", "fish food", "bird food", "cat toy", "dog toy", "pet brush",
        "poop bags", "flea treatment",
        # Hebrew
        "מזון יבש לכלב", "מזון רטוב לכלב", "מזון לכלב", "מזון יבש לחתול", "מזון רטוב לחתול",
        "מזון לחתול", "חטיפים לכלב", "חטיפים לחתול", "חול לחתול", "שמפו לכלב", "עצמות ללעיסה",
        "מזון לדגים", "מזון לציפורים", "צעצוע לחתול", "צעצוע לכלב", "מברשת לחיות",
        "שקיות לצרכים", "טיפול נגד פרעושים", "כלב", "חתול", "חיות",
    ],
}


# Apostrophe / Hebrew geresh used in transliterations ("קוטג'", "צ'יפס"). We strip
# these from both keywords and item names so spelling variants still match.
_MARKS_RE = re.compile(r"['׳’]")


def _strip_marks(text: str) -> str:
    return _MARKS_RE.sub("", text.lower())


# Build, once, a lookup of single-word keywords and a list of multi-word phrases.
_PHRASE_KEYWORDS: list[tuple[str, str]] = []  # (phrase, category)
_WORD_KEYWORDS: list[tuple[str, str]] = []  # (word, category), in category order
for _cat in CATEGORY_ORDER:
    for _kw in CATEGORY_KEYWORDS.get(_cat, []):
        _clean = _strip_marks(_kw)
        if " " in _clean or "-" in _clean:
            _PHRASE_KEYWORDS.append((_clean, _cat))
        else:
            _WORD_KEYWORDS.append((_clean, _cat))

# Match runs of letters in any script, so Hebrew words are tokenized too.
_WORD_RE = re.compile(r"[^\W\d_]+")


def categorize(normalized_name: str) -> str:
    """Return the category for a normalized item name, or ``Other`` if unknown.

    Multi-word keywords ("toilet paper", "olive oil") are matched first as whole
    phrases. Otherwise single words are checked from right to left, so the head noun
    wins for compounds like "orange juice" (juice -> Beverages, not orange -> Produce).
    English keywords also match by prefix ("tomatoes" -> "tomato"); non-ASCII (Hebrew)
    keywords match whole words only, to avoid false hits like "דגנים" (cereal) -> "דג".
    """
    name = _strip_marks(normalized_name)

    for phrase, category in _PHRASE_KEYWORDS:
        if re.search(rf"\b{re.escape(phrase)}\b", name):
            return category

    words = _WORD_RE.findall(name)
    for word in reversed(words):
        for keyword, category in _WORD_KEYWORDS:
            if word == keyword or (keyword.isascii() and word.startswith(keyword)):
                return category
    return "Other"

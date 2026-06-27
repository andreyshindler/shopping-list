"""Tiny translation catalog for the web UI (English + Hebrew)."""

from __future__ import annotations

from app.categories import CATEGORY_ORDER

DEFAULT_LANG = "he"
SUPPORTED_LANGS = ("he", "en")

# Localised display names for the (English) category keys stored on items.
CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "en": {category: category for category in CATEGORY_ORDER},
    "he": {
        "Produce": "פירות וירקות",
        "Dairy & Eggs": "חלב וביצים",
        "Meat & Fish": "בשר ודגים",
        "Bakery": "מאפים",
        "Pantry": "מזווה",
        "Frozen": "קפואים",
        "Beverages": "משקאות",
        "Snacks": "חטיפים",
        "Household": "מוצרי בית",
        "Personal Care": "טיפוח",
        "Baby & Kids": "תינוק וילדים",
        "Pet Supplies": "חיות מחמד",
        "Other": "אחר",
    },
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "shopping_list": "Shopping list",
        "statistics": "Statistics",
        "predicted_total": "Predicted total",
        "bought": "Bought",
        "bought_section": "✓ Bought",
        "no_history": "no history",
        "pick_variant": "Which one? Tap to choose:",
        "custom_variant": "Or type your own product",
        "add": "Add",
        "all_done": "All done! 🎉",
        "enter_paid": "Enter what you actually paid so we can improve "
        "predictions and your statistics.",
        "total_paid": "Total paid",
        "save_finish": "Save & finish",
        "finish_shopping": "Finish shopping now",
        "finish_confirm": "Some items aren't marked as bought. End the list and save them for next time?",
        "list_ended": "🏁 List ended",
        "missing_saved": "Items you didn't buy were saved for your next list.",
        "empty_list": "This list is empty.",
        "swipe_hint": "← Swipe left on an item to delete it",
        "share_list": "Share",
        "completed": "✅ Completed",
        "real_total_spent": "Real total spent",
        "total_spent": "Total spent",
        "shopping_trips": "Shopping trips",
        "monthly_spending": "Monthly spending",
        "yearly_spending": "Yearly spending",
        "most_bought": "Most bought items",
        "no_trips": "No completed trips yet.",
    },
    "he": {
        "shopping_list": "רשימת קניות",
        "statistics": "סטטיסטיקה",
        "predicted_total": "סכום צפוי",
        "bought": "נקנו",
        "bought_section": "✓ נקנו",
        "no_history": "אין היסטוריה",
        "pick_variant": "איזה מהם? הקישו לבחירה:",
        "custom_variant": "או הקלידו מוצר משלכם",
        "add": "הוסף",
        "all_done": "הכול מוכן! 🎉",
        "enter_paid": "הזינו כמה שילמתם בפועל כדי לשפר את התחזיות "
        "והסטטיסטיקה שלכם.",
        "total_paid": "סך הכול שולם",
        "save_finish": "שמירה וסיום",
        "finish_shopping": "סיום הקנייה",
        "finish_confirm": "יש פריטים שלא סומנו כנקנו. לסיים את הרשימה ולשמור אותם לפעם הבאה?",
        "list_ended": "🏁 הקנייה הסתיימה",
        "missing_saved": "הפריטים שלא קנית נשמרו לרשימה הבאה.",
        "empty_list": "הרשימה ריקה.",
        "swipe_hint": "← החלק שמאלה על פריט כדי למחוק",
        "share_list": "שתף",
        "completed": "✅ הושלם",
        "real_total_spent": "סכום ששולם בפועל",
        "total_spent": "סך ההוצאות",
        "shopping_trips": "מספר קניות",
        "monthly_spending": "הוצאות חודשיות",
        "yearly_spending": "הוצאות שנתיות",
        "most_bought": "הפריטים הנפוצים ביותר",
        "no_trips": "אין עדיין קניות שהושלמו.",
    },
}


def normalize_lang(lang: str | None) -> str:
    """Return a supported language code, defaulting to Hebrew."""
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def i18n_context(
    lang: str | None, lang_token: str | None = None, lang_kind: str = "list"
) -> dict[str, object]:
    """Localisation template variables for a given (per-user) language.

    ``lang_token``/``lang_kind`` identify the owner so the EN/עב toggle can persist
    the choice back to ``User.language`` (shared with the bot). When ``lang_token``
    is None the toggle is hidden.
    """
    lang = normalize_lang(lang)
    return {
        "lang": lang,
        "dir": "rtl" if lang == "he" else "ltr",
        "t": TRANSLATIONS[lang],
        "cat_labels": CATEGORY_LABELS[lang],
        "lang_token": lang_token,
        "lang_kind": lang_kind,
    }

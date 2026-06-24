"""Translation catalog and localisation helpers for the Telegram bot."""

from __future__ import annotations

from calendar import month_abbr, month_name

from aiogram.types import BotCommand, KeyboardButton, ReplyKeyboardMarkup

DEFAULT_LANG = "he"
SUPPORTED_LANGS = ("he", "en")

# Hebrew month names, indexed 1..12 (index 0 unused, to match calendar.month_name).
_HE_MONTHS = [
    "",
    "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
    "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר",
]

BOT_TEXT: dict[str, dict[str, str]] = {
    "he": {
        "help": (
            "🛒 *בוט רשימת קניות*\n\n"
            "שלחו לי את רשימת הקניות — פריט אחד בכל שורה (או מופרדים בפסיקים). "
            "אני אמיין אותם לקטגוריות ואחזיר לכם קישור לדף אינטרנט.\n\n"
            "דוגמאות:\n"
            "`2 חלב`\n`לחם`\n`עגבניות x3`\n\n"
            "פקודות:\n"
            "הרשימות של החודש והיסטוריה — ⁦/lists⁩\n"
            "סטטיסטיקת הוצאות — ⁦/stats⁩\n"
            "הגדרת מטבע — ⁦/currency ILS⁩\n"
            "שינוי שפה — ⁦/language⁩\n"
            "דיווח על תקלה — ⁦/report⁩\n"
            "עזרה — ⁦/help⁩"
        ),
        "btn_lists": "🧾 הרשימות שלי",
        "btn_stats": "📊 סטטיסטיקה",
        "btn_currency": "💱 מטבע",
        "btn_language": "🌐 שפה",
        "btn_report": "🐞 דיווח על תקלה",
        "btn_help": "❓ עזרה",
        "report_usage": (
            "כדי לדווח על תקלה, שלחו הודעה שמתחילה ב-⁦/report⁩ ואחריה התיאור.\nלמשל:\n"
            "`/report הכפתור לא עובד`"
        ),
        "report_sent": "תודה! הדיווח נשלח למנהל. ✅",
        "report_unavailable": "דיווח אינו זמין כרגע.",
        "report_to_admin": "🐞 דיווח תקלה חדש:\n{text}\n\nמאת: {name}\nשם משתמש: {username}\nמזהה: {id}",
        "currency_usage": "שימוש: /currency ILS",
        "currency_set": "המטבע הוגדר ל-{code}.",
        "currency_current": "המטבע שלכם הוא *{cur}*.\nכדי לשנות, שלחו `/currency ILS`.",
        "id_text": "מזהה הטלגרם שלכם הוא `{id}`.",
        "choose_language": "בחרו שפה:",
        "language_set": "השפה שונתה לעברית.",
        "pending": "⏳ הגישה שלכם ממתינה לאישור. תקבלו כאן הודעה לאחר האישור.",
        "approved_user": "✅ אושרתם! שלחו לי רשימת קניות כדי להתחיל.",
        "new_user_admin": "👤 משתמש חדש מבקש להשתמש בבוט:\n{name}\nשם משתמש: {username}\nמזהה: {id}",
        "btn_approve": "✅ אישור",
        "btn_deny": "🚫 דחייה",
        "approved_admin": "✅ {name} אושר (מזהה {id}).",
        "denied_admin": "🚫 {name} נדחה (מזהה {id}).",
        "approved_toast": "אושר.",
        "denied_toast": "נדחה.",
        "not_allowed": "לא מורשה.",
        "user_not_found": "המשתמש לא נמצא.",
        "no_pending": "אין משתמשים הממתינים לאישור.",
        "pending_entry": "👤 {name}\nמזהה: {id}",
        "stats_link": "📊 הסטטיסטיקה שלכם: {url}",
        "lists_title": "רשימות — {period}",
        "no_lists_period": "אין רשימות לתקופה זו.",
        "total_spent": "סך הכול שהוצא: {amount}",
        "open_link": "פתיחה",
        "history_btn": "📅 היסטוריה",
        "select_year": "📅 *היסטוריה* — בחרו שנה:",
        "select_month": "📅 *{year}* — בחרו חודש:",
        "back_years": "« שנים",
        "back_months": "« חודשים",
        "no_history": "אין עדיין היסטוריה.",
        "added": "✅ נוספו {count} פריט(ים) ומוינו לקטגוריות.",
        "predicted_total": "סכום צפוי: {amount}",
        "price_breakdown": "💰 {with_price} עם מחיר צפוי · ❓ {without_price} ללא",
        "open_your_list": "פתחו את הרשימה:",
        "no_items_found": "לא מצאתי פריטים בהודעה.",
        "pending_intro": "פריטים שלא קנית בפעם הקודמת — הקישו כדי להוסיף לרשימה:",
        "btn_clear_pending": "🗑 נקה הכול",
        "pending_added": "נוסף ✅",
        "pending_cleared": "הפריטים שנשמרו נמחקו.",
        "pending_done": "הכול טופל. ✅",
    },
    "en": {
        "help": (
            "🛒 *Shopping List Bot*\n\n"
            "Send me your shopping list — one item per line (or comma separated). "
            "I'll sort it into categories and give you a web link.\n\n"
            "Examples:\n"
            "`2 milk`\n`bread`\n`tomatoes x3`\n\n"
            "Commands:\n"
            "/lists — this month's lists & history\n"
            "/stats — spending statistics\n"
            "/currency ILS — set your currency\n"
            "/language — change language\n"
            "/report — report a bug\n"
            "/help — show this help"
        ),
        "btn_lists": "🧾 My lists",
        "btn_stats": "📊 Stats",
        "btn_currency": "💱 Currency",
        "btn_language": "🌐 Language",
        "btn_report": "🐞 Report a bug",
        "btn_help": "❓ Help",
        "report_usage": (
            "To report a bug, send a message starting with ⁦/report⁩ followed by the "
            "description.\nE.g.:\n`/report the toggle button doesn't work`"
        ),
        "report_sent": "Thanks! Your report was sent to the admin. ✅",
        "report_unavailable": "Reporting isn't available right now.",
        "report_to_admin": "🐞 New bug report:\n{text}\n\nfrom: {name}\nusername: {username}\nid: {id}",
        "currency_usage": "Usage: /currency ILS",
        "currency_set": "Currency set to {code}.",
        "currency_current": "Your currency is *{cur}*.\nTo change it, send `/currency ILS`.",
        "id_text": "Your Telegram ID is `{id}`.",
        "choose_language": "Choose a language:",
        "language_set": "Language set to English.",
        "pending": "⏳ Your access is pending approval. You'll get a message here once you're approved.",
        "approved_user": "✅ You've been approved! Send me your shopping list to get started.",
        "new_user_admin": "👤 New user wants to use the bot:\n{name}\nusername: {username}\nid: {id}",
        "btn_approve": "✅ Approve",
        "btn_deny": "🚫 Deny",
        "approved_admin": "✅ Approved {name} (id {id}).",
        "denied_admin": "🚫 Denied {name} (id {id}).",
        "approved_toast": "Approved.",
        "denied_toast": "Denied.",
        "not_allowed": "Not allowed.",
        "user_not_found": "User not found.",
        "no_pending": "No users are awaiting approval.",
        "pending_entry": "👤 {name}\nid: {id}",
        "stats_link": "📊 Your statistics: {url}",
        "lists_title": "Lists — {period}",
        "no_lists_period": "No lists for this period.",
        "total_spent": "Total spent: {amount}",
        "open_link": "open",
        "history_btn": "📅 History",
        "select_year": "📅 *History* — select a year:",
        "select_month": "📅 *{year}* — select a month:",
        "back_years": "« Years",
        "back_months": "« Months",
        "no_history": "No history yet.",
        "added": "✅ Added {count} item(s) and sorted them by category.",
        "predicted_total": "Predicted total: {amount}",
        "price_breakdown": "💰 {with_price} with predicted price · ❓ {without_price} without",
        "open_your_list": "Open your list:",
        "no_items_found": "I couldn't find any items in that message.",
        "pending_intro": "Carried over from last time — tap to add to your list:",
        "btn_clear_pending": "🗑 Clear all",
        "pending_added": "Added ✅",
        "pending_cleared": "Carried-over items cleared.",
        "pending_done": "All set. ✅",
    },
}


def normalize_lang(lang: str | None) -> str:
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def t(lang: str | None) -> dict[str, str]:
    """Return the translation dict for a language (falling back to the default)."""
    return BOT_TEXT[normalize_lang(lang)]


def button_labels(key: str) -> set[str]:
    """All localized labels for a reply-keyboard button, across languages."""
    return {BOT_TEXT[lang][key] for lang in SUPPORTED_LANGS}


def month_label(lang: str, month: int) -> str:
    """Full month name for titles."""
    return _HE_MONTHS[month] if normalize_lang(lang) == "he" else month_name[month]


def month_short(lang: str, month: int) -> str:
    """Short month label for the history month-picker buttons."""
    return _HE_MONTHS[month] if normalize_lang(lang) == "he" else month_abbr[month]


def main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    tr = t(lang)
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=tr["btn_lists"]), KeyboardButton(text=tr["btn_stats"])],
            [KeyboardButton(text=tr["btn_currency"]), KeyboardButton(text=tr["btn_language"])],
            [KeyboardButton(text=tr["btn_report"]), KeyboardButton(text=tr["btn_help"])],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# Command-menu (☰) entries per language. Telegram shows these by the user's *client*
# locale, so we register Hebrew as the default and English for en-locale clients.
BOT_COMMANDS: dict[str, list[BotCommand]] = {
    "he": [
        BotCommand(command="start", description="התחלה / עזרה"),
        BotCommand(command="lists", description="רשימות החודש והיסטוריה"),
        BotCommand(command="stats", description="סטטיסטיקת הוצאות"),
        BotCommand(command="currency", description="הגדרת מטבע (למשל /currency ILS)"),
        BotCommand(command="language", description="שינוי שפה"),
        BotCommand(command="report", description="דיווח על תקלה למנהל"),
        BotCommand(command="help", description="איך משתמשים בבוט"),
    ],
    "en": [
        BotCommand(command="start", description="Start / help"),
        BotCommand(command="lists", description="This month's lists & history"),
        BotCommand(command="stats", description="Spending statistics"),
        BotCommand(command="currency", description="Set your currency (e.g. /currency ILS)"),
        BotCommand(command="language", description="Change language"),
        BotCommand(command="report", description="Report a bug to the admin"),
        BotCommand(command="help", description="How to use the bot"),
    ],
}

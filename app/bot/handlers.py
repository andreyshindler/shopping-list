"""Telegram bot command and message handlers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import extract, select

from app.bot.i18n import (
    button_labels,
    main_keyboard,
    month_label,
    month_short,
    normalize_lang,
    t,
)
from app.config import get_settings
from app.db import session_scope
from app.models import Item, PendingItem, ShoppingList, User
from app.services import (
    add_item_from_pending,
    create_list_from_text,
    delete_lists_in_range,
    discard_carryover,
    get_or_create_user,
)

router = Router()
settings = get_settings()


def _display_name(message: Message) -> str | None:
    return _user_name(message.from_user)


def _user_name(tg_user) -> str | None:
    return (tg_user.full_name or tg_user.username) if tg_user else None


def _is_admin(telegram_id: int | None) -> bool:
    return bool(settings.admin_telegram_id) and telegram_id == settings.admin_telegram_id


def _get_or_create(session, tg_user) -> User:
    return get_or_create_user(
        session, tg_user.id, _user_name(tg_user), settings.default_currency
    )


def _admin_lang(session) -> str:
    admin = session.scalar(
        select(User).where(User.telegram_id == settings.admin_telegram_id)
    )
    return normalize_lang(admin.language if admin else None)


def _approval_keyboard(telegram_id: int, lang: str) -> InlineKeyboardMarkup:
    tr = t(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=tr["btn_approve"], callback_data=f"approve:{telegram_id}"
                ),
                InlineKeyboardButton(text=tr["btn_deny"], callback_data=f"deny:{telegram_id}"),
            ]
        ]
    )


# --- Basic commands ------------------------------------------------------------


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    """Reply with the caller's numeric Telegram ID (used to set ADMIN_TELEGRAM_ID)."""
    with session_scope() as session:
        lang = _get_or_create(session, message.from_user).language
    await message.answer(t(lang)["id_text"].format(id=message.from_user.id), parse_mode="Markdown")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    with session_scope() as session:
        lang = _get_or_create(session, message.from_user).language
    await message.answer(
        t(lang)["help"],
        parse_mode="Markdown",
        reply_markup=main_keyboard(lang, _is_admin(message.from_user.id)),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


@router.message(Command("language"))
async def cmd_language(message: Message) -> None:
    with session_scope() as session:
        lang = _get_or_create(session, message.from_user).language
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="עברית", callback_data="setlang:he"),
                InlineKeyboardButton(text="English", callback_data="setlang:en"),
            ]
        ]
    )
    await message.answer(t(lang)["choose_language"], reply_markup=keyboard)


@router.callback_query(F.data.startswith("setlang:"))
async def cb_setlang(callback: CallbackQuery) -> None:
    new_lang = normalize_lang(callback.data.split(":")[1])
    with session_scope() as session:
        user = _get_or_create(session, callback.from_user)
        user.language = new_lang
    tr = t(new_lang)
    try:
        await callback.message.edit_text(tr["language_set"])
    except Exception:
        pass
    await callback.answer()
    # Reply keyboards can't be swapped from a callback edit, so send a fresh one.
    await callback.bot.send_message(
        callback.from_user.id,
        tr["help"],
        parse_mode="Markdown",
        reply_markup=main_keyboard(new_lang, _is_admin(callback.from_user.id)),
    )


@router.message(Command("currency"))
async def cmd_currency(message: Message, command: CommandObject) -> None:
    code = (command.args or "").strip().upper()
    with session_scope() as session:
        user = _get_or_create(session, message.from_user)
        lang = user.language
        if not code or len(code) > 8:
            await message.answer(t(lang)["currency_usage"])
            return
        user.currency = code
    await message.answer(t(lang)["currency_set"].format(code=code))


@router.message(Command("report"))
async def cmd_report(message: Message, command: CommandObject) -> None:
    """Relay a user's bug report to the admin."""
    report = (command.args or "").strip()
    with session_scope() as session:
        lang = _get_or_create(session, message.from_user).language
        admin_lang = _admin_lang(session) if settings.admin_telegram_id else "he"
    tr = t(lang)
    if not report:
        await message.answer(tr["report_usage"], parse_mode="Markdown")
        return
    if not settings.admin_telegram_id:
        await message.answer(tr["report_unavailable"])
        return
    username = f"@{message.from_user.username}" if message.from_user.username else "—"
    name = _user_name(message.from_user) or str(message.from_user.id)
    try:
        await message.bot.send_message(
            settings.admin_telegram_id,
            t(admin_lang)["report_to_admin"].format(
                text=report, name=name, username=username, id=message.from_user.id
            ),
        )
    except Exception:
        await message.answer(tr["report_unavailable"])
        return
    await message.answer(tr["report_sent"])


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    with session_scope() as session:
        user = _get_or_create(session, message.from_user)
        lang, token = user.language, user.stats_token
    await message.answer(
        t(lang)["stats_link"].format(url=f"{settings.web_base_url}/stats/{token}"),
        disable_web_page_preview=True,
    )


# --- Lists & history -----------------------------------------------------------


def _list_price(sl: ShoppingList) -> float | None:
    """Price to show for a list: the real total once completed, else the prediction."""
    if sl.status == "completed" and sl.real_total is not None:
        return sl.real_total
    return sl.predicted_total or None


def _iso(text: str) -> str:
    """Wrap a left-to-right run in directional isolates (U+2066…U+2069) so digits and
    currency render cleanly inside a right-to-left (Hebrew) message."""
    return f"⁦{text}⁩"


def _render_lists(
    lists: list[ShoppingList], currency: str, title: str, tr: dict[str, str], rtl: bool
) -> str:
    if not lists:
        return f"*{title}*\n\n{tr['no_lists_period']}"
    lines = [f"*{title}*", ""]
    total = 0.0
    for idx, sl in enumerate(lists, 1):
        emoji = "✅" if sl.status == "completed" else "🟡"
        price = _list_price(sl)
        price_str = f"{price:.2f} {currency}" if price else "—"
        # The total reflects money actually spent, so only completed lists count.
        if sl.status == "completed" and sl.real_total is not None:
            total += sl.real_total
        num = _iso(f"{idx}.")
        meta = _iso(f"{sl.created_at:%Y-%m-%d} · {price_str}")
        link = f"[{tr['open_link']}]({settings.web_base_url}/list/{sl.web_token})"
        # RTL: lead with the link so the row reads naturally; the LTR meta is isolated.
        lines.append(f"{num} {emoji} {link} — {meta}" if rtl else f"{num} {emoji} {meta} — {link}")
    amount = f"*{_iso(f'{total:.2f} {currency}')}*"
    lines += ["", tr["total_spent"].format(amount=amount)]
    return "\n".join(lines)


def _lists_in_range(session, user_id: int, start: datetime, end: datetime) -> list[ShoppingList]:
    return (
        session.query(ShoppingList)
        .filter(
            ShoppingList.user_id == user_id,
            ShoppingList.created_at >= start,
            ShoppingList.created_at < end,
        )
        .order_by(ShoppingList.created_at.desc())
        .all()
    )


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = (
        datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=timezone.utc)
    )
    return start, end


def _grid(buttons: list[InlineKeyboardButton], per_row: int = 3) -> list[list[InlineKeyboardButton]]:
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


def _del_label(sl: ShoppingList, currency: str) -> str:
    price = _list_price(sl)
    suffix = f" · {price:.0f} {currency}" if price else ""
    return f"🗑 {sl.created_at:%d/%m}{suffix}"


def _lists_view(
    session, user: User, ctx: str, manage: bool = False
) -> tuple[str, InlineKeyboardMarkup]:
    """Render a month's lists. ``manage`` toggles delete mode.

    Default view stays clean (summary + nav + a single "🗑 Delete" button). Delete
    mode shows one delete button per list plus "✓ Done". ``ctx`` is "c" for the
    current month or "YYYY.M" for a history month; it is echoed into callbacks so the
    view re-renders correctly.
    """
    lang, currency, tr = user.language, user.currency, t(user.language)
    if ctx == "c":
        now = datetime.now(timezone.utc)
        year, month, current = now.year, now.month, True
    else:
        y, m = ctx.split(".")
        year, month, current = int(y), int(m), False
    start, end = _month_bounds(year, month)
    lists = _lists_in_range(session, user.id, start, end)
    period = f"{month_label(lang, month)} {_iso(str(year))}"
    text = _render_lists(lists, currency, tr["lists_title"].format(period=period), tr, lang == "he")

    rows: list[list[InlineKeyboardButton]] = []
    if manage:
        rows += [
            [InlineKeyboardButton(text=_del_label(sl, currency), callback_data=f"ld:{sl.id}:{ctx}")]
            for sl in lists
        ]
        rows.append([InlineKeyboardButton(text=tr["btn_done"], callback_data=f"lv:{ctx}")])
    else:
        if lists:
            rows.append(
                [InlineKeyboardButton(text=tr["btn_delete_list"], callback_data=f"lm:{ctx}")]
            )
        if current:
            rows.append([InlineKeyboardButton(text=tr["history_btn"], callback_data="hist:years")])
        else:
            rows.append(
                [InlineKeyboardButton(text=tr["back_months"], callback_data=f"hist:y:{year}")]
            )
            rows.append([InlineKeyboardButton(text=tr["back_years"], callback_data="hist:years")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("lists"))
async def cmd_lists(message: Message) -> None:
    with session_scope() as session:
        user = _get_or_create(session, message.from_user)
        text, kb = _lists_view(session, user, "c")
    await message.answer(
        text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=kb
    )


def _years_view(session, user: User, manage: bool = False):
    """Year picker. Normal: year buttons + 🗑 Delete. Manage: delete-a-year buttons."""
    tr = t(user.language)
    year_col = extract("year", ShoppingList.created_at)
    years = [
        int(r[0])
        for r in session.query(year_col)
        .filter(ShoppingList.user_id == user.id)
        .distinct()
        .order_by(year_col.desc())
        .all()
    ]
    if not years:
        return None, None
    if manage:
        rows = [[InlineKeyboardButton(text=f"🗑 {y}", callback_data=f"yd:{y}")] for y in years]
        rows.append([InlineKeyboardButton(text=tr["btn_done"], callback_data="hist:years")])
    else:
        rows = _grid([InlineKeyboardButton(text=str(y), callback_data=f"hist:y:{y}") for y in years])
        rows.append([InlineKeyboardButton(text=tr["btn_delete_year"], callback_data="ym")])
    return tr["select_year"], InlineKeyboardMarkup(inline_keyboard=rows)


def _months_view(session, user: User, year: int, manage: bool = False):
    """Month picker for a year. Normal: month buttons + 🗑 Delete. Manage: delete-a-month."""
    lang = user.language
    tr = t(lang)
    month_col = extract("month", ShoppingList.created_at)
    year_col = extract("year", ShoppingList.created_at)
    months = [
        int(r[0])
        for r in session.query(month_col)
        .filter(ShoppingList.user_id == user.id, year_col == year)
        .distinct()
        .order_by(month_col)
        .all()
    ]
    if not months:
        return None, None
    if manage:
        rows = [
            [InlineKeyboardButton(text=f"🗑 {month_short(lang, m)}", callback_data=f"md:{year}.{m}")]
            for m in months
        ]
        rows.append([InlineKeyboardButton(text=tr["btn_done"], callback_data=f"hist:y:{year}")])
    else:
        rows = _grid(
            [
                InlineKeyboardButton(text=month_short(lang, m), callback_data=f"hist:m:{year}:{m}")
                for m in months
            ]
        )
        rows.append([InlineKeyboardButton(text=tr["btn_delete_month"], callback_data=f"mm:{year}")])
        rows.append([InlineKeyboardButton(text=tr["back_years"], callback_data="hist:years")])
    return tr["select_month"].format(year=year), InlineKeyboardMarkup(inline_keyboard=rows)


async def _edit(callback: CallbackQuery, text: str, kb, markdown: bool = True) -> None:
    try:
        await callback.message.edit_text(
            text, parse_mode="Markdown" if markdown else None, reply_markup=kb
        )
    except Exception:
        pass


@router.callback_query(F.data == "hist:years")
async def cb_hist_years(callback: CallbackQuery) -> None:
    with session_scope() as session:
        user = _get_or_create(session, callback.from_user)
        tr = t(user.language)
        text, kb = _years_view(session, user)
    if text is None:
        await callback.answer(tr["no_history"], show_alert=True)
        return
    await _edit(callback, text, kb)
    await callback.answer()


@router.callback_query(F.data == "ym")
async def cb_year_manage(callback: CallbackQuery) -> None:
    with session_scope() as session:
        user = _get_or_create(session, callback.from_user)
        text, kb = _years_view(session, user, manage=True)
    if text is not None:
        await _edit(callback, text, kb)
    await callback.answer()


@router.callback_query(F.data.startswith("yd:"))
async def cb_year_del(callback: CallbackQuery) -> None:
    year = int(callback.data.split(":")[1])
    with session_scope() as session:
        tr = t(_get_or_create(session, callback.from_user).language)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=tr["btn_yes"], callback_data=f"ydy:{year}"),
                InlineKeyboardButton(text=tr["btn_no"], callback_data="ym"),
            ]
        ]
    )
    await _edit(callback, tr["confirm_delete_year"].format(year=year), kb)
    await callback.answer()


@router.callback_query(F.data.startswith("ydy:"))
async def cb_year_delyes(callback: CallbackQuery) -> None:
    year = int(callback.data.split(":")[1])
    with session_scope() as session:
        user = _get_or_create(session, callback.from_user)
        tr = t(user.language)
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        count = delete_lists_in_range(session, user.id, start, end)
        text, kb = _years_view(session, user, manage=True)
        if text is None:
            text, kb = tr["no_history"], None
    await _edit(callback, text, kb)
    await callback.answer(tr["lists_deleted"].format(n=count))


@router.callback_query(F.data.startswith("hist:y:"))
async def cb_hist_year(callback: CallbackQuery) -> None:
    year = int(callback.data.split(":")[2])
    with session_scope() as session:
        user = _get_or_create(session, callback.from_user)
        text, kb = _months_view(session, user, year)
    if text is None:
        await cb_hist_years(callback)  # year now empty -> back to years
        return
    await _edit(callback, text, kb)
    await callback.answer()


@router.callback_query(F.data.startswith("mm:"))
async def cb_month_manage(callback: CallbackQuery) -> None:
    year = int(callback.data.split(":")[1])
    with session_scope() as session:
        user = _get_or_create(session, callback.from_user)
        tr = t(user.language)
        text, kb = _months_view(session, user, year, manage=True)
        if text is None:
            text, kb = tr["no_history"], None
    await _edit(callback, text, kb)
    await callback.answer()


@router.callback_query(F.data.startswith("md:"))
async def cb_month_del(callback: CallbackQuery) -> None:
    ym = callback.data.split(":", 1)[1]  # "YYYY.M"
    year_s, month_s = ym.split(".")
    with session_scope() as session:
        lang = _get_or_create(session, callback.from_user).language
    tr = t(lang)
    period = f"{month_label(lang, int(month_s))} {year_s}"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=tr["btn_yes"], callback_data=f"mdy:{ym}"),
                InlineKeyboardButton(text=tr["btn_no"], callback_data=f"mm:{year_s}"),
            ]
        ]
    )
    await _edit(callback, tr["confirm_delete_month"].format(period=period), kb)
    await callback.answer()


@router.callback_query(F.data.startswith("mdy:"))
async def cb_month_delyes(callback: CallbackQuery) -> None:
    year, month = (int(x) for x in callback.data.split(":", 1)[1].split("."))
    with session_scope() as session:
        user = _get_or_create(session, callback.from_user)
        tr = t(user.language)
        start, end = _month_bounds(year, month)
        count = delete_lists_in_range(session, user.id, start, end)
        text, kb = _months_view(session, user, year, manage=True)
        if text is None:  # year may now be empty
            text, kb = _years_view(session, user)
            if text is None:
                text, kb = tr["no_history"], None
    await _edit(callback, text, kb)
    await callback.answer(tr["lists_deleted"].format(n=count))


@router.callback_query(F.data.startswith("hist:m:"))
async def cb_hist_month(callback: CallbackQuery) -> None:
    _, _, year_s, month_s = callback.data.split(":")
    with session_scope() as session:
        user = _get_or_create(session, callback.from_user)
        text, kb = _lists_view(session, user, f"{int(year_s)}.{int(month_s)}")
    try:
        await callback.message.edit_text(
            text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=kb
        )
    except Exception:
        pass
    await callback.answer()


async def _edit_lists_view(callback: CallbackQuery, ctx: str, manage: bool) -> None:
    with session_scope() as session:
        user = _get_or_create(session, callback.from_user)
        text, kb = _lists_view(session, user, ctx, manage)
    try:
        await callback.message.edit_text(
            text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=kb
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("lm:"))
async def cb_list_manage(callback: CallbackQuery) -> None:
    """Enter delete mode for a month's lists."""
    await _edit_lists_view(callback, callback.data.split(":", 1)[1], manage=True)
    await callback.answer()


@router.callback_query(F.data.startswith("lv:"))
async def cb_list_view(callback: CallbackQuery) -> None:
    """Leave delete mode (back to the clean view)."""
    await _edit_lists_view(callback, callback.data.split(":", 1)[1], manage=False)
    await callback.answer()


@router.callback_query(F.data.startswith("ld:"))
async def cb_list_del(callback: CallbackQuery) -> None:
    _, id_s, ctx = callback.data.split(":", 2)
    list_id = int(id_s)
    with session_scope() as session:
        tr = t(_get_or_create(session, callback.from_user).language)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=tr["btn_yes"], callback_data=f"ldy:{list_id}:{ctx}"),
                InlineKeyboardButton(text=tr["btn_no"], callback_data=f"lm:{ctx}"),
            ]
        ]
    )
    try:
        await callback.message.edit_text(tr["confirm_delete_list"], reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("ldy:"))
async def cb_list_delyes(callback: CallbackQuery) -> None:
    _, id_s, ctx = callback.data.split(":", 2)
    list_id = int(id_s)
    with session_scope() as session:
        user = _get_or_create(session, callback.from_user)
        tr = t(user.language)
        sl = session.get(ShoppingList, list_id)
        if sl is not None and sl.user_id == user.id:  # owner check
            session.delete(sl)
            session.flush()
        text, kb = _lists_view(session, user, ctx, manage=True)
    try:
        await callback.message.edit_text(
            text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=kb
        )
    except Exception:
        pass
    await callback.answer(tr["list_deleted"])


# --- Reply-keyboard buttons (registered before the free-text list parser) ------


@router.message(F.text.in_(button_labels("btn_lists")))
async def btn_lists(message: Message) -> None:
    await cmd_lists(message)


@router.message(F.text.in_(button_labels("btn_stats")))
async def btn_stats(message: Message) -> None:
    await cmd_stats(message)


@router.message(F.text.in_(button_labels("btn_help")))
async def btn_help(message: Message) -> None:
    await cmd_start(message)


@router.message(F.text.in_(button_labels("btn_language")))
async def btn_language(message: Message) -> None:
    await cmd_language(message)


@router.message(F.text.in_(button_labels("btn_users")))
async def btn_users(message: Message) -> None:
    await cmd_users(message)


@router.message(F.text.in_(button_labels("btn_report")))
async def btn_report(message: Message) -> None:
    with session_scope() as session:
        lang = _get_or_create(session, message.from_user).language
    await message.answer(t(lang)["report_usage"], parse_mode="Markdown")


@router.message(F.text.in_(button_labels("btn_currency")))
async def btn_currency(message: Message) -> None:
    with session_scope() as session:
        user = _get_or_create(session, message.from_user)
        lang, current = user.language, user.currency
    await message.answer(t(lang)["currency_current"].format(cur=current), parse_mode="Markdown")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_list_text(message: Message) -> None:
    with session_scope() as session:
        user = _get_or_create(session, message.from_user)
        lang, currency = user.language, user.currency
        tr = t(lang)
        shopping_list = create_list_from_text(session, user, message.text)
        if shopping_list is None:
            await message.answer(tr["no_items_found"])
            return
        count = len(shopping_list.items)
        with_price = sum(1 for i in shopping_list.items if i.predicted_price is not None)
        without_price = count - with_price
        predicted = shopping_list.predicted_total
        token = shopping_list.web_token
        list_id = shopping_list.id
        pending = _pending_rows(session, user.id)

    text = [tr["added"].format(count=count)]
    if predicted > 0:
        amount = f"*{_iso(f'{predicted:.2f} {currency}')}*"
        text.append(tr["predicted_total"].format(amount=amount))
    text.append(
        tr["price_breakdown"].format(with_price=_iso(with_price), without_price=_iso(without_price))
    )
    text.append(f"\n{tr['open_your_list']}\n{settings.web_base_url}/list/{token}")
    await message.answer("\n".join(text), parse_mode="Markdown", disable_web_page_preview=True)

    # Offer carried-over items (saved when an earlier list was ended early).
    if pending:
        await message.answer(
            tr["pending_intro"], reply_markup=_pending_keyboard(pending, list_id, tr)
        )


# --- Carried-over (pending) items ----------------------------------------------


def _pending_rows(session, user_id: int) -> list[tuple[int, str]]:
    return [
        (p.id, p.raw_name)
        for p in session.scalars(
            select(PendingItem)
            .where(PendingItem.user_id == user_id)
            .order_by(PendingItem.created_at)
        ).all()
    ]


def _pending_keyboard(
    rows: list[tuple[int, str]], list_id: int, tr: dict[str, str]
) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"➕ {name}", callback_data=f"pend:add:{pid}:{list_id}")]
        for pid, name in rows
    ]
    buttons.append(
        [InlineKeyboardButton(text=tr["btn_clear_pending"], callback_data=f"pend:clear:{list_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data.startswith("pend:add:"))
async def cb_pend_add(callback: CallbackQuery) -> None:
    _, _, pid_s, list_id_s = callback.data.split(":")
    pid, list_id = int(pid_s), int(list_id_s)
    with session_scope() as session:
        user = _get_or_create(session, callback.from_user)
        tr = t(user.language)
        pending = session.get(PendingItem, pid)
        sl = session.get(ShoppingList, list_id)
        if pending and sl and pending.user_id == user.id and sl.user_id == user.id:
            add_item_from_pending(session, sl, pending)
            session.delete(pending)
            session.flush()  # so the removed item drops out of the rebuilt keyboard
        rows = _pending_rows(session, user.id)
        # When the last carry-over item is added, list everything that was added.
        added = [] if rows else _added_from_carryover(session, list_id)
    await callback.answer(tr["pending_added"])
    try:
        if rows:
            await callback.message.edit_reply_markup(
                reply_markup=_pending_keyboard(rows, list_id, tr)
            )
        elif added:
            items = "\n".join(f"• {name}" for name in added)
            await callback.message.edit_text(tr["pending_added_list"].format(items=items))
        else:
            await callback.message.edit_text(tr["pending_done"])
    except Exception:
        pass


def _added_from_carryover(session, list_id: int) -> list[str]:
    """Names of items in a list that were added from carried-over (pending) items."""
    return [
        i.raw_name
        for i in session.scalars(
            select(Item)
            .where(Item.list_id == list_id, Item.from_pending.is_(True))
            .order_by(Item.sort_order)
        ).all()
    ]


@router.callback_query(F.data.startswith("pend:clear"))
async def cb_pend_clear(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    list_id = int(parts[2]) if len(parts) > 2 else None
    with session_scope() as session:
        user = _get_or_create(session, callback.from_user)
        tr = t(user.language)
        # Clears pending and removes any carry-over items already added to this list.
        discard_carryover(session, user.id, list_id)
    await callback.answer()
    try:
        await callback.message.edit_text(tr["pending_cleared"])
    except Exception:
        pass


# --- Admin: user management ----------------------------------------------------


def _users_view(session, lang: str) -> tuple[str, InlineKeyboardMarkup | None]:
    """Build the registered-users list with a delete button per non-admin user."""
    tr = t(lang)
    users = session.scalars(select(User).order_by(User.created_at)).all()
    if not users:
        return tr["users_none"], None
    lines = [tr["users_header"]]
    buttons: list[list[InlineKeyboardButton]] = []
    for u in users:
        is_admin_user = _is_admin(u.telegram_id)
        name = u.display_name or str(u.telegram_id)
        marker = "👑" if is_admin_user else "👤"
        lines.append(f"{marker} {name} · {_iso(str(u.telegram_id))}")
        if not is_admin_user:
            buttons.append(
                [InlineKeyboardButton(text=f"🗑 {name}", callback_data=f"usr:del:{u.id}")]
            )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    return "\n".join(lines), kb


@router.message(Command("users"))
async def cmd_users(message: Message) -> None:
    """Admin: list all users with a delete option."""
    if not _is_admin(message.from_user.id):
        return
    with session_scope() as session:
        lang = _get_or_create(session, message.from_user).language
        text, kb = _users_view(session, lang)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("usr:del:"))
async def cb_usr_del(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(t(None)["not_allowed"], show_alert=True)
        return
    uid = int(callback.data.split(":")[2])
    with session_scope() as session:
        tr = t(_get_or_create(session, callback.from_user).language)
        target = session.get(User, uid)
        name = (target.display_name if target else None) or str(uid)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=tr["btn_yes"], callback_data=f"usr:delyes:{uid}"),
                InlineKeyboardButton(text=tr["btn_no"], callback_data="usr:list"),
            ]
        ]
    )
    try:
        await callback.message.edit_text(
            tr["confirm_delete_user"].format(name=name), reply_markup=keyboard
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("usr:delyes:"))
async def cb_usr_delyes(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(t(None)["not_allowed"], show_alert=True)
        return
    uid = int(callback.data.split(":")[2])
    with session_scope() as session:
        lang = _get_or_create(session, callback.from_user).language
        tr = t(lang)
        target = session.get(User, uid)
        deleted_name = None
        if target is not None and not _is_admin(target.telegram_id):
            deleted_name = target.display_name or str(target.telegram_id)
            session.delete(target)  # cascades to lists, items, pending, price history
            session.flush()
        text, kb = _users_view(session, lang)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback.answer(tr["user_deleted"].format(name=deleted_name) if deleted_name else "")


@router.callback_query(F.data == "usr:list")
async def cb_usr_list(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(t(None)["not_allowed"], show_alert=True)
        return
    with session_scope() as session:
        lang = _get_or_create(session, callback.from_user).language
        text, kb = _users_view(session, lang)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()


# --- Approval / access control -------------------------------------------------


@router.message(Command("pending"))
async def cmd_pending(message: Message) -> None:
    """Admin: re-list users awaiting approval (in case a notification was missed)."""
    if not _is_admin(message.from_user.id):
        return
    with session_scope() as session:
        lang = _get_or_create(session, message.from_user).language
        tr = t(lang)
        rows = [
            (u.telegram_id, u.display_name or str(u.telegram_id))
            for u in session.scalars(
                select(User).where(User.is_approved.is_(False)).order_by(User.created_at)
            ).all()
        ]
    if not rows:
        await message.answer(tr["no_pending"])
        return
    for telegram_id, name in rows:
        await message.answer(
            tr["pending_entry"].format(name=name, id=telegram_id),
            reply_markup=_approval_keyboard(telegram_id, lang),
        )


@router.callback_query(F.data.startswith("approve:"))
async def cb_approve(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(t(None)["not_allowed"], show_alert=True)
        return
    target_id = int(callback.data.split(":", 1)[1])
    with session_scope() as session:
        admin_lang = _get_or_create(session, callback.from_user).language
        tr = t(admin_lang)
        user = session.scalar(select(User).where(User.telegram_id == target_id))
        if user is None:
            await callback.answer(tr["user_not_found"], show_alert=True)
            return
        user.is_approved = True
        name = user.display_name or str(target_id)
        target_lang = user.language
    try:
        await callback.message.edit_text(tr["approved_admin"].format(name=name, id=target_id))
    except Exception:
        pass
    await callback.answer(tr["approved_toast"])
    try:
        await callback.bot.send_message(
            target_id,
            t(target_lang)["approved_user"],
            reply_markup=main_keyboard(target_lang, _is_admin(target_id)),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("deny:"))
async def cb_deny(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(t(None)["not_allowed"], show_alert=True)
        return
    target_id = int(callback.data.split(":", 1)[1])
    with session_scope() as session:
        admin_lang = _get_or_create(session, callback.from_user).language
        tr = t(admin_lang)
        user = session.scalar(select(User).where(User.telegram_id == target_id))
        name = (user.display_name if user else None) or str(target_id)
    try:
        await callback.message.edit_text(tr["denied_admin"].format(name=name, id=target_id))
    except Exception:
        pass
    await callback.answer(tr["denied_toast"])


class ApprovalMiddleware(BaseMiddleware):
    """Block messages from users who haven't been approved by the admin.

    Disabled while ``admin_telegram_id`` is unset (0): everyone passes through.
    The admin is always allowed and is notified once when a new user appears.
    """

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        tg_user = event.from_user
        if not settings.admin_telegram_id or tg_user is None:
            return await handler(event, data)

        with session_scope() as session:
            user = session.scalar(select(User).where(User.telegram_id == tg_user.id))
            is_new = user is None
            if is_new:
                user = User(
                    telegram_id=tg_user.id,
                    display_name=tg_user.full_name or tg_user.username,
                    currency=settings.default_currency,
                    is_approved=_is_admin(tg_user.id),
                )
                session.add(user)
                session.flush()
            approved = user.is_approved
            lang = user.language
            admin_lang = _admin_lang(session)

        if approved:
            return await handler(event, data)

        if is_new:
            username = f"@{tg_user.username}" if tg_user.username else "—"
            name = tg_user.full_name or tg_user.username or str(tg_user.id)
            try:
                await data["bot"].send_message(
                    settings.admin_telegram_id,
                    t(admin_lang)["new_user_admin"].format(
                        name=name, username=username, id=tg_user.id
                    ),
                    reply_markup=_approval_keyboard(tg_user.id, admin_lang),
                )
            except Exception:
                pass
        await event.answer(t(lang)["pending"])
        return None

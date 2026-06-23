"""Telegram bot command and message handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from app.config import get_settings
from app.db import session_scope
from app.models import ShoppingList
from app.services import create_list_from_text, get_or_create_user

router = Router()
settings = get_settings()

HELP_TEXT = (
    "🛒 *Shopping List Bot*\n\n"
    "Send me your shopping list — one item per line (or comma separated). "
    "I'll sort it into categories and give you a web link.\n\n"
    "Examples:\n"
    "`2 milk`\n`bread`\n`tomatoes x3`\n\n"
    "Commands:\n"
    "/lists — your recent lists\n"
    "/stats — spending statistics\n"
    "/currency USD — set your currency"
)


def _display_name(message: Message) -> str | None:
    user = message.from_user
    if user is None:
        return None
    return user.full_name or user.username


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    with session_scope() as session:
        get_or_create_user(
            session, message.from_user.id, _display_name(message), settings.default_currency
        )
    await message.answer(HELP_TEXT, parse_mode="Markdown")


@router.message(Command("currency"))
async def cmd_currency(message: Message, command: CommandObject) -> None:
    code = (command.args or "").strip().upper()
    if not code or len(code) > 8:
        await message.answer("Usage: /currency USD")
        return
    with session_scope() as session:
        user = get_or_create_user(
            session, message.from_user.id, _display_name(message), settings.default_currency
        )
        user.currency = code
    await message.answer(f"Currency set to {code}.")


@router.message(Command("lists"))
async def cmd_lists(message: Message) -> None:
    with session_scope() as session:
        user = get_or_create_user(
            session, message.from_user.id, _display_name(message), settings.default_currency
        )
        lists = (
            session.query(ShoppingList)
            .filter(ShoppingList.user_id == user.id)
            .order_by(ShoppingList.created_at.desc())
            .limit(10)
            .all()
        )
        if not lists:
            await message.answer("No lists yet. Send me some items to start one!")
            return
        lines = ["*Your recent lists:*"]
        for sl in lists:
            status = "✅" if sl.status == "completed" else "🟡"
            lines.append(
                f"{status} {sl.created_at:%Y-%m-%d} — "
                f"[open]({settings.web_base_url}/list/{sl.web_token})"
            )
    await message.answer("\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    with session_scope() as session:
        user = get_or_create_user(
            session, message.from_user.id, _display_name(message), settings.default_currency
        )
        token = user.stats_token
    await message.answer(
        f"📊 Your statistics: {settings.web_base_url}/stats/{token}",
        disable_web_page_preview=True,
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_list_text(message: Message) -> None:
    with session_scope() as session:
        user = get_or_create_user(
            session, message.from_user.id, _display_name(message), settings.default_currency
        )
        shopping_list = create_list_from_text(session, user, message.text)
        if shopping_list is None:
            await message.answer("I couldn't find any items in that message.")
            return
        count = len(shopping_list.items)
        predicted = shopping_list.predicted_total
        token = shopping_list.web_token
        currency = user.currency

    text = [f"✅ Added {count} item(s) and sorted them by category."]
    if predicted > 0:
        text.append(f"Predicted total: *{predicted:.2f} {currency}*")
    text.append(f"\nOpen your list:\n{settings.web_base_url}/list/{token}")
    await message.answer(
        "\n".join(text), parse_mode="Markdown", disable_web_page_preview=True
    )

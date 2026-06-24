"""Telegram bot entrypoint (long polling)."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot.handlers import ApprovalMiddleware, router
from app.bot.i18n import BOT_COMMANDS
from app.config import get_settings


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not set")

    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher()
    dispatcher.message.middleware(ApprovalMiddleware())
    dispatcher.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    # Hebrew is the default command menu; English shows for en-locale Telegram clients.
    await bot.set_my_commands(BOT_COMMANDS["he"])
    await bot.set_my_commands(BOT_COMMANDS["en"], language_code="en")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

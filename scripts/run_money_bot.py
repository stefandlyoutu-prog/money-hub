#!/usr/bin/env python3
"""Локальный polling для Money Hub бота (без webhook)."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from business_dashboard.config import MONEY_BOT_TOKEN  # noqa: E402
from business_dashboard.storage import init_db  # noqa: E402
from money_bot.handlers import router  # noqa: E402
from money_bot.telegram_net import create_telegram_session  # noqa: E402


async def main() -> None:
    if not MONEY_BOT_TOKEN:
        print("Задай MONEY_BOT_TOKEN в .env")
        sys.exit(1)
    init_db()
    bot = Bot(
        token=MONEY_BOT_TOKEN,
        session=create_telegram_session(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    me = await bot.get_me()
    print(f"Money Hub polling: @{me.username}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

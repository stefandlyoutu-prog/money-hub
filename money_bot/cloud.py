"""Облако: webhook Telegram + Money Hub бот."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import MenuButtonWebApp, Update, WebAppInfo
from fastapi import APIRouter, Request

from business_dashboard.config import (
    MONEY_BOT_TOKEN,
    money_cloud_enabled,
    public_miniapp_url,
)
from money_bot.handlers import router as money_router
from money_bot.telegram_net import create_telegram_session

logger = logging.getLogger("money_bot.cloud")

_bot: Optional[Bot] = None
_dp: Optional[Dispatcher] = None

router_cloud = APIRouter()


async def start_cloud() -> None:
    global _bot, _dp
    if not MONEY_BOT_TOKEN:
        logger.warning("MONEY_BOT_TOKEN не задан — бот не запущен")
        return
    _bot = Bot(
        token=MONEY_BOT_TOKEN,
        session=create_telegram_session(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    _dp = Dispatcher(storage=MemoryStorage())
    _dp.include_router(money_router)
    me = await _bot.get_me()
    logger.info("Money Hub bot: @%s", me.username)

    mini = public_miniapp_url()
    if mini.startswith("https://"):
        try:
            await _bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Money Hub",
                    web_app=WebAppInfo(url=mini),
                )
            )
            logger.info("Mini App menu: %s", mini)
        except Exception as e:
            logger.warning("Mini App menu: %s", e)

    webhook_base = os.getenv("MONEY_WEBHOOK_URL", "").strip() or os.getenv(
        "RENDER_EXTERNAL_URL", ""
    ).strip()
    if not webhook_base:
        logger.warning("Webhook URL не задан — только polling локально")
        return
    webhook_url = webhook_base.rstrip("/") + "/webhook"
    await _bot.delete_webhook(drop_pending_updates=True)
    await _bot.set_webhook(webhook_url, drop_pending_updates=True)
    logger.info("Webhook: %s", webhook_url)


async def stop_cloud() -> None:
    global _bot
    if _bot:
        try:
            await _bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            pass
        await _bot.session.close()
        _bot = None


@router_cloud.post("/webhook")
async def telegram_webhook(request: Request):
    if not _bot or not _dp:
        return {"ok": False, "error": "bot not started"}
    data = await request.json()
    update = Update.model_validate(data)
    asyncio.create_task(_dp.feed_update(_bot, update))
    return {"ok": True}


@router_cloud.get("/health")
async def health():
    return {
        "ok": True,
        "cloud": money_cloud_enabled(),
        "miniapp": public_miniapp_url(),
    }

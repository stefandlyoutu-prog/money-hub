"""Облако: webhook Telegram + Money Hub бот."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

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
from money_bot.handlers_remote import router as remote_router
from money_bot.handlers import router as money_router
from money_bot.telegram_net import create_telegram_session

logger = logging.getLogger("money_bot.cloud")

_bot: Optional[Bot] = None
_dp: Optional[Dispatcher] = None
_webhook_url: str = ""
_bot_username: str = ""

router_cloud = APIRouter()


def bot_ready() -> bool:
    return _bot is not None and _dp is not None


def bot_info() -> dict[str, Any]:
    return {
        "ready": bot_ready(),
        "username": _bot_username,
        "webhook": _webhook_url,
        "token_set": bool(MONEY_BOT_TOKEN),
    }


async def _ensure_webhook(bot: Bot, url: str, *, retries: int = 5) -> bool:
    global _webhook_url
    for attempt in range(retries):
        try:
            await bot.set_webhook(url, drop_pending_updates=False)
            info = await bot.get_webhook_info()
            if info.url == url:
                _webhook_url = url
                logger.info("Webhook OK: %s", url)
                return True
            logger.warning("Webhook mismatch: %s != %s", info.url, url)
        except Exception as e:
            logger.warning("set_webhook attempt %s: %s", attempt + 1, e)
        await asyncio.sleep(2.0 * (attempt + 1))
    return False


async def start_cloud() -> None:
    global _bot, _dp, _bot_username, _webhook_url
    if not MONEY_BOT_TOKEN:
        logger.warning("MONEY_BOT_TOKEN не задан — бот не запущен")
        return
    try:
        _bot = Bot(
            token=MONEY_BOT_TOKEN,
            session=create_telegram_session(),
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        _dp = Dispatcher(storage=MemoryStorage())
        # Remote (голос, /cmd) — первым, чтобы не перехватили другие хендлеры
        _dp.include_router(remote_router)
        _dp.include_router(money_router)

        @_dp.errors()
        async def on_error(event):  # type: ignore[no-untyped-def]
            logger.exception("Telegram handler error: %s", getattr(event, "exception", event))

        me = await _bot.get_me()
        _bot_username = me.username or ""
        logger.info("Money Hub bot: @%s", _bot_username)

        mini = public_miniapp_url()
        if mini.startswith("https://"):
            try:
                await _bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(
                        text="Money Hub",
                        web_app=WebAppInfo(url=mini),
                    )
                )
            except Exception as e:
                logger.warning("Mini App menu: %s", e)

        webhook_base = os.getenv("MONEY_WEBHOOK_URL", "").strip() or os.getenv(
            "RENDER_EXTERNAL_URL", ""
        ).strip()
        if not webhook_base:
            logger.warning("RENDER_EXTERNAL_URL не задан — webhook не установлен")
            return
        webhook_url = webhook_base.rstrip("/") + "/webhook"
        ok = await _ensure_webhook(_bot, webhook_url)
        if not ok:
            logger.error("Не удалось установить webhook после %s попыток", 5)
    except Exception as e:
        logger.exception("Money Hub bot не запустился: %s", e)
        if _bot:
            try:
                await _bot.session.close()
            except Exception:
                pass
        _bot = None
        _dp = None


async def maintain_webhook() -> bool:
    """Периодически восстанавливает webhook если слетел."""
    if not _bot or not _webhook_url:
        return False
    try:
        info = await _bot.get_webhook_info()
        if info.url == _webhook_url:
            return True
        logger.warning("Webhook lost (%s), restoring…", info.url)
        return await _ensure_webhook(_bot, _webhook_url, retries=3)
    except Exception as e:
        logger.warning("maintain_webhook: %s", e)
        return False


async def stop_cloud() -> None:
    global _bot, _dp
    # Не удаляем webhook при redeploy — иначе бот «молчит» до ручного fix
    if _bot:
        try:
            await _bot.session.close()
        except Exception:
            pass
    _bot = None
    _dp = None


@router_cloud.post("/webhook")
async def telegram_webhook(request: Request):
    if not _bot or not _dp:
        logger.error("webhook hit but bot not ready")
        return {"ok": False, "error": "bot not started"}
    try:
        data = await request.json()
        update = Update.model_validate(data)
        await _dp.feed_update(_bot, update)
    except Exception as e:
        logger.exception("webhook processing failed: %s", e)
        return {"ok": False, "error": str(e)[:200]}
    return {"ok": True}


@router_cloud.get("/health")
async def health():
    return {
        "ok": True,
        "cloud": money_cloud_enabled(),
        "miniapp": public_miniapp_url(),
        "bot": bot_info(),
    }

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
from money_bot.bot_tokens import bot_slots, usernames
from money_bot.handlers_remote import router as remote_router
from money_bot.handlers import router as money_router
from money_bot.telegram_net import create_telegram_session

logger = logging.getLogger("money_bot.cloud")

_bots: dict[str, Bot] = {}
_webhook_urls: dict[str, str] = {}
_dp: Optional[Dispatcher] = None

router_cloud = APIRouter()


def bot_ready() -> bool:
    return bool(_bots) and _dp is not None


def bot_info() -> dict[str, Any]:
    names = usernames()
    return {
        "ready": bot_ready(),
        "bots": [
            {
                "slot": slot,
                "username": names.get(slot, ""),
                "webhook": _webhook_urls.get(slot, ""),
            }
            for slot in sorted(_bots)
        ],
        "token_set": bool(MONEY_BOT_TOKEN),
    }


async def _ensure_webhook(bot: Bot, url: str, *, retries: int = 5) -> bool:
    for attempt in range(retries):
        try:
            await bot.set_webhook(url, drop_pending_updates=False)
            info = await bot.get_webhook_info()
            if info.url == url:
                logger.info("Webhook OK: %s", url)
                return True
            logger.warning("Webhook mismatch: %s != %s", info.url, url)
        except Exception as e:
            logger.warning("set_webhook attempt %s: %s", attempt + 1, e)
        await asyncio.sleep(2.0 * (attempt + 1))
    return False


async def _start_one_bot(slot: str, token: str, webhook_url: str) -> None:
    bot = Bot(
        token=token,
        session=create_telegram_session(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    me = await bot.get_me()
    username = me.username or usernames().get(slot, "")
    logger.info("Money Hub bot [%s]: @%s", slot, username)

    if slot == "1":
        mini = public_miniapp_url()
        if mini.startswith("https://"):
            try:
                await bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(
                        text="Money Hub",
                        web_app=WebAppInfo(url=mini),
                    )
                )
            except Exception as e:
                logger.warning("Mini App menu: %s", e)

    ok = await _ensure_webhook(bot, webhook_url)
    if not ok:
        logger.error("Не удалось webhook для бота slot=%s", slot)
    else:
        _webhook_urls[slot] = webhook_url
    _bots[slot] = bot


async def start_cloud() -> None:
    global _dp
    tokens = bot_slots()
    if not tokens:
        logger.warning("MONEY_BOT_TOKEN не задан — бот не запущен")
        return
    try:
        _dp = Dispatcher(storage=MemoryStorage())
        _dp.include_router(remote_router)
        _dp.include_router(money_router)

        @_dp.errors()
        async def on_error(event):  # type: ignore[no-untyped-def]
            logger.exception("Telegram handler error: %s", getattr(event, "exception", event))

        webhook_base = os.getenv("MONEY_WEBHOOK_URL", "").strip() or os.getenv(
            "RENDER_EXTERNAL_URL", ""
        ).strip()
        if not webhook_base:
            logger.warning("RENDER_EXTERNAL_URL не задан — webhook не установлен")
            return
        base = webhook_base.rstrip("/")
        for slot, token in tokens.items():
            path = "/webhook" if slot == "1" else f"/webhook/{slot}"
            await _start_one_bot(slot, token, base + path)
    except Exception as e:
        logger.exception("Money Hub bot не запустился: %s", e)
        await stop_cloud()


async def maintain_webhook() -> bool:
    """Периодически восстанавливает webhook если слетел."""
    ok_all = True
    for slot, bot in _bots.items():
        url = _webhook_urls.get(slot, "")
        if not url:
            ok_all = False
            continue
        try:
            info = await bot.get_webhook_info()
            if info.url == url:
                continue
            logger.warning("Webhook lost slot=%s (%s), restoring…", slot, info.url)
            if not await _ensure_webhook(bot, url, retries=3):
                ok_all = False
            else:
                _webhook_urls[slot] = url
        except Exception as e:
            logger.warning("maintain_webhook slot=%s: %s", slot, e)
            ok_all = False
    return ok_all


def get_bot_for_slot(slot: str = "1") -> Bot | None:
    return _bots.get(slot) or _bots.get("1")


async def stop_cloud() -> None:
    global _dp
    for bot in _bots.values():
        try:
            await bot.session.close()
        except Exception:
            pass
    _bots.clear()
    _webhook_urls.clear()
    _dp = None


async def _feed_webhook(slot: str, request: Request) -> dict[str, Any]:
    bot = _bots.get(slot)
    if not bot or not _dp:
        logger.error("webhook/%s hit but bot not ready", slot)
        return {"ok": False, "error": "bot not started"}
    try:
        data = await request.json()
        update = Update.model_validate(data)
        await _dp.feed_update(bot, update)
    except Exception as e:
        logger.exception("webhook/%s processing failed: %s", slot, e)
        return {"ok": False, "error": str(e)[:200]}
    return {"ok": True}


@router_cloud.post("/webhook")
async def telegram_webhook(request: Request):
    return await _feed_webhook("1", request)


@router_cloud.post("/webhook/2")
async def telegram_webhook_2(request: Request):
    return await _feed_webhook("2", request)


@router_cloud.get("/health")
async def health():
    return {
        "ok": True,
        "cloud": money_cloud_enabled(),
        "miniapp": public_miniapp_url(),
        "bot": bot_info(),
    }

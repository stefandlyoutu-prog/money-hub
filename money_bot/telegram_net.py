"""Telegram-сессия для Money Hub бота."""

from __future__ import annotations

import logging

from aiogram.client.session.aiohttp import AiohttpSession

from business_dashboard.config import TELEGRAM_PROXY

logger = logging.getLogger(__name__)


def create_telegram_session() -> AiohttpSession:
    kwargs: dict = {"timeout": 120}
    if TELEGRAM_PROXY:
        kwargs["proxy"] = TELEGRAM_PROXY
        logger.info("Telegram proxy: %s", TELEGRAM_PROXY)
    return AiohttpSession(**kwargs)

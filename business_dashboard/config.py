"""Настройки Центра доходов из окружения."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Только эти Telegram user id могут /money (пусто = все)
MONEY_ADMIN_IDS: set[int] = {
    int(x.strip())
    for x in os.getenv("MONEY_ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

# Токен для API дашборда (пусто = без авторизации, только localhost)
DASHBOARD_TOKEN: str = os.getenv("MONEY_DASHBOARD_TOKEN", "").strip()

# Telegram-бот Money Hub (отдельный от M-bot / M-oracul)
MONEY_BOT_TOKEN: str = os.getenv("MONEY_BOT_TOKEN", "").strip()
MONEY_BOT_USERNAME: str = os.getenv("MONEY_BOT_USERNAME", "MS_Moneybot").strip().lstrip("@")
TELEGRAM_PROXY: str | None = os.getenv("TELEGRAM_PROXY", "").strip() or None

# Публичный URL (Render: RENDER_EXTERNAL_URL или вручную)
MONEY_HUB_PUBLIC_URL: str = (
    os.getenv("MONEY_HUB_PUBLIC_URL", "").strip()
    or os.getenv("RENDER_EXTERNAL_URL", "").strip()
).rstrip("/")

# Mini App path on same host
MONEY_MINIAPP_PATH: str = os.getenv("MONEY_MINIAPP_PATH", "/mini").strip().rstrip("/") or "/mini"


def public_dashboard_url() -> str:
    return MONEY_HUB_PUBLIC_URL or "http://127.0.0.1:8765"


def public_miniapp_url() -> str:
    base = public_dashboard_url().rstrip("/")
    path = MONEY_MINIAPP_PATH if MONEY_MINIAPP_PATH.startswith("/") else f"/{MONEY_MINIAPP_PATH}"
    return f"{base}{path}"


def money_cloud_enabled() -> bool:
    return os.getenv("MONEY_CLOUD", "").strip() in {"1", "true", "True"} or bool(
        os.getenv("RENDER_EXTERNAL_URL", "").strip()
    )

# Авто-отчёт в полночь (локальное время)
AUTO_CLOSE_DAY: bool = os.getenv("MONEY_AUTO_CLOSE_DAY", "1") not in {"0", "false", "False"}

# Подсказки для разведки трендов
TREND_SEED_QUERIES: tuple[str, ...] = tuple(
    q.strip()
    for q in os.getenv(
        "MONEY_TREND_QUERIES",
        "заработать в интернете,telegram бот подписка,осаго онлайн,"
        "самозанятый чек,карточка ozon,гадание таро бот,хозблок смета",
    ).split(",")
    if q.strip()
)

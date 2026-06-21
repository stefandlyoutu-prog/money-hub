"""Токены Telegram-ботов Money Hub (основной + второй тестовый)."""

from __future__ import annotations

import os

from business_dashboard.config import MONEY_BOT_TOKEN


def _token_2() -> str:
    return os.getenv("MONEY_BOT_TOKEN_2", "").strip()


def bot_slots() -> dict[str, str]:
    """slot → token (Mac .env)."""
    out: dict[str, str] = {}
    if MONEY_BOT_TOKEN:
        out["1"] = MONEY_BOT_TOKEN
    t2 = _token_2()
    if t2:
        out["2"] = t2
    return out


def render_bot_slots() -> dict[str, str]:
    """Токены бота на Render (если отличаются от Mac)."""
    out: dict[str, str] = {}
    r1 = os.getenv("MONEY_BOT_TOKEN_RENDER", "").strip()
    r2 = os.getenv("MONEY_BOT_TOKEN_2_RENDER", "").strip()
    if r1:
        out["1"] = r1
    elif MONEY_BOT_TOKEN:
        out["1"] = MONEY_BOT_TOKEN
    if r2:
        out["2"] = r2
    elif _token_2():
        out["2"] = _token_2()
    return out


def _on_render_host() -> bool:
    return bool(os.getenv("RENDER", "").strip())


def local_tokens_for_slot(slot: str | None = None) -> list[str]:
    """Только Mac/.env токены (бот @M_onetest_bot при локальном polling)."""
    slot = slot or "1"
    seen: set[str] = set()
    ordered: list[str] = []
    for t in (bot_slots().get(slot), bot_slots().get("1")):
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered


def render_tokens_for_slot(slot: str | None = None) -> list[str]:
    """Токены бота на Render (@MS_Moneybot в проде)."""
    slot = slot or "1"
    seen: set[str] = set()
    ordered: list[str] = []
    for t in (render_bot_slots().get(slot), render_bot_slots().get("1")):
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered


def all_tokens_for_slot(slot: str | None = None) -> list[str]:
    """Токены для скачивания file_id: на Mac — локальный бот первым, на Render — серверный."""
    slot = slot or "1"
    seen: set[str] = set()
    ordered: list[str] = []
    sources = (
        (render_bot_slots(), bot_slots())
        if _on_render_host()
        else (bot_slots(), render_bot_slots())
    )
    for src in sources:
        t = src.get(slot) or src.get("1") or ""
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)
    for t in bot_slots().values():
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered


def notify_tokens_for_slot(slot: str | None = None) -> list[str]:
    """Токены для исходящих сообщений с Mac-воркера (локальный чат первым)."""
    if _on_render_host():
        return render_tokens_for_slot(slot) or local_tokens_for_slot(slot)
    return local_tokens_for_slot(slot) or render_tokens_for_slot(slot)


def slot_for_token(token: str | None) -> str:
    if not token:
        return "1"
    for slot, t in bot_slots().items():
        if t == token:
            return slot
    return "1"


def token_for_slot(slot: str | None) -> str:
    tokens = all_tokens_for_slot(slot)
    return tokens[0] if tokens else MONEY_BOT_TOKEN


def notify_token_for_slot(slot: str | None) -> str:
    tokens = notify_tokens_for_slot(slot)
    return tokens[0] if tokens else MONEY_BOT_TOKEN


def usernames() -> dict[str, str]:
    u1 = os.getenv("MONEY_BOT_USERNAME", "M_onetest_bot").strip().lstrip("@")
    u2 = os.getenv("MONEY_BOT_USERNAME_2", "M_twotest_bot").strip().lstrip("@")
    out: dict[str, str] = {}
    if "1" in bot_slots():
        out["1"] = u1
    if "2" in bot_slots():
        out["2"] = u2
    return out

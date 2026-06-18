"""Токены Telegram-ботов Money Hub (основной + второй тестовый)."""

from __future__ import annotations

import os

from business_dashboard.config import MONEY_BOT_TOKEN


def _token_2() -> str:
    return os.getenv("MONEY_BOT_TOKEN_2", "").strip()


def bot_slots() -> dict[str, str]:
    """slot → token."""
    out: dict[str, str] = {}
    if MONEY_BOT_TOKEN:
        out["1"] = MONEY_BOT_TOKEN
    t2 = _token_2()
    if t2:
        out["2"] = t2
    return out


def slot_for_token(token: str | None) -> str:
    if not token:
        return "1"
    for slot, t in bot_slots().items():
        if t == token:
            return slot
    return "1"


def token_for_slot(slot: str | None) -> str:
    slots = bot_slots()
    if slot and slot in slots:
        return slots[slot]
    return MONEY_BOT_TOKEN or next(iter(slots.values()), "")


def usernames() -> dict[str, str]:
    u1 = os.getenv("MONEY_BOT_USERNAME", "M_onetest_bot").strip().lstrip("@")
    u2 = os.getenv("MONEY_BOT_USERNAME_2", "M_twotest_bot").strip().lstrip("@")
    out: dict[str, str] = {}
    if "1" in bot_slots():
        out["1"] = u1
    if "2" in bot_slots():
        out["2"] = u2
    return out

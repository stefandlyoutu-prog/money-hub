#!/usr/bin/env python3
"""Подсказка и проверка токенов Money Hub (Render vs Mac)."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _get(token: str, method: str) -> dict:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        b"{}",
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main() -> None:
    t1 = os.getenv("MONEY_BOT_TOKEN", "").strip()
    t2 = os.getenv("MONEY_BOT_TOKEN_2", "").strip()
    tr = os.getenv("MONEY_BOT_TOKEN_RENDER", "").strip()
    hub = os.getenv("MONEY_HUB_PUBLIC_URL", "https://money-hub-3p4r.onrender.com").strip()

    print("=== Money Hub — токены ===\n")
    for label, token in [
        ("Mac MONEY_BOT_TOKEN", t1),
        ("Mac MONEY_BOT_TOKEN_2", t2),
        ("Mac MONEY_BOT_TOKEN_RENDER", tr),
    ]:
        if not token:
            print(f"{label}: не задан")
            continue
        me = _get(token, "getMe")["result"]
        wh = _get(token, "getWebhookInfo")["result"].get("url") or "(polling)"
        print(f"{label}: @{me['username']} · webhook={wh}")

    try:
        with urllib.request.urlopen(f"{hub.rstrip('/')}/health", timeout=25) as r:
            health = json.load(r)
        bots = health.get("bot", {}).get("bots", [])
        print(f"\nRender {hub}:")
        for b in bots:
            print(f"  slot {b.get('slot')}: @{b.get('username')} → {b.get('webhook')}")
    except Exception as e:
        print(f"\nRender health: {e}")

    print(
        "\nЕсли Render показывает @MS_Moneybot, а ты пишешь в @M_onetest_bot — "
        "бот не ответит. На Render → money-hub → Environment задай:\n"
        "  MONEY_BOT_TOKEN = токен @M_onetest_bot\n"
        "  MONEY_BOT_USERNAME = M_onetest_bot\n"
        "  MONEY_BOT_TOKEN_2 = токен @M_twotest_bot\n"
        "  MONEY_BOT_USERNAME_2 = M_twotest_bot\n"
        "После сохранения — Manual Deploy.\n"
        "Локально: python3 scripts/run_money_bot.py (polling @M_onetest_bot)"
    )


if __name__ == "__main__":
    main()

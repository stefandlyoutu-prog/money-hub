#!/usr/bin/env python3
"""Проверка remote pipeline: webhook, очередь, воркер."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

BASE = os.getenv("MONEY_HUB_PUBLIC_URL", "https://money-hub-3p4r.onrender.com").rstrip("/")
PW = os.getenv("MONEY_DASHBOARD_PASSWORD", "1234")
SECRET = os.getenv("REMOTE_WORKER_SECRET", "")
ADMIN = int(os.getenv("MONEY_ADMIN_IDS", "5845195049").split(",")[0])
TOKEN = os.getenv("MONEY_BOT_TOKEN", "")


def get(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def post(url: str, payload: dict, headers: dict | None = None) -> dict:
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def main() -> None:
    errors: list[str] = []

    print("1. Health + bot webhook")
    h = get(f"{BASE}/health")
    bot = h.get("bot", {})
    print("   ", bot)
    if not bot.get("webhook"):
        errors.append("webhook пустой на сервере")
    if not bot.get("ready"):
        errors.append("bot not ready on server")

    print("2. Telegram webhook info")
    if TOKEN:
        tg = get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")["result"]
        print("   ", tg.get("url"), "pending", tg.get("pending_update_count"))
        if tg.get("url") != f"{BASE}/webhook":
            errors.append(f"TG webhook mismatch: {tg.get('url')}")

    print("3. Create test task")
    task = post(
        f"{BASE}/api/remote/tasks",
        {"user_id": ADMIN, "prompt": "Reply with exactly one word: ping"},
        {"X-Dashboard-Password": PW},
    )
    tid = task["id"]
    print(f"   task #{tid}")

    print("4. Wait worker (max 120s)")
    for i in range(24):
        time.sleep(5)
        st = get(f"{BASE}/api/remote/status", {"X-Dashboard-Password": PW})
        print(f"   {i*5}s queued={st.get('queued')} running={st.get('running')} online={st.get('online')}")
        if st.get("queued") == 0 and st.get("running") == 0:
            break

    print()
    if errors:
        print("FAIL:", *errors, sep="\n  ")
        sys.exit(1)
    print("OK pipeline checks passed (check Telegram for task result)")


if __name__ == "__main__":
    main()

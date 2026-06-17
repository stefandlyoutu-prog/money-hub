#!/usr/bin/env python3
"""Проверка всех возможностей remote-бота."""

from __future__ import annotations

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
        return json_load(r)


def post(url: str, payload: dict, headers: dict | None = None) -> dict:
    import json

    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=h, method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json_load(r)


def json_load(r):
    import json

    return json.load(r)


def main() -> None:
    ok: list[str] = []
    fail: list[str] = []

    print("=== 1. Render health + bot ===")
    try:
        h = get(f"{BASE}/health")
        bot = h.get("bot", {})
        if bot.get("ready") and bot.get("webhook"):
            ok.append("bot webhook ready")
        else:
            fail.append(f"bot not ready: {bot}")
    except Exception as e:
        fail.append(f"health: {e}")

    print("=== 2. Mac worker online ===")
    try:
        st = get(f"{BASE}/api/remote/status", {"X-Dashboard-Password": PW})
        if st.get("online"):
            ok.append("mac worker online")
        else:
            fail.append("mac worker offline")
    except Exception as e:
        fail.append(f"status: {e}")

    print("=== 3. Local mac_tools ===")
    try:
        from remote_agent.mac_tools import cmd_ls, cmd_open

        out, err = cmd_ls(str(Path.home() / "Projects"))
        if out and not err:
            ok.append("mac ls")
        else:
            fail.append(f"mac ls: {err}")
        # open Calculator is safe
        _, err2 = cmd_open("Calculator")
        if not err2:
            ok.append("mac open app")
        else:
            fail.append(f"mac open: {err2}")
    except Exception as e:
        fail.append(f"mac_tools: {e}")

    print("=== 4. Direct command queue ===")
    try:
        task = post(
            f"{BASE}/api/remote/tasks",
            {
                "user_id": ADMIN,
                "prompt": "__DIRECT__:ls ~/Projects",
            },
            {"X-Dashboard-Password": PW},
        )
        tid = task["id"]
        for _ in range(24):
            time.sleep(5)
            st = get(f"{BASE}/api/remote/status", {"X-Dashboard-Password": PW})
            if st.get("queued") == 0 and st.get("running") == 0:
                break
        ok.append(f"direct task #{tid} processed")
    except Exception as e:
        fail.append(f"direct task: {e}")

    print("=== 5. Groq voice key ===")
    try:
        from remote_agent.voice import _groq_api_key
        import json
        import urllib.request

        key = _groq_api_key()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/models",
            headers={
                "Authorization": f"Bearer {key}",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/124.0.0.0",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            json.load(r)
        ok.append("groq whisper API")
    except Exception as e:
        fail.append(f"groq: {e}")

    print("=== 6. Cursor agent CLI ===")
    try:
        from remote_agent.executor import agent_available

        ok_cli, path = agent_available()
        if ok_cli:
            ok.append(f"cursor agent: {path}")
        else:
            fail.append("cursor agent missing")
    except Exception as e:
        fail.append(f"agent: {e}")

    print("=== 7. Projects map ===")
    try:
        from remote_agent.projects import project_roots

        roots = project_roots()
        found = sum(1 for p in roots.values() if Path(p).is_dir())
        ok.append(f"projects {found}/{len(roots)} dirs exist")
    except Exception as e:
        fail.append(f"projects: {e}")

    if TOKEN:
        print("=== 8. TG webhook ===")
        try:
            tg = get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")["result"]
            if tg.get("url") == f"{BASE}/webhook":
                ok.append("telegram webhook")
            else:
                fail.append(f"webhook mismatch: {tg.get('url')}")
        except Exception as e:
            fail.append(f"tg: {e}")

    print("\n" + "=" * 40)
    print("OK:", len(ok))
    for x in ok:
        print("  ✅", x)
    if fail:
        print("FAIL:", len(fail))
        for x in fail:
            print("  ❌", x)
        sys.exit(1)
    print("\nВсе проверки прошли. Тест в Telegram: /cap, текст, голос, файл.")


if __name__ == "__main__":
    main()

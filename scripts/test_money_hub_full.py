#!/usr/bin/env python3
"""Полная проверка Money Hub: API, бот-команды, конфиг."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PW = "1234"
ADMIN = 5845195049
errors: list[str] = []


def ok(name: str) -> None:
    print(f"  OK  {name}")


def fail(name: str, e: str) -> None:
    errors.append(f"{name}: {e}")
    print(f"  FAIL {name}: {e}")


def test_api() -> None:
    from fastapi.testclient import TestClient
    from business_dashboard.app import app

    c = TestClient(app)
    h = {"X-Dashboard-Password": PW}
    endpoints = [
        ("GET", "/health", None, None),
        ("GET", "/api/config", None, None),
        ("GET", "/api/dashboard", h, 200),
        ("GET", "/api/spheres", h, 200),
        ("GET", "/api/chart", h, 200),
        ("GET", "/api/today/plan", h, 200),
        ("GET", "/api/assets", h, 200),
        ("GET", "/api/scout", h, 200),
        ("GET", "/api/tg-channels", h, 200),
        ("GET", "/mini/", None, 200),
        ("GET", f"/api/mini/home?user_id={ADMIN}", None, 200),
    ]
    for method, path, headers, expect in endpoints:
        r = c.get(path, headers=headers or {})
        if expect and r.status_code != expect:
            fail(f"{method} {path}", f"status {r.status_code}")
        elif path == "/health" and not r.json().get("ok"):
            fail(path, "not ok")
        else:
            ok(f"{method} {path}")


def test_bot_handlers() -> None:
    from money_bot.handlers import router, _allowed, open_3d_module
    assert router is not None
    assert _allowed(ADMIN)
    assert not _allowed(1)
    ok("bot access control")


def test_commands_logic() -> None:
    from business_dashboard.storage import init_db, list_ideas, add_revenue
    from business_dashboard.daily import get_money_metrics, add_to_today_plan

    init_db()
    ideas = list_ideas()
    assert ideas, "no ideas seeded"
    ok(f"ideas seeded ({len(ideas)})")
    m = get_money_metrics()
    assert "gap" in m and "target_today" in m
    ok("money metrics")
    slug = ideas[0]["slug"]
    add_to_today_plan(slug, 100)
    ok("add to plan")


async def test_live_render() -> None:
    import aiohttp

    base = "https://money-hub-3p4r.onrender.com"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{base}/health", timeout=aiohttp.ClientTimeout(total=60)) as r:
                if r.status != 200:
                    fail("live /health", str(r.status))
                    return
                ok("live /health")
            async with s.get(
                f"{base}/api/dashboard",
                headers={"X-Dashboard-Password": PW},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as r:
                if r.status != 200:
                    fail("live dashboard", str(r.status))
                else:
                    ok("live dashboard (password 1234)")
    except Exception as e:
        fail("live render", str(e))


def main() -> None:
    print("Money Hub full check\n")
    for fn in (test_api, test_bot_handlers, test_commands_logic):
        try:
            fn()
        except Exception as e:
            fail(fn.__name__, str(e))
    asyncio.run(test_live_render())
    print()
    if errors:
        print(f"FAILED: {len(errors)}")
        for e in errors:
            print(" ", e)
        sys.exit(1)
    print("All checks passed")


if __name__ == "__main__":
    main()

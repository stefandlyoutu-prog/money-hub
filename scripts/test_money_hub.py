#!/usr/bin/env python3
"""Smoke-тест Money Hub: API, импорты, конфиг."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

errors: list[str] = []


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"  OK  {name}")
    except Exception as e:
        errors.append(f"{name}: {e}")
        print(f"  FAIL {name}: {e}")


def main() -> None:
    print("Money Hub tests\n")

    def imports():
        from business_dashboard.app import app  # noqa: F401
        from money_bot.handlers import router  # noqa: F401

    def db():
        from business_dashboard.storage import init_db, list_ideas

        init_db()
        assert isinstance(list_ideas(), list)

    def metrics():
        from business_dashboard.daily import get_money_metrics

        m = get_money_metrics()
        assert "target_today" in m

    def routes():
        from business_dashboard.app import app

        paths = {getattr(r, "path", "") for r in app.routes}
        for p in ("/health", "/mini", "/api/mini/home", "/api/config"):
            assert p in paths, f"missing {p}"

    def http():
        from fastapi.testclient import TestClient
        from business_dashboard.app import app

        c = TestClient(app)
        assert c.get("/health").json()["ok"]
        assert c.get("/mini/").status_code == 200
        h = {"X-Dashboard-Password": "1234"}
        assert c.get("/api/mini/home?user_id=5845195049").status_code == 200
        assert c.get("/api/dashboard", headers=h).status_code == 200
        assert c.get("/api/dashboard", headers={"X-Dashboard-Password": "wrong"}).status_code == 401

    check("imports", imports)
    check("database", db)
    check("metrics", metrics)
    check("routes", routes)
    check("http", http)

    print()
    if errors:
        print(f"FAILED: {len(errors)}")
        sys.exit(1)
    print("All OK")


if __name__ == "__main__":
    main()

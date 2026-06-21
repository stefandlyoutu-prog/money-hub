"""HTTP-клиент очереди задач на Render (Mac polling → hub DB)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def hub_url() -> str:
    return (
        os.getenv("MONEY_HUB_PUBLIC_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
        or "https://money-hub-3p4r.onrender.com"
    ).rstrip("/")


def _dashboard_password() -> str:
    return os.getenv("MONEY_DASHBOARD_PASSWORD", "1234").strip()


def use_remote_hub_queue() -> bool:
    """Mac polling пишет задачи на Render, а не в локальный sqlite."""
    if os.getenv("RENDER", "").strip():
        return False
    return bool(hub_url() and _dashboard_password())


def _hub_request(
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    worker_secret: str = "",
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if worker_secret:
        headers["X-Remote-Worker-Secret"] = worker_secret
    else:
        headers["X-Dashboard-Password"] = _dashboard_password()
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        hub_url() + path,
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def create_task_remote(
    user_id: int, prompt: str, *, bot_slot: str = "1"
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "user_id": user_id,
        "prompt": prompt[:8000],
        "bot_slot": bot_slot if bot_slot in ("1", "2") else "1",
    }
    return _hub_request("POST", "/api/remote/tasks", body)


def worker_status_remote() -> dict[str, Any]:
    return _hub_request("GET", "/api/remote/status")


def render_bot_username(slot: str = "1") -> str:
    """Username бота на Render (из /health)."""
    try:
        req = urllib.request.Request(f"{hub_url()}/health", method="GET")
        with urllib.request.urlopen(req, timeout=25) as r:
            health = json.load(r)
        for b in health.get("bot", {}).get("bots", []):
            if str(b.get("slot")) == slot:
                return str(b.get("username") or "")
    except Exception:
        pass
    return ""


def render_bot_differs(slot: str = "1") -> bool:
    """True если на Render другой @username, чем локальный polling-бот на Mac."""
    from money_bot.bot_tokens import usernames

    render_u = render_bot_username(slot).strip().lstrip("@").lower()
    local_u = usernames().get(slot, "").strip().lstrip("@").lower()
    if not render_u or not local_u:
        return False
    return render_u != local_u


def prefer_hub_telegram(slot: str = "1") -> bool:
    """Mac-воркер шлёт в Telegram через Render (токен @MS_Moneybot и т.п.)."""
    if os.getenv("RENDER", "").strip():
        return False
    secret = os.getenv("REMOTE_WORKER_SECRET", "").strip()
    if not secret or not hub_url():
        return False
    return render_bot_differs(slot)

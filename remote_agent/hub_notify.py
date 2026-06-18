"""Отправка в Telegram через Render (токен бота на сервере)."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


def _hub_url() -> str:
    return (
        os.getenv("MONEY_HUB_PUBLIC_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
        or "https://money-hub-3p4r.onrender.com"
    ).rstrip("/")


def _secret() -> str:
    return os.getenv("REMOTE_WORKER_SECRET", "").strip()


def hub_available() -> bool:
    return bool(_hub_url() and _secret())


def push_notify(
    user_id: int,
    task_id: int,
    *,
    prompt: str = "",
    result: str = "",
    error: str = "",
    files: list[tuple[str, bytes, str]] | None = None,
    bot_slot: str = "1",
) -> tuple[bool, str]:
    """
    files: [(filename, bytes, kind)] kind = photo|document
    Returns (ok, error_message).
    """
    if not hub_available():
        return False, "hub not configured"
    payload: dict = {
        "user_id": user_id,
        "task_id": task_id,
        "prompt": prompt,
        "result": result,
        "error": error,
        "bot_slot": bot_slot,
        "files": [],
    }
    for name, data, kind in files or []:
        if not data:
            continue
        payload["files"].append(
            {
                "filename": name,
                "kind": kind,
                "data_b64": base64.b64encode(data).decode("ascii"),
            }
        )
    url = f"{_hub_url()}/api/remote/worker/push-notify"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Remote-Worker-Secret": _secret(),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.load(r)
        if data.get("ok"):
            return True, ""
        return False, str(data.get("error") or "push-notify failed")
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")[:400]
        try:
            detail = json.loads(raw).get("detail", raw)
        except json.JSONDecodeError:
            detail = raw
        return False, f"hub notify HTTP {e.code}: {detail}"
    except Exception as e:
        return False, str(e)


def collect_files(paths: list[str], *, max_mb: int = 45) -> list[tuple[str, bytes, str]]:
    out: list[tuple[str, bytes, str]] = []
    limit = max_mb * 1024 * 1024
    for raw in paths:
        p = Path(raw).expanduser()
        if not p.is_file():
            continue
        if p.stat().st_size > limit:
            continue
        ext = p.suffix.lower()
        kind = "photo" if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"} else "document"
        out.append((p.name, p.read_bytes(), kind))
    return out

#!/usr/bin/env python3
"""Mac-воркер: забирает задачи с Render и запускает Cursor Agent CLI."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from remote_agent.attachments import ingest_prompt_attachments
from remote_agent.config import REMOTE_AGENT_BIN
from remote_agent.direct import is_direct_task, run_direct_task
from remote_agent.executor import agent_available, run_agent_prompt
from remote_agent.notify_mac import notify_task_result
from remote_agent.voice import resolve_prompt

ATTACH_DIR = ROOT / "data" / "remote_attachments"


def _hub_url() -> str:
    return (
        os.getenv("MONEY_HUB_PUBLIC_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
        or "https://money-hub-3p4r.onrender.com"
    ).rstrip("/")


def _secret() -> str:
    s = os.getenv("REMOTE_WORKER_SECRET", "").strip()
    if not s:
        raise SystemExit("Задай REMOTE_WORKER_SECRET в .env (тот же что на Render)")
    return s


def _api(method: str, path: str, payload: dict | None = None) -> dict:
    url = _hub_url() + path
    data = json.dumps(payload or {}).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Remote-Worker-Secret": _secret(),
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def _agent_version() -> str:
    ok, path = agent_available()
    if not ok:
        return "not installed"
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15)
        return (out.stdout or out.stderr or "ok").strip()[:100]
    except Exception:
        return "ok"


def heartbeat() -> None:
    _api(
        "POST",
        "/api/remote/worker/heartbeat",
        {
            "hostname": platform.node(),
            "agent_version": _agent_version(),
        },
    )


def _complete(
    tid: int,
    *,
    user_id: int,
    raw_prompt: str,
    result: str,
    error: str,
    extra_files: list[str] | None = None,
) -> None:
    try:
        notify_task_result(
            user_id,
            tid,
            prompt=raw_prompt,
            result=result,
            error=error,
            extra_files=extra_files,
        )
        worker_notified = True
    except Exception as e:
        print(f"[remote] notify failed #{tid}: {e}")
        worker_notified = False
    _api(
        "POST",
        f"/api/remote/worker/complete/{tid}",
        {
            "result": result,
            "error": error,
            "worker_notified": worker_notified,
        },
    )


def process_once() -> bool:
    data = _api("POST", "/api/remote/worker/claim")
    task = data.get("task")
    if not task:
        return False
    tid = int(task["id"])
    user_id = int(task.get("user_id") or 0)
    raw_prompt = task["prompt"]
    print(f"[remote] task #{tid}: {raw_prompt[:80]}…")

    if is_direct_task(raw_prompt):
        result, error = run_direct_task(raw_prompt)
        _complete(tid, user_id=user_id, raw_prompt=raw_prompt, result=result, error=error)
        print(f"[remote] task #{tid} direct done error={bool(error)}")
        return True

    prompt, attach_paths, attach_err = ingest_prompt_attachments(
        raw_prompt, download_dir=ATTACH_DIR / str(tid)
    )
    if attach_err and not prompt:
        _complete(tid, user_id=user_id, raw_prompt=raw_prompt, result="", error=attach_err)
        return True

    prompt, prep_err = resolve_prompt(prompt)
    if prep_err:
        _complete(tid, user_id=user_id, raw_prompt=raw_prompt, result="", error=prep_err)
        print(f"[remote] task #{tid} prep failed: {prep_err}")
        return True
    if raw_prompt != prompt:
        print(f"[remote] voice → {prompt[:120]}…")

    result, error = run_agent_prompt(prompt, attachment_paths=attach_paths)
    if raw_prompt != prompt and not error:
        result = f"🎤 Расшифровано: {prompt[:500]}\n\n{result}"
    _complete(
        tid,
        user_id=user_id,
        raw_prompt=raw_prompt,
        result=result,
        error=error,
        extra_files=attach_paths,
    )
    print(f"[remote] task #{tid} done error={bool(error)}")
    return True


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Money Hub remote worker (Mac)")
    p.add_argument("--once", action="store_true", help="Обработать одну задачу и выйти")
    p.add_argument("--interval", type=float, default=8.0, help="Пауза между опросами (сек)")
    args = p.parse_args()

    print(f"Hub: {_hub_url()}")
    ok, path = agent_available()
    print(f"Agent: {path} ({'ok' if ok else 'MISSING — curl https://cursor.com/install -fsS | bash'})")

    while True:
        try:
            heartbeat()
            if process_once():
                continue
        except urllib.error.HTTPError as e:
            print(f"[remote] HTTP {e.code}: {e.read().decode()[:200]}")
        except Exception as e:
            print(f"[remote] error: {e}")
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

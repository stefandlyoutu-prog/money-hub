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
from remote_agent.video_audio import extract_audio_from_paths, is_video_path
from money_bot.bot_tokens import token_for_slot
from remote_agent.notify_mac import notify_task_result
from remote_agent.progress import TaskProgress, run_with_progress
from remote_agent.voice import VOICE_PREFIX, resolve_prompt

ATTACH_DIR = ROOT / "data" / "remote_attachments"

_ATTACH_MARKERS = (
    "__FILE__:",
    "__PHOTO__:",
    "__DOC__:",
    "__VIDEO__:",
    "__VIDEO_NOTE__:",
)

_SKIP_AUDIO_KEYWORDS = (
    "не извлек",
    "без аудио",
    "не аудио",
    "анализ видео",
    "опиши видео",
    "что на видео",
    "распознай видео",
    "субтитр",
)


def _wants_audio_extraction(prompt: str, raw_prompt: str, *, has_video: bool) -> bool:
    """Для видео по умолчанию извлекаем mp3, если пользователь явно не просит другое."""
    if not has_video:
        return False
    low = f"{prompt}\n{raw_prompt}".lower()
    if any(k in low for k in _SKIP_AUDIO_KEYWORDS):
        return False
    return True


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
    progress: TaskProgress | None = None,
    bot_slot: str = "1",
) -> None:
    if progress:
        progress.done()
    worker_notified = False
    try:
        notify_task_result(
            user_id,
            tid,
            prompt=raw_prompt,
            result=result,
            error=error,
            extra_files=extra_files,
            bot_slot=bot_slot,
        )
        worker_notified = True
    except Exception as e:
        print(f"[remote] notify failed #{tid}: {e}")
    try:
        _api(
            "POST",
            f"/api/remote/worker/complete/{tid}",
            {
                "result": result,
                "error": error,
                "worker_notified": worker_notified,
            },
        )
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        if worker_notified and not error and e.code == 404:
            print(f"[remote] complete #{tid} 404 ignored (user already notified): {body}")
        else:
            raise


def process_once() -> bool:
    data = _api("POST", "/api/remote/worker/claim")
    task = data.get("task")
    if not task:
        return False
    tid = int(task["id"])
    user_id = int(task.get("user_id") or 0)
    raw_prompt = task["prompt"]
    bot_slot = str(task.get("bot_slot") or "1")
    bot_token = token_for_slot(bot_slot)
    print(f"[remote] task #{tid} bot={bot_slot}: {raw_prompt[:80]}…")

    progress = TaskProgress(user_id, tid, raw_prompt=raw_prompt, bot_slot=bot_slot)
    progress.start("Mac взял в работу", detail="Обычно < 10 сек до старта")

    try:
        if is_direct_task(raw_prompt):
            progress.update("⚡ Быстрая команда Mac…")
            result, error = run_direct_task(raw_prompt)
            _complete(
                tid, user_id=user_id, raw_prompt=raw_prompt,
                result=result, error=error, progress=progress, bot_slot=bot_slot,
            )
            print(f"[remote] task #{tid} direct done error={bool(error)}")
            return True

        has_attach = any(
            x in raw_prompt
            for x in ("__FILE__:", "__PHOTO__:", "__DOC__:", "__VIDEO__:", "__VIDEO_NOTE__:")
        )
        if has_attach:
            progress.update("📥 Скачиваю файлы с Telegram…", detail="На Mac")

        prompt, attach_paths, attach_err = ingest_prompt_attachments(
            raw_prompt,
            download_dir=ATTACH_DIR / str(tid),
            bot_token=bot_token,
            bot_slot=bot_slot,
        )
        wants_video = any(m in raw_prompt for m in ("__VIDEO__:", "__VIDEO_NOTE__:"))
        if attach_err and (not prompt or (wants_video and not attach_paths)):
            _complete(
                tid, user_id=user_id, raw_prompt=raw_prompt,
                result="", error=attach_err, progress=progress, bot_slot=bot_slot,
            )
            print(f"[remote] task #{tid} attach failed: {attach_err[:120]}")
            return True

        video_paths = [p for p in attach_paths if is_video_path(p)]
        if video_paths:
            print(f"[remote] task #{tid} video files: {[Path(p).name for p in video_paths]}")
        if video_paths and _wants_audio_extraction(prompt, raw_prompt, has_video=True):
            progress.update("🎬 Извлекаю аудио из видео…", detail="ffmpeg на Mac")
            mp3_paths, aud_err = extract_audio_from_paths(
                video_paths, download_dir=ATTACH_DIR / str(tid)
            )
            if mp3_paths:
                names = ", ".join(Path(p).name for p in mp3_paths)
                result = (
                    f"🎬 Готово — аудио из видео:\n{names}\n\n"
                    f"Файлы mp3 прикреплены к этому сообщению."
                )
                _complete(
                    tid,
                    user_id=user_id,
                    raw_prompt=raw_prompt,
                    result=result,
                    error="",
                    extra_files=mp3_paths,
                    progress=progress,
                    bot_slot=bot_slot,
                )
                print(f"[remote] task #{tid} video→audio direct done")
                return True
            if aud_err:
                _complete(
                    tid, user_id=user_id, raw_prompt=raw_prompt,
                    result="", error=aud_err, progress=progress, bot_slot=bot_slot,
                )
                return True

        is_voice = VOICE_PREFIX in prompt
        if is_voice:
            progress.update(
                "🎤 Расшифровываю голос…",
                detail="Whisper 1–3 мин для длинных сообщений",
            )

        prompt, prep_err = resolve_prompt(
            prompt, bot_token=bot_token, bot_slot=bot_slot
        )
        if prep_err:
            _complete(
                tid, user_id=user_id, raw_prompt=raw_prompt,
                result="", error=prep_err, progress=progress, bot_slot=bot_slot,
            )
            print(f"[remote] task #{tid} prep failed: {prep_err}")
            return True

        if is_voice:
            preview = (prompt[:150] + "…") if len(prompt) > 150 else prompt
            progress.update("✍️ Голос расшифрован", detail=preview)
            print(f"[remote] voice → {prompt[:120]}…")

        result, error = run_with_progress(
            progress,
            lambda: run_agent_prompt(prompt, attachment_paths=attach_paths),
            stage="🧠 Cursor Agent думает…",
            detail="До 15 мин — статус обновляется каждые 40 сек",
        )
        if is_voice and not error:
            result = f"🎤 Расшифровано: {prompt[:500]}\n\n{result}"

        _complete(
            tid,
            user_id=user_id,
            raw_prompt=raw_prompt,
            result=result,
            error=error,
            extra_files=attach_paths,
            progress=progress,
            bot_slot=bot_slot,
        )
        print(f"[remote] task #{tid} done error={bool(error)}")
        return True
    except Exception as e:
        progress.update("❌ Сбой на Mac", detail=str(e)[:200])
        _complete(
            tid, user_id=user_id, raw_prompt=raw_prompt,
            result="", error=str(e), progress=progress, bot_slot=bot_slot,
        )
        print(f"[remote] task #{tid} failed: {e}")
        return True


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Money Hub remote worker (Mac)")
    p.add_argument("--once", action="store_true", help="Обработать одну задачу и выйти")
    p.add_argument("--interval", type=float, default=8.0, help="Пауза между опросами (сек)")
    args = p.parse_args()

    print(f"Hub: {_hub_url()}")
    ok, path = agent_available()
    print(f"Agent: {path} ({'ok' if ok else 'MISSING'})")

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

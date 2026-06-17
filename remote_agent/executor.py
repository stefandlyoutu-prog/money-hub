"""Запуск Cursor Agent CLI на Mac."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from remote_agent.config import REMOTE_AGENT_BIN, REMOTE_AGENT_CWD, REMOTE_TASK_TIMEOUT_SEC
from remote_agent.prompt import wrap_user_prompt


def agent_available() -> tuple[bool, str]:
    p = Path(REMOTE_AGENT_BIN)
    if p.is_file():
        return True, str(p)
    for alt in (
        Path.home() / ".cursor" / "bin" / "agent",
        Path.home() / ".local" / "bin" / "agent",
    ):
        if alt.is_file():
            return True, str(alt)
    return False, REMOTE_AGENT_BIN


def run_agent_prompt(prompt: str, *, attachment_paths: list[str] | None = None) -> tuple[str, str]:
    """Возвращает (stdout+result, error)."""
    ok, bin_path = agent_available()
    if not ok:
        return "", (
            "Cursor Agent CLI не установлен. Запусти на Mac:\n"
            "curl https://cursor.com/install -fsS | bash\n"
            "export CURSOR_API_KEY=... в ~/.zshrc"
        )

    cwd = Path(REMOTE_AGENT_CWD)
    if not cwd.is_dir():
        return "", f"Папка проекта не найдена: {cwd}"

    env = os.environ.copy()
    wrapped = wrap_user_prompt(prompt, project_dir=str(cwd), attachment_paths=attachment_paths)
    cmd = [
        bin_path,
        "-p",
        "--trust",
        "--force",
        "--output-format",
        "text",
        wrapped,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=REMOTE_TASK_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return "", f"Таймаут {REMOTE_TASK_TIMEOUT_SEC // 60} мин — задача слишком большая"
    except OSError as e:
        return "", str(e)

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        msg = err or out or f"agent exit {proc.returncode}"
        return out, msg
    return out or "Агент выполнил задачу, но не вернул текст.", ""

"""Прямые команды Mac без полного агента."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _run(cmd: list[str], *, timeout: int = 60) -> tuple[str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        if p.returncode != 0:
            return out, err or f"exit {p.returncode}"
        return out, ""
    except subprocess.TimeoutExpired:
        return "", f"Таймаут {timeout}с"
    except OSError as e:
        return "", str(e)


def cmd_open(app_or_path: str) -> tuple[str, str]:
    target = app_or_path.strip()
    if not target:
        return "", "Укажи приложение или путь"
    if Path(target).expanduser().exists():
        return _run(["open", str(Path(target).expanduser())])
    return _run(["open", "-a", target])


def cmd_find(query: str, *, root: str | None = None) -> tuple[str, str]:
    q = query.strip()
    if not q:
        return "", "Укажи имя файла"
    base = root or str(Path.home())
    out, err = _run(["mdfind", "-onlyin", base, q], timeout=30)
    if err:
        out2, err2 = _run(["find", base, "-iname", f"*{q}*", "-maxdepth", "5"], timeout=45)
        return out2[:4000], err2
    lines = out.splitlines()[:25]
    return "\n".join(lines) if lines else "(ничего не найдено)", ""


def cmd_ls(path: str) -> tuple[str, str]:
    p = Path(path.strip() or ".").expanduser()
    if not p.is_dir():
        return "", f"Не папка: {p}"
    lines = []
    for item in sorted(p.iterdir())[:40]:
        mark = "📁" if item.is_dir() else "📄"
        lines.append(f"{mark} {item.name}")
    if len(list(p.iterdir())) > 40:
        lines.append("…")
    return "\n".join(lines), ""


def cmd_shell(command: str) -> tuple[str, str]:
    if os.getenv("REMOTE_ALLOW_SHELL", "1").strip() not in {"1", "true", "True"}:
        return "", "Shell отключён (REMOTE_ALLOW_SHELL=0)"
    cmd = command.strip()
    if not cmd:
        return "", "Пустая команда"
    return _run(["/bin/bash", "-lc", cmd], timeout=120)


def cmd_sleep() -> tuple[str, str]:
    out, err = _run(["pmset", "sleepnow"])
    return out or "Mac уходит в сон", err


def cmd_shutdown(*, confirm: bool) -> tuple[str, str]:
    if os.getenv("REMOTE_ALLOW_POWER", "1").strip() not in {"1", "true", "True"}:
        return "", "Выключение отключено (REMOTE_ALLOW_POWER=0)"
    if not confirm:
        return (
            "⚠️ Для выключения отправь:\n/mac power shutdown confirm",
            "",
        )
    out, err = _run(["osascript", "-e", 'tell app "System Events" to shut down'])
    return out or "Команда выключения отправлена", err


def cmd_restart(*, confirm: bool) -> tuple[str, str]:
    if os.getenv("REMOTE_ALLOW_POWER", "1").strip() not in {"1", "true", "True"}:
        return "", "Перезагрузка отключена (REMOTE_ALLOW_POWER=0)"
    if not confirm:
        return "⚠️ Для перезагрузки:\n/mac power restart confirm", ""
    out, err = _run(["osascript", "-e", 'tell app "System Events" to restart'])
    return out or "Команда перезагрузки отправлена", err


def run_direct(subcmd: str, args: str) -> tuple[str, str]:
    """/mac … → текст результата."""
    sub = subcmd.lower().strip()
    a = args.strip()
    if sub in ("open", "app"):
        return cmd_open(a)
    if sub in ("find", "search"):
        return cmd_find(a)
    if sub == "ls":
        return cmd_ls(a or "~")
    if sub in ("run", "shell", "exec"):
        return cmd_shell(a)
    if sub == "sleep":
        return cmd_sleep()
    if sub == "power":
        parts = a.split()
        action = parts[0].lower() if parts else ""
        confirmed = "confirm" in [p.lower() for p in parts[1:]]
        if action == "shutdown":
            return cmd_shutdown(confirm=confirmed)
        if action == "restart":
            return cmd_restart(confirm=confirmed)
        return "power: shutdown | restart (+ confirm)", ""
    return "", f"Неизвестная команда /mac {sub}. См. /cap"

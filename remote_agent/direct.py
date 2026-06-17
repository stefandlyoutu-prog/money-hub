"""Маршрутизация: прямые команды Mac vs Cursor Agent."""

from __future__ import annotations

from remote_agent.mac_tools import run_direct

_DIRECT_PREFIX = "__DIRECT__:"


def is_direct_task(raw: str) -> bool:
    return (raw or "").strip().startswith(_DIRECT_PREFIX)


def run_direct_task(raw: str) -> tuple[str, str]:
    body = raw.strip()[len(_DIRECT_PREFIX) :].strip()
    parts = body.split(maxsplit=1)
    sub = parts[0] if parts else ""
    args = parts[1] if len(parts) > 1 else ""
    out, err = run_direct(sub, args)
    if err:
        return out, err
    header = (
        "КАК ПОНЯЛ ЗАДАЧУ:\n"
        f"Прямая команда Mac: /mac {sub} {args}".strip()
        + "\n\nЧТО СДЕЛАЛ:\n"
        f"Выполнил на Mac без Cursor Agent.\n\nИТОГ:\n"
    )
    return header + (out or "OK"), ""


def wrap_direct_command(sub: str, args: str) -> str:
    return f"{_DIRECT_PREFIX}{sub} {args}".strip()

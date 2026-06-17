"""Пути к проектам на Mac для агента."""

from __future__ import annotations

import os
from pathlib import Path

_HOME = Path.home()
_DEFAULT_ROOT = _HOME / "Projects"


def project_roots() -> dict[str, str]:
    """Имя → абсолютный путь."""
    raw = os.getenv("REMOTE_PROJECTS", "").strip()
    if raw:
        out: dict[str, str] = {}
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                name, path = part.split(":", 1)
                out[name.strip()] = str(Path(path.strip()).expanduser())
            else:
                p = Path(part).expanduser()
                out[p.name] = str(p)
        return out
    return {
        "morozov-workspace": str(_DEFAULT_ROOT / "morozov-workspace"),
        "m-oracul": str(_DEFAULT_ROOT / "m-oracul"),
        "m-bot": str(_DEFAULT_ROOT / "m-bot"),
        "m-money-hub": str(_DEFAULT_ROOT / "m-money-hub"),
        "telegram-agent-bot": str(_DEFAULT_ROOT / "telegram-agent-bot"),
    }


def projects_block() -> str:
    lines = ["Доступные проекты на Mac:"]
    for name, path in project_roots().items():
        mark = "✓" if Path(path).is_dir() else "✗"
        lines.append(f"  {mark} {name}: {path}")
    return "\n".join(lines)

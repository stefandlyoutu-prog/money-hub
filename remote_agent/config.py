"""Настройки remote agent."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REMOTE_WORKER_SECRET: str = os.getenv("REMOTE_WORKER_SECRET", "").strip()
REMOTE_AGENT_CWD: str = os.getenv(
    "REMOTE_AGENT_CWD",
    str(Path.home() / "Projects" / "morozov-workspace"),
).strip()
REMOTE_AGENT_BIN: str = os.getenv(
    "REMOTE_AGENT_BIN",
    str(Path.home() / ".local" / "bin" / "agent"),
).strip()
REMOTE_HEARTBEAT_TTL_SEC: int = int(os.getenv("REMOTE_HEARTBEAT_TTL_SEC", "120"))
REMOTE_TASK_TIMEOUT_SEC: int = int(os.getenv("REMOTE_TASK_TIMEOUT_SEC", "900"))

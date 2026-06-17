"""Очередь задач: Telegram → Mac worker → Cursor Agent."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from business_dashboard.storage import DB_PATH, _connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_remote(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS remote_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            prompt TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            result TEXT DEFAULT '',
            error TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS remote_worker (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_heartbeat TEXT,
            hostname TEXT DEFAULT '',
            agent_version TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO remote_worker (id, last_heartbeat) VALUES (1, NULL)"
    )


def ensure_remote() -> None:
    with _connect() as conn:
        init_remote(conn)


def create_task(user_id: int, prompt: str) -> Dict[str, Any]:
    ensure_remote()
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO remote_tasks (user_id, prompt, status, created_at)
            VALUES (?, ?, 'queued', ?)
            """,
            (user_id, prompt[:8000], now),
        )
        tid = int(cur.lastrowid)
        row = conn.execute("SELECT * FROM remote_tasks WHERE id = ?", (tid,)).fetchone()
    return dict(row)


def worker_heartbeat(hostname: str = "", agent_version: str = "") -> None:
    ensure_remote()
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE remote_worker SET last_heartbeat = ?, hostname = ?, agent_version = ?
            WHERE id = 1
            """,
            (now, hostname[:200], agent_version[:200]),
        )


def worker_status() -> Dict[str, Any]:
    ensure_remote()
    with _connect() as conn:
        w = conn.execute("SELECT * FROM remote_worker WHERE id = 1").fetchone()
        pending = conn.execute(
            "SELECT COUNT(*) FROM remote_tasks WHERE status = 'queued'"
        ).fetchone()[0]
        running = conn.execute(
            "SELECT COUNT(*) FROM remote_tasks WHERE status = 'running'"
        ).fetchone()[0]
    last = w["last_heartbeat"] if w else None
    online = False
    if last:
        try:
            dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - dt).total_seconds()
            from remote_agent.config import REMOTE_HEARTBEAT_TTL_SEC

            online = age < REMOTE_HEARTBEAT_TTL_SEC
        except ValueError:
            online = False
    return {
        "online": online,
        "last_heartbeat": last,
        "hostname": w["hostname"] if w else "",
        "agent_version": w["agent_version"] if w else "",
        "queued": int(pending),
        "running": int(running),
    }


def claim_next_task() -> Optional[Dict[str, Any]]:
    ensure_remote()
    now = _now()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM remote_tasks WHERE status = 'queued'
            ORDER BY id ASC LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        conn.execute(
            """
            UPDATE remote_tasks SET status = 'running', started_at = ?
            WHERE id = ? AND status = 'queued'
            """,
            (now, row["id"]),
        )
        return dict(row)


def complete_task(task_id: int, *, result: str = "", error: str = "") -> Optional[Dict[str, Any]]:
    ensure_remote()
    now = _now()
    status = "done" if not error else "error"
    with _connect() as conn:
        conn.execute(
            """
            UPDATE remote_tasks SET status = ?, result = ?, error = ?, finished_at = ?
            WHERE id = ?
            """,
            (status, result[:50000], error[:2000], now, task_id),
        )
        row = conn.execute("SELECT * FROM remote_tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def get_task(task_id: int) -> Optional[Dict[str, Any]]:
    ensure_remote()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM remote_tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def list_recent_tasks(user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    ensure_remote()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, status, substr(prompt,1,80) AS prompt_preview, created_at, finished_at
            FROM remote_tasks WHERE user_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]

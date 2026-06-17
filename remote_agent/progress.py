"""Живой статус задачи в Telegram (редактируемое сообщение + typing)."""

from __future__ import annotations

import html
import threading
import time
from typing import Callable

from remote_agent.notify_mac import (
    edit_status_message,
    remove_status_message,
    send_chat_action,
    send_status_message,
)
from remote_agent.voice import VOICE_PREFIX, format_prompt_preview


class TaskProgress:
    """Показывает этапы: Mac взял → расшифровка → агент → готово."""

    def __init__(self, chat_id: int, task_id: int, *, raw_prompt: str = "") -> None:
        self.chat_id = chat_id
        self.task_id = task_id
        self.raw_prompt = raw_prompt
        self._msg_id: int | None = None
        self._stage = ""
        self._detail = ""
        self._started = time.time()
        self._stop = threading.Event()
        self._pulse: threading.Thread | None = None

    def _elapsed(self) -> str:
        sec = int(time.time() - self._started)
        m, s = divmod(sec, 60)
        return f"{m}:{s:02d}"

    def _render(self) -> str:
        preview = html.escape(format_prompt_preview(self.raw_prompt, 120))
        detail = html.escape(self._detail) if self._detail else ""
        lines = [
            f"⚙️ <b>Задача #{self.task_id}</b> — {html.escape(self._stage)}",
            f"⏱ {self._elapsed()}",
        ]
        if preview:
            lines.append(f"📩 {preview}")
        if detail:
            lines.append(f"<i>{detail}</i>")
        lines.append("\n<i>Статус обновляется автоматически</i>")
        return "\n".join(lines)

    def _push(self) -> None:
        if self.chat_id <= 0:
            return
        text = self._render()
        if self._msg_id is None:
            self._msg_id = send_status_message(self.chat_id, text)
        else:
            edit_status_message(self.chat_id, self._msg_id, text)

    def start(self, stage: str, *, detail: str = "") -> None:
        self._stage = stage
        self._detail = detail
        self._push()
        send_chat_action(self.chat_id, "typing")
        self._start_pulse()

    def update(self, stage: str, *, detail: str = "") -> None:
        self._stage = stage
        self._detail = detail
        self._push()
        low = stage.lower()
        action = "record_voice" if "голос" in low or "расшифр" in low else "typing"
        send_chat_action(self.chat_id, action)

    def stop(self) -> None:
        self._stop.set()
        if self._pulse and self._pulse.is_alive():
            self._pulse.join(timeout=1)

    def done(self) -> None:
        self.stop()
        if self._msg_id and self.chat_id > 0:
            try:
                remove_status_message(self.chat_id, self._msg_id)
            except Exception:
                pass

    def _start_pulse(self) -> None:
        def loop() -> None:
            while not self._stop.wait(40):
                if self.chat_id <= 0:
                    continue
                send_chat_action(self.chat_id, "typing")
                low = self._stage.lower()
                if "думает" in low or "расшифр" in low or "работ" in low:
                    self._detail = f"⏳ {self._elapsed()} — ещё работаю, не завис"
                    try:
                        self._push()
                    except Exception:
                        pass

        self._pulse = threading.Thread(target=loop, daemon=True)
        self._pulse.start()


def run_with_progress(
    progress: TaskProgress,
    fn: Callable[[], tuple[str, str]],
    *,
    stage: str = "🧠 Cursor Agent думает…",
    detail: str = "Большие задачи — до 15 мин",
) -> tuple[str, str]:
    progress.update(stage, detail=detail)
    try:
        return fn()
    finally:
        progress.update("📤 Отправляю ответ…", detail="")

"""Единое оформление уведомлений агента в Telegram."""

from __future__ import annotations

import html

from remote_agent.notify import _split_message
from remote_agent.telegram_format import agent_text_to_telegram_html
from remote_agent.voice import format_prompt_preview


def build_task_messages(
    task_id: int,
    *,
    prompt: str = "",
    result: str = "",
    error: str = "",
    qa_note: str = "",
    preview_limit: int = 220,
    body_limit: int = 12000,
) -> list[str]:
    """HTML-чанки для sendMessage (parse_mode=HTML)."""
    preview = html.escape(format_prompt_preview(prompt, preview_limit))

    if error:
        err_html = agent_text_to_telegram_html(error[:4000]) or html.escape(error[:4000])
        text = (
            f"❌ <b>Не получилось · задача #{task_id}</b>\n\n"
            f"<b>📩 Запрос:</b>\n{preview}\n\n"
            f"<b>Ошибка:</b>\n{err_html}"
        )
        return _split_message(text)

    body = agent_text_to_telegram_html(result, limit=body_limit)
    if not body:
        body = "Агент выполнил задачу, но не оставил текст. Проверьте вложенные файлы."

    qa_html = ""
    if qa_note.strip():
        qa_html = "\n\n" + agent_text_to_telegram_html(qa_note, limit=2000)

    text = (
        f"✅ <b>Готово · задача #{task_id}</b>\n\n"
        f"<i>Запрос:</i> {preview}\n\n"
        f"{body}{qa_html}"
    )
    return _split_message(text)

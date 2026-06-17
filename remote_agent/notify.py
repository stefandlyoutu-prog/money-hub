"""Уведомление в Telegram о результате задачи."""

from __future__ import annotations

import html
import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

_INTERNAL_PREFIXES = ("__INTERNAL__:", "__probe__")


def _skip_notify(prompt: str) -> bool:
    p = (prompt or "").strip()
    return any(p.startswith(x) for x in _INTERNAL_PREFIXES)


def _preview_prompt(prompt: str, limit: int = 300) -> str:
    from remote_agent.voice import VOICE_PREFIX

    lines = []
    for line in (prompt or "").split("\n"):
        if line.startswith(VOICE_PREFIX):
            continue
        if line.strip():
            lines.append(line.strip())
    text = "\n".join(lines).strip() or "(без текста)"
    return html.escape(text[:limit])


async def send_task_result(
    user_id: int,
    task_id: int,
    *,
    prompt: str = "",
    result: str = "",
    error: str = "",
) -> None:
    if user_id <= 0:
        return
    if _skip_notify(prompt):
        logger.info("skip notify internal task #%s", task_id)
        return
    preview = _preview_prompt(prompt)
    if error:
        text = (
            f"❌ <b>Не получилось (задача #{task_id})</b>\n\n"
            f"<b>Вы просили:</b>\n{preview}\n\n"
            f"<b>Ошибка:</b>\n{html.escape(error[:3000])}"
        )
    else:
        body = html.escape(result[:3500]) if result else "Агент отработал, но не написал текст ответа."
        text = (
            f"✅ <b>Готово (задача #{task_id})</b>\n\n"
            f"<b>Вы просили:</b>\n{preview}\n\n"
            f"<b>Ответ Cursor:</b>\n{body}"
        )

    from money_bot.cloud import _bot

    if _bot:
        try:
            chunks = _split_message(text)
            for chunk in chunks:
                await _bot.send_message(user_id, chunk, parse_mode="HTML")
            return
        except Exception as e:
            logger.warning("notify via bot failed task %s: %s", task_id, e)

    token = os.getenv("MONEY_BOT_TOKEN", "").strip()
    if not token:
        logger.warning("notify task %s: no bot token", task_id)
        return
    for chunk in _split_message(text):
        payload = json.dumps(
            {"chat_id": user_id, "text": chunk, "parse_mode": "HTML"}
        ).encode()
        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                ),
                timeout=30,
            )
        except Exception as e:
            logger.warning("notify via HTTP failed task %s: %s", task_id, e)


def _split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    while text:
        parts.append(text[:limit])
        text = text[limit:]
    return parts

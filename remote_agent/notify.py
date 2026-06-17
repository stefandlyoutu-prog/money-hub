"""Уведомление в Telegram о результате задачи."""

from __future__ import annotations

import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)


async def send_task_result(user_id: int, task_id: int, *, result: str = "", error: str = "") -> None:
    if user_id <= 0:
        return
    if error:
        text = f"❌ <b>Задача #{task_id}</b>\n\n{error[:3500]}"
    else:
        body = result[:3800] if result else "(пустой ответ)"
        text = f"✅ <b>Задача #{task_id} готова</b>\n\n{body}"

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

"""Уведомление в Telegram о результате задачи."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def send_task_result(user_id: int, task_id: int, *, result: str = "", error: str = "") -> None:
    from money_bot.cloud import _bot

    if not _bot or user_id <= 0:
        return
    if error:
        text = f"❌ <b>Задача #{task_id}</b>\n\n{error[:3500]}"
    else:
        body = result[:3800] if result else "(пустой ответ)"
        text = f"✅ <b>Задача #{task_id} готова</b>\n\n{body}"
    try:
        await _bot.send_message(user_id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning("notify task %s: %s", task_id, e)

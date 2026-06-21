"""Уведомление в Telegram о результате задачи."""

from __future__ import annotations

import html
import json
import logging
import urllib.request

logger = logging.getLogger(__name__)

_INTERNAL_PREFIXES = ("__INTERNAL__:", "__probe__")


def _skip_notify(prompt: str) -> bool:
    p = (prompt or "").strip()
    return any(p.startswith(x) for x in _INTERNAL_PREFIXES)


def _split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    while text:
        parts.append(text[:limit])
        text = text[limit:]
    return parts


async def send_task_result(
    user_id: int,
    task_id: int,
    *,
    prompt: str = "",
    result: str = "",
    error: str = "",
    bot_slot: str = "1",
) -> None:
    if user_id <= 0:
        return
    if _skip_notify(prompt):
        logger.info("skip notify internal task #%s", task_id)
        return

    from remote_agent.notify_message import build_task_messages

    chunks = build_task_messages(
        task_id, prompt=prompt, result=result, error=error
    )

    from money_bot.bot_tokens import token_for_slot
    from money_bot.cloud import get_bot_for_slot

    bot = get_bot_for_slot(bot_slot)
    if bot:
        try:
            for chunk in chunks:
                await bot.send_message(user_id, chunk, parse_mode="HTML")
            return
        except Exception as e:
            logger.warning("notify via bot failed task %s: %s", task_id, e)

    token = token_for_slot(bot_slot)
    if not token:
        logger.warning("notify task %s: no bot token", task_id)
        return
    for chunk in chunks:
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

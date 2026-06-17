"""Telegram: удалённое управление Cursor Agent с телефона."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from business_dashboard.config import MONEY_ADMIN_IDS
from remote_agent.storage import create_task, list_recent_tasks, worker_status

logger = logging.getLogger(__name__)
router = Router()

_agent_mode: set[int] = set()


def _allowed(uid: int | None) -> bool:
    if not MONEY_ADMIN_IDS:
        return True
    return uid is not None and uid in MONEY_ADMIN_IDS


def _status_text() -> str:
    st = worker_status()
    if st["online"]:
        mac = f"🟢 Mac онлайн ({st.get('hostname') or 'worker'})"
    else:
        mac = "😴 Mac спит или воркер не запущен — задача встанет в очередь"
    return (
        f"{mac}\n"
        f"Очередь: {st['queued']} · выполняется: {st['running']}\n"
        f"Agent: {st.get('agent_version') or '—'}"
    )


async def _submit(message: Message, prompt: str) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not prompt.strip():
        await message.answer("Напиши задачу текстом или голосом.")
        return
    task = create_task(uid, prompt.strip())
    st = worker_status()
    if st["online"]:
        hint = "⏳ Mac принял в очередь, выполняю…"
    else:
        hint = (
            "📥 Задача #{} в очереди.\n"
            "Mac сейчас недоступен — выполню, когда проснётся "
            "(воркер на Wi‑Fi подхватит автоматически)."
        ).format(task["id"])
    await message.answer(
        f"{hint}\n\n<b>Задача #{task['id']}</b>\n"
        f"<i>{prompt[:500]}</i>",
        parse_mode="HTML",
    )


@router.message(Command("agent"))
async def cmd_agent(message: Message, command: CommandObject) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа.")
        return
    sub = (command.args or "").strip().lower()
    if sub in ("", "help"):
        await message.answer(
            "🖥 <b>Управление Cursor с телефона</b>\n\n"
            "/cmd текст — одна задача\n"
            "/agent on — любое сообщение = задача\n"
            "/agent off — выключить режим\n"
            "/agent status — Mac онлайн?\n"
            "/agent list — последние задачи\n"
            "🎤 Голосовое — распознаю и отправлю агенту\n\n"
            + _status_text(),
            parse_mode="HTML",
        )
        return
    if sub == "on":
        _agent_mode.add(uid)
        await message.answer("✅ Режим агента включён. Пиши задачи обычным текстом.\n\n" + _status_text())
        return
    if sub == "off":
        _agent_mode.discard(uid)
        await message.answer("Режим агента выключен. Используй /cmd …")
        return
    if sub == "status":
        await message.answer(_status_text())
        return
    if sub == "list":
        rows = list_recent_tasks(uid)
        if not rows:
            await message.answer("Задач пока нет.")
            return
        lines = ["<b>Последние задачи</b>\n"]
        for r in rows:
            lines.append(f"#{r['id']} {r['status']} — {r['prompt_preview']}")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return
    await _submit(message, command.args or "")


@router.message(Command("cmd"))
async def cmd_cmd(message: Message, command: CommandObject) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        return
    text = (command.args or "").strip()
    if not text:
        await message.answer("Пример:\n/cmd добавь в m-oracul пуш при оплате")
        return
    await _submit(message, text)


@router.message(F.text & ~F.text.startswith("/"))
async def agent_mode_text(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid) or uid not in _agent_mode:
        return
    await _submit(message, message.text or "")


@router.message(F.voice | F.audio)
async def agent_voice(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        return
    status = await message.answer("🎤 Слушаю…")
    try:
        from aiogram import Bot

        bot: Bot = message.bot
        file = await bot.get_file(message.voice.file_id if message.voice else message.audio.file_id)
        data = await bot.download_file(file.file_path)
        audio_bytes = data.read()
        text = await _transcribe(audio_bytes)
        if not text:
            await status.edit_text("Не разобрал голос — напиши текстом.")
            return
        cap = (message.caption or "").strip()
        prompt = f"{cap}\n{text}".strip() if cap else text
        await status.edit_text(f"🎤 Распознано:\n<i>{text[:400]}</i>", parse_mode="HTML")
        await _submit(message, prompt)
    except Exception as e:
        logger.exception("voice remote: %s", e)
        await status.edit_text(f"Ошибка голоса: {e}")


async def _transcribe(audio_bytes: bytes) -> str:
    """Groq/OpenAI whisper или заглушка."""
    import os

    key = os.getenv("GROK_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    if not key:
        return ""
    import aiohttp

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    form = aiohttp.FormData()
    form.add_field("file", audio_bytes, filename="voice.ogg", content_type="audio/ogg")
    form.add_field("model", "whisper-large-v3")
    headers = {"Authorization": f"Bearer {key}"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=form, headers=headers, timeout=aiohttp.ClientTimeout(total=90)) as r:
            if r.status != 200:
                return ""
            data = await r.json()
            return (data.get("text") or "").strip()

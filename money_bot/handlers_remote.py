"""Telegram: удалённое управление Cursor Agent с телефона."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from business_dashboard.config import MONEY_ADMIN_IDS
from remote_agent.storage import create_task, list_recent_tasks, worker_status
from remote_agent.voice import VOICE_PREFIX

logger = logging.getLogger(__name__)
router = Router()

# По умолчанию любой текст админа = задача; /agent off временно отключает
_agent_off: set[int] = set()


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
    try:
        task = create_task(uid, prompt.strip())
        st = worker_status()
        if st["online"]:
            hint = "⏳ Mac принял в очередь, выполняю…"
        else:
            hint = (
                "📥 Задача #{} в очереди.\n"
                "Mac сейчас недоступен — выполню, когда проснётся."
            ).format(task["id"])
        await message.answer(
            f"{hint}\n\n"
            f"<b>Задача #{task['id']}</b>\n"
            f"<b>Ваш запрос:</b>\n<i>{prompt[:500].replace('<', '')}</i>\n\n"
            f"Когда выполнится — пришлю ответ сюда.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("submit task: %s", e)
        await message.answer(f"❌ Не удалось создать задачу: {e}")


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
            "Любой текст — сразу задача (по умолчанию)\n"
            "/agent off — не отправлять текст как задачу\n"
            "/agent on — снова включить\n"
            "/agent status — Mac онлайн?\n"
            "/agent list — последние задачи\n"
            "🎤 Голосовое — распознаю и отправлю агенту\n\n"
            + _status_text(),
            parse_mode="HTML",
        )
        return
    if sub == "on":
        _agent_off.discard(uid)
        await message.answer("✅ Любой текст снова уходит агенту.\n\n" + _status_text())
        return
    if sub == "off":
        _agent_off.add(uid)
        await message.answer("Режим агента выключен. Используй /cmd … или /agent on")
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
        await message.answer("Нет доступа.")
        return
    text = (command.args or "").strip()
    if not text:
        await message.answer("Пример:\n/cmd добавь в m-oracul пуш при оплате")
        return
    await _submit(message, text)


@router.message(F.text & ~F.text.startswith("/"))
async def agent_mode_text(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        return
    if uid in _agent_off:
        await message.answer(
            "Режим агента выключен (/agent off).\n"
            "Напиши /cmd … или включи /agent on"
        )
        return
    await _submit(message, message.text or "")


@router.message(F.voice | F.audio)
async def agent_voice(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа.")
        return
    file_id = (message.voice or message.audio).file_id
    cap = (message.caption or "").strip()
    payload = f"{VOICE_PREFIX}{file_id}"
    if cap:
        payload = f"{cap}\n{payload}"
    await message.answer(
        "🎤 <b>Голос принят</b>\n\nMac расшифрует и выполнит задачу…\n\n" + _status_text(),
        parse_mode="HTML",
    )
    await _submit(message, payload)

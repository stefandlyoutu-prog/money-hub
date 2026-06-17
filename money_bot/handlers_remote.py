"""Telegram: удалённое управление Cursor Agent с телефона."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from business_dashboard.config import MONEY_ADMIN_IDS
from remote_agent.attachments import DOC_PREFIX, PHOTO_PREFIX
from remote_agent.direct import wrap_direct_command
from remote_agent.storage import create_task, list_recent_tasks, worker_status
from remote_agent.voice import VOICE_PREFIX, format_prompt_preview

logger = logging.getLogger(__name__)
router = Router()

_agent_off: set[int] = set()

_CAPABILITIES = (
    "🖥 <b>Полное управление Mac через @MS_Moneybot</b>\n\n"
    "<b>Текст / голос</b> — задача Cursor Agent (код, деплой, 3D, таблицы…)\n"
    "<b>📎 Файл / фото</b> — отправь с подписью = задача + файл на Mac\n\n"
    "<b>Быстрые команды Mac</b> (без агента):\n"
    "/mac open Safari — открыть приложение\n"
    "/mac open ~/Downloads — открыть папку\n"
    "/mac find budget — поиск файлов\n"
    "/mac ls ~/Projects — список папки\n"
    "/mac run git status — shell (если включён)\n"
    "/mac sleep — сон Mac\n"
    "/mac power shutdown confirm — выключение\n"
    "/mac power restart confirm — перезагрузка\n\n"
    "<b>Агент</b>\n"
    "/cmd … — одна задача\n"
    "/agent status · /agent list\n"
    "/agent off — не отправлять текст как задачу\n\n"
    "Агент может: править код, создавать файлы (Word/Excel через Python), "
    "Google Таблицы (если есть доступ), 3D-модели, деплой Render, "
    "запускать приложения. Файлы пришлёт обратно в чат.\n\n"
)


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
    if not prompt.strip():
        await message.answer("Напиши задачу текстом, голосом или файлом с подписью.")
        return
    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        task = create_task(message.from_user.id if message.from_user else 0, prompt.strip())
        st = worker_status()
        if st["online"]:
            hint = "⏳ Mac онлайн — скоро придёт <b>живой статус</b> задачи"
        else:
            hint = f"📥 Задача #{task['id']} в очереди — Mac offline, выполню когда проснётся"
        await message.answer(
            f"{hint}\n\n"
            f"<b>Задача #{task['id']}</b>\n"
            f"<b>Ваш запрос:</b>\n<i>{format_prompt_preview(prompt).replace('<', '')}</i>\n\n"
            f"Этапы: Mac взял → расшифровка (голос) → агент → ответ.\n"
            f"Сообщение со статусом обновляется каждые 40 сек.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("submit task: %s", e)
        await message.answer(f"❌ Не удалось создать задачу: {e}")


@router.message(Command("cap"))
async def cmd_cap(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа.")
        return
    await message.answer(_CAPABILITIES + _status_text(), parse_mode="HTML")


@router.message(Command("mac"))
async def cmd_mac(message: Message, command: CommandObject) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа.")
        return
    args = (command.args or "").strip()
    if not args:
        await message.answer("Пример:\n/mac open Safari\n/mac find report.xlsx\nСписок: /cap")
        return
    parts = args.split(maxsplit=1)
    sub = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    await _submit(message, wrap_direct_command(sub, rest))


@router.message(Command("agent"))
async def cmd_agent(message: Message, command: CommandObject) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа.")
        return
    sub = (command.args or "").strip().lower()
    if sub in ("", "help"):
        await message.answer(_CAPABILITIES + _status_text(), parse_mode="HTML")
        return
    if sub == "on":
        _agent_off.discard(uid)
        await message.answer("✅ Любой текст снова уходит агенту.\n\n" + _status_text())
        return
    if sub == "off":
        _agent_off.add(uid)
        await message.answer("Режим выключен. /cmd … или /agent on")
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
            preview = format_prompt_preview(r.get("prompt_preview") or "")
            lines.append(f"#{r['id']} {r['status']} — {preview[:80]}")
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
        await message.answer("Пример:\n/cmd создай google таблицу с планом на неделю")
        return
    await _submit(message, text)


@router.message(F.text & ~F.text.startswith("/"))
async def agent_mode_text(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        return
    if uid in _agent_off:
        await message.answer("Режим выключен. /cmd … или /agent on")
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
    await message.bot.send_chat_action(message.chat.id, ChatAction.RECORD_VOICE)
    await message.answer(
        "🎤 <b>Голос принят</b>\n\n"
        "Сейчас придёт сообщение со статусом:\n"
        "расшифровка → агент → ответ.\n\n" + _status_text(),
        parse_mode="HTML",
    )
    await _submit(message, payload)


@router.message(F.photo)
async def agent_photo(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа.")
        return
    photo = message.photo[-1]
    cap = (message.caption or "").strip() or "Обработай это фото"
    payload = f"{cap}\n{PHOTO_PREFIX}{photo.file_id}"
    await message.answer("📷 Фото принято — отправлю на Mac вместе с задачей.", parse_mode="HTML")
    await _submit(message, payload)


@router.message(F.document)
async def agent_document(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа.")
        return
    doc = message.document
    cap = (message.caption or "").strip() or f"Обработай файл {doc.file_name or 'document'}"
    name = doc.file_name or "document.bin"
    payload = f"{cap}\n{DOC_PREFIX}{doc.file_id}|{name}"
    await message.answer(f"📎 Файл <b>{name}</b> принят.", parse_mode="HTML")
    await _submit(message, payload)

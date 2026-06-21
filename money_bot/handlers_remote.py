"""Telegram: удалённое управление Cursor Agent с телефона."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from business_dashboard.config import MONEY_ADMIN_IDS
from remote_agent.attachments import DOC_PREFIX, PHOTO_PREFIX, VIDEO_NOTE_PREFIX, VIDEO_PREFIX
from remote_agent.direct import wrap_direct_command
from remote_agent.hub_client import create_task_remote, use_remote_hub_queue, worker_status_remote
from remote_agent.storage import create_task, list_recent_tasks, worker_status
from remote_agent.voice import VOICE_PREFIX, format_prompt_preview
from money_bot.bot_tokens import slot_for_token

logger = logging.getLogger(__name__)
router = Router()

_agent_off: set[int] = set()

_CAPABILITIES = (
    "🖥 <b>Управление Mac через Telegram-бота</b>\n\n"
    "<b>Текст / голос</b> — задача Cursor Agent (код, деплой, 3D, таблицы…)\n"
    "<b>📎 Файл / фото / видео</b> — отправь с подписью = задача + файл на Mac\n\n"
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
    try:
        st = worker_status_remote() if use_remote_hub_queue() else worker_status()
    except Exception:
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
        bot_slot = slot_for_token(getattr(message.bot, "token", None))
        if use_remote_hub_queue():
            task = create_task_remote(
                message.from_user.id if message.from_user else 0,
                prompt.strip(),
                bot_slot=bot_slot,
            )
        else:
            task = create_task(
                message.from_user.id if message.from_user else 0,
                prompt.strip(),
                bot_slot=bot_slot,
            )
        try:
            st = worker_status_remote() if use_remote_hub_queue() else worker_status()
        except Exception:
            st = worker_status()
        if st["online"]:
            hint = "⏳ Mac онлайн — скоро придёт <b>живой статус</b> задачи"
        else:
            hint = f"📥 Задача #{task['id']} в очереди — Mac offline, выполню когда проснётся"
        reply_bot = ""
        try:
            from remote_agent.hub_client import render_bot_username

            render_u = (render_bot_username(bot_slot) or "").strip().lstrip("@")
            if render_u and render_u != (getattr(message.bot, "id", None) or ""):
                me = await message.bot.get_me()
                if render_u != (me.username or ""):
                    reply_bot = (
                        f"\n\n📬 <b>Ответ придёт в @{render_u}</b> — "
                        f"основной бот на телефоне (не @{me.username})."
                    )
        except Exception:
            pass
        await message.answer(
            f"{hint}\n\n"
            f"<b>Задача #{task['id']}</b>\n"
            f"<b>Ваш запрос:</b>\n<i>{format_prompt_preview(prompt).replace('<', '')}</i>\n\n"
            f"Этапы: Mac взял → расшифровка (голос) → агент → ответ.\n"
            f"Сообщение со статусом обновляется каждые 40 сек."
            f"{reply_bot}",
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


_VIDEO_MIMES = frozenset(
    {"video/mp4", "video/quicktime", "video/webm", "video/x-m4v", "video/mpeg"}
)


def _is_video_document(message: Message) -> bool:
    doc = message.document
    if not doc:
        return False
    mime = (doc.mime_type or "").lower()
    if mime in _VIDEO_MIMES or mime.startswith("video/"):
        return True
    name = (doc.file_name or "").lower()
    return any(name.endswith(ext) for ext in (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"))


@router.message(F.document)
async def agent_document(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа.")
        return
    doc = message.document
    if _is_video_document(message):
        cap = (message.caption or "").strip() or "Извлеки аудио из этого видео и пришли mp3"
        name = doc.file_name or f"video_{doc.file_unique_id}.mp4"
        payload = f"{cap}\n{VIDEO_PREFIX}{doc.file_id}|{name}"
        await message.answer(
            "🎬 <b>Видео (файл) принято</b> — скачаю на Mac и извлеку аудио в mp3.",
            parse_mode="HTML",
        )
        await _submit(message, payload)
        return
    cap = (message.caption or "").strip() or f"Обработай файл {doc.file_name or 'document'}"
    name = doc.file_name or "document.bin"
    payload = f"{cap}\n{DOC_PREFIX}{doc.file_id}|{name}"
    await message.answer(f"📎 Файл <b>{name}</b> принят.", parse_mode="HTML")
    await _submit(message, payload)


@router.message(F.video)
async def agent_video(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа.")
        return
    video = message.video
    cap = (message.caption or "").strip() or "Извлеки аудио из этого видео и пришли mp3"
    name = (video.file_name or f"video_{video.file_unique_id}.mp4").strip()
    payload = f"{cap}\n{VIDEO_PREFIX}{video.file_id}|{name}"
    await message.answer(
        "🎬 <b>Видео принято</b> — скачаю на Mac. "
        "Если нужно только аудио — извлеку и пришлю mp3.",
        parse_mode="HTML",
    )
    await _submit(message, payload)


@router.message(F.video_note)
async def agent_video_note(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа.")
        return
    note = message.video_note
    cap = (message.caption or "").strip() or "Извлеки аудио из этого видео-кружка и пришли mp3"
    payload = f"{cap}\n{VIDEO_NOTE_PREFIX}{note.file_id}|video_note.mp4"
    await message.answer("🎬 Видео-кружок принят — отправлю на Mac.", parse_mode="HTML")
    await _submit(message, payload)


@router.message()
async def agent_unhandled(message: Message) -> None:
    """Стикеры, опросы и прочее — не молчим."""
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        return
    if uid in _agent_off:
        return
    kind = message.content_type or "unknown"
    await message.answer(
        f"Тип «{kind}» пока не поддерживается.\n"
        "Отправь текст, голос, фото, видео или файл с подписью.\n"
        "Список: /cap",
        parse_mode="HTML",
    )

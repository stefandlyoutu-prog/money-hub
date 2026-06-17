"""Отправка результатов с Mac (текст + файлы)."""

from __future__ import annotations

import html
import json
import mimetypes
import os
import urllib.request
from pathlib import Path

from remote_agent.attachments import strip_file_markers
from remote_agent.notify import _INTERNAL_PREFIXES, _split_message
from remote_agent.voice import format_prompt_preview

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_MAX_ATTACH_MB = int(os.getenv("REMOTE_MAX_ATTACH_MB", "45"))


def _token() -> str:
    return os.getenv("MONEY_BOT_TOKEN", "").strip()


def _skip_notify(prompt: str) -> bool:
    p = (prompt or "").strip()
    return any(p.startswith(x) for x in _INTERNAL_PREFIXES)


def _tg_post(method: str, data: dict, *, files: dict | None = None) -> dict:
    token = _token()
    if not token:
        return {}
    url = f"https://api.telegram.org/bot{token}/{method}"
    if files:
        import uuid

        boundary = uuid.uuid4().hex
        body = b""
        for k, v in data.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for field, (fname, content, mime) in files.items():
            body += f"--{boundary}\r\n".encode()
            body += (
                f'Content-Disposition: form-data; name="{field}"; filename="{fname}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            ).encode()
            body += content
            body += b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": _BROWSER_UA,
            },
            method="POST",
        )
    else:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": _BROWSER_UA},
            method="POST",
        )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def send_chat_action(chat_id: int, action: str = "typing") -> None:
    if chat_id <= 0:
        return
    try:
        _tg_post("sendChatAction", {"chat_id": chat_id, "action": action})
    except Exception:
        pass


def send_status_message(chat_id: int, text: str) -> int | None:
    if chat_id <= 0:
        return None
    try:
        data = _tg_post(
            "sendMessage",
            {"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )
        return int(data.get("result", {}).get("message_id", 0)) or None
    except Exception:
        return None


def edit_status_message(chat_id: int, message_id: int | None, text: str) -> None:
    if chat_id <= 0 or not message_id:
        return
    try:
        _tg_post(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
            },
        )
    except Exception:
        pass


def remove_status_message(chat_id: int, message_id: int | None) -> None:
    if chat_id <= 0 or not message_id:
        return
    try:
        _tg_post("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
    except Exception:
        pass


def send_photo(chat_id: int, path: str, *, caption: str = "") -> None:
    p = Path(path).expanduser()
    if not p.is_file():
        return
    if p.stat().st_size > _MAX_ATTACH_MB * 1024 * 1024:
        return
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption[:1024]
    _tg_post(
        "sendPhoto",
        data,
        files={"photo": (p.name, p.read_bytes(), mime)},
    )


def send_document(chat_id: int, path: str, *, caption: str = "") -> None:
    p = Path(path).expanduser()
    if not p.is_file():
        return
    if p.stat().st_size > _MAX_ATTACH_MB * 1024 * 1024:
        _tg_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": f"Файл слишком большой для Telegram ({p.name})",
            },
        )
        return
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption[:1024]
    _tg_post(
        "sendDocument",
        data,
        files={"document": (p.name, p.read_bytes(), mime)},
    )


def notify_task_result(
    user_id: int,
    task_id: int,
    *,
    prompt: str = "",
    result: str = "",
    error: str = "",
    extra_files: list[str] | None = None,
) -> None:
    if user_id <= 0 or _skip_notify(prompt):
        return
    preview = html.escape(format_prompt_preview(prompt, 300))
    cleaned, marked_files = strip_file_markers(result)
    all_files: list[str] = []
    seen: set[str] = set()
    for p in (extra_files or []) + marked_files:
        rp = str(Path(p).expanduser())
        if rp not in seen and Path(rp).is_file():
            seen.add(rp)
            all_files.append(rp)

    qa_note = ""
    from remote_agent.quality_gate import is_3d_task, validate_delivery

    if all_files and is_3d_task(prompt, all_files):
        qa = validate_delivery(all_files, prompt=prompt, strict=True)
        all_files = qa.ok_files
        if qa.issues:
            qa_note = "\n\n" + qa.summary_ru()
        if not qa.passed and not all_files:
            error = error or "QA 3D не пройден — файлы не отправлены.\n" + "\n".join(qa.issues[:8])

    if error:
        text = (
            f"❌ <b>Не получилось (задача #{task_id})</b>\n\n"
            f"<b>📩 Ваш запрос:</b>\n{preview}\n\n"
            f"<b>Ошибка:</b>\n{html.escape(error[:3000])}"
        )
        for chunk in _split_message(text):
            _tg_post(
                "sendMessage",
                {"chat_id": user_id, "text": chunk, "parse_mode": "HTML"},
            )
        return

    body = html.escape(cleaned[:3500]) if cleaned else "Агент выполнил задачу."
    text = (
        f"✅ <b>Готово (задача #{task_id})</b>\n\n"
        f"<b>📩 Ваш запрос:</b>\n{preview}\n\n"
        f"<b>📋 Резюме агента:</b>\n{body}{qa_note}"
    )
    for chunk in _split_message(text):
        _tg_post(
            "sendMessage",
            {"chat_id": user_id, "text": chunk, "parse_mode": "HTML"},
        )
    for fp in all_files[:10]:
        try:
            ext = Path(fp).suffix.lower()
            if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                send_photo(user_id, fp, caption=Path(fp).name)
            else:
                send_document(user_id, fp, caption=Path(fp).name)
        except Exception:
            pass

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


def _token(bot_slot: str | None = None) -> str:
    from money_bot.bot_tokens import notify_token_for_slot

    return notify_token_for_slot(bot_slot or "1")


def _tokens_for_send(bot_slot: str = "1") -> list[str]:
    from money_bot.bot_tokens import notify_tokens_for_slot, render_tokens_for_slot

    seen: set[str] = set()
    ordered: list[str] = []
    for t in notify_tokens_for_slot(bot_slot) + render_tokens_for_slot(bot_slot):
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered


def _should_route_via_hub(bot_slot: str = "1") -> bool:
    from remote_agent.hub_client import prefer_hub_telegram

    return prefer_hub_telegram(bot_slot)


def _user_has_local_chat(user_id: int, bot_slot: str = "1") -> bool:
    if user_id <= 0:
        return False
    for token in _tokens_for_send(bot_slot)[:1]:
        try:
            url = f"https://api.telegram.org/bot{token}/getChat"
            payload = json.dumps({"chat_id": user_id}).encode()
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": _BROWSER_UA},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                return bool(json.load(r).get("ok"))
        except Exception:
            return False
    return False


def _skip_notify(prompt: str) -> bool:
    p = (prompt or "").strip()
    return any(p.startswith(x) for x in _INTERNAL_PREFIXES)


def _tg_post_direct(
    method: str,
    data: dict,
    *,
    files: dict | None = None,
    bot_slot: str = "1",
    tokens: list[str] | None = None,
) -> dict:
    from money_bot.bot_tokens import notify_tokens_for_slot, render_tokens_for_slot

    token_list = tokens or render_tokens_for_slot(bot_slot) or notify_tokens_for_slot(bot_slot)

    last_err: Exception | None = None
    for token in token_list:
        url = f"https://api.telegram.org/bot{token}/{method}"
        try:
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
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if (
                    method == "sendMessage"
                    and e.code == 400
                    and data.get("parse_mode") == "HTML"
                ):
                    plain = dict(data)
                    plain.pop("parse_mode", None)
                    req2 = urllib.request.Request(
                        url,
                        data=json.dumps(plain).encode(),
                        headers={"Content-Type": "application/json", "User-Agent": _BROWSER_UA},
                        method="POST",
                    )
                    with urllib.request.urlopen(req2, timeout=120) as r:
                        return json.load(r)
                raise
        except Exception as e:
            last_err = e
            continue
    if last_err:
        raise last_err
    return {}


def _push_raw_via_hub(chat_id: int, text: str, *, task_id: int = 0, bot_slot: str = "1") -> bool:
    """Статус через Render (@MS_Moneybot), если tg-call ещё не задеплоен."""
    from remote_agent.hub_notify import hub_available, push_notify

    if not hub_available() or chat_id <= 0 or not text.strip():
        return False
    ok, _ = push_notify(
        chat_id,
        task_id or 1,
        prompt="",
        result="",
        raw_text=text.strip()[:4000],
        bot_slot=bot_slot,
    )
    if ok:
        return True
    # Старый Render без raw_text — хотя бы текст в result (с обёрткой «Готово»)
    ok2, _ = push_notify(
        chat_id,
        task_id or 1,
        prompt="Статус",
        result=text.strip()[:3500],
        bot_slot=bot_slot,
    )
    return ok2


def _tg_post(
    method: str, data: dict, *, files: dict | None = None, bot_slot: str = "1"
) -> dict:
    if _should_route_via_hub(bot_slot):
        from remote_agent.hub_notify import push_tg_call

        tg_files: list[tuple[str, str, bytes, str]] = []
        if files:
            for field, (fname, content, mime) in files.items():
                tg_files.append((field, fname, content, mime))
        ok, err = push_tg_call(method, data, bot_slot=bot_slot, files=tg_files or None)
        if ok:
            return {"ok": True, "result": {}}
        # Render ещё без /tg-call — шлём токеном @MS_Moneybot напрямую
        if "404" in (err or "") or "Not Found" in (err or ""):
            from money_bot.bot_tokens import render_tokens_for_slot

            try:
                return _tg_post_direct(
                    method,
                    data,
                    files=files,
                    bot_slot=bot_slot,
                    tokens=render_tokens_for_slot(bot_slot),
                )
            except Exception:
                if method == "sendMessage" and data.get("text"):
                    if _push_raw_via_hub(
                        int(data["chat_id"]),
                        str(data["text"]),
                        bot_slot=bot_slot,
                    ):
                        return {"ok": True, "result": {"message_id": 0}}
                raise
        raise RuntimeError(err or "hub tg-call failed")

    return _tg_post_direct(method, data, files=files, bot_slot=bot_slot)


def send_chat_action(chat_id: int, action: str = "typing", *, bot_slot: str = "1") -> None:
    if chat_id <= 0:
        return
    try:
        _tg_post("sendChatAction", {"chat_id": chat_id, "action": action}, bot_slot=bot_slot)
    except Exception:
        pass


def send_status_message(chat_id: int, text: str, *, bot_slot: str = "1") -> int | None:
    if chat_id <= 0:
        return None
    try:
        data = _tg_post(
            "sendMessage",
            {"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            bot_slot=bot_slot,
        )
        return int(data.get("result", {}).get("message_id", 0)) or None
    except Exception:
        return None


def edit_status_message(
    chat_id: int, message_id: int | None, text: str, *, bot_slot: str = "1"
) -> None:
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
            bot_slot=bot_slot,
        )
    except Exception:
        pass


def remove_status_message(chat_id: int, message_id: int | None, *, bot_slot: str = "1") -> None:
    if chat_id <= 0 or not message_id:
        return
    try:
        _tg_post("deleteMessage", {"chat_id": chat_id, "message_id": message_id}, bot_slot=bot_slot)
    except Exception:
        pass


def send_photo(chat_id: int, path: str, *, caption: str = "", bot_slot: str = "1") -> None:
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
        bot_slot=bot_slot,
    )


def send_audio(chat_id: int, path: str, *, caption: str = "", bot_slot: str = "1") -> None:
    p = Path(path).expanduser()
    if not p.is_file():
        return
    if p.stat().st_size > _MAX_ATTACH_MB * 1024 * 1024:
        send_document(chat_id, str(p), caption=caption, bot_slot=bot_slot)
        return
    mime = mimetypes.guess_type(p.name)[0] or "audio/mpeg"
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption[:1024]
    _tg_post(
        "sendAudio",
        data,
        files={"audio": (p.name, p.read_bytes(), mime)},
        bot_slot=bot_slot,
    )


def send_document(chat_id: int, path: str, *, caption: str = "", bot_slot: str = "1") -> None:
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
            bot_slot=bot_slot,
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
        bot_slot=bot_slot,
    )


def notify_task_result(
    user_id: int,
    task_id: int,
    *,
    prompt: str = "",
    result: str = "",
    error: str = "",
    extra_files: list[str] | None = None,
    bot_slot: str = "1",
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

    from remote_agent.hub_notify import collect_files, hub_available, push_notify

    bot_hint = ""
    try:
        from remote_agent.hub_client import render_bot_username

        render_user = (render_bot_username(bot_slot) or "").strip().lstrip("@")
        local_user = (
            __import__("money_bot.bot_tokens", fromlist=["usernames"]).usernames().get(bot_slot, "")
        ).strip().lstrip("@")
        if render_user and local_user and render_user != local_user:
            bot_hint = f"\n\n📬 Ответ в @{render_user} (основной бот на телефоне)"
    except Exception:
        pass

    def _send_direct() -> None:
        if error:
            from remote_agent.notify_message import build_task_messages

            for chunk in build_task_messages(
                task_id, prompt=prompt, error=error
            ):
                _tg_post(
                    "sendMessage",
                    {"chat_id": user_id, "text": chunk, "parse_mode": "HTML"},
                    bot_slot=bot_slot,
                )
            return

        from remote_agent.notify_message import build_task_messages

        chunks = build_task_messages(
            task_id, prompt=prompt, result=cleaned, qa_note=qa_note
        )
        for i, chunk in enumerate(chunks):
            text = chunk + (bot_hint if i == len(chunks) - 1 and bot_hint else "")
            _tg_post(
                "sendMessage",
                {"chat_id": user_id, "text": text, "parse_mode": "HTML"},
                bot_slot=bot_slot,
            )
        for fp in all_files[:10]:
            ext = Path(fp).suffix.lower()
            if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                send_photo(user_id, fp, caption=Path(fp).name, bot_slot=bot_slot)
            elif ext in {".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac"}:
                send_audio(user_id, fp, caption=Path(fp).name, bot_slot=bot_slot)
            else:
                send_document(user_id, fp, caption=Path(fp).name, bot_slot=bot_slot)

    def _send_via_hub() -> bool:
        if not hub_available():
            return False
        result_text = cleaned if not error else ""
        if bot_hint and result_text and not error:
            result_text = result_text + bot_hint
        ok, hub_err = push_notify(
            user_id,
            task_id,
            prompt=prompt,
            result=result_text,
            error=error,
            files=collect_files(all_files) if not error else None,
            bot_slot=bot_slot,
        )
        if not ok:
            print(f"[remote] hub notify failed #{task_id}: {hub_err}")
        return ok

    # Пользователь с телефона пишет в @MS_Moneybot (Render), Mac polling — @M_onetest_bot.
    from remote_agent.hub_client import prefer_hub_telegram

    prefer_hub = hub_available() and (
        prefer_hub_telegram(bot_slot) or not _user_has_local_chat(user_id, bot_slot)
    )
    if prefer_hub and _send_via_hub():
        return

    try:
        _send_direct()
        return
    except Exception as e:
        print(f"[remote] direct notify failed #{task_id}: {e}")

    if hub_available() and _send_via_hub():
        return

    raise RuntimeError("Не удалось отправить ответ ни напрямую, ни через hub")

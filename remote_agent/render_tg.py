"""Синхронная отправка в Telegram с Render (urllib)."""

from __future__ import annotations

import json
import mimetypes
import urllib.request
from pathlib import Path

from money_bot.bot_tokens import token_for_slot

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _post(token: str, method: str, data: dict, *, files: dict | None = None) -> dict:
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
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={
                "Content-Type": "application/json",
                "User-Agent": _BROWSER_UA,
            },
            method="POST",
        )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def send_text(chat_id: int, text: str, *, bot_slot: str = "1") -> None:
    token = token_for_slot(bot_slot)
    for i in range(0, len(text), 4000):
        chunk = text[i : i + 4000]
        try:
            _post(
                token,
                "sendMessage",
                {"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"},
            )
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            _post(token, "sendMessage", {"chat_id": chat_id, "text": chunk})


def send_file_bytes(
    chat_id: int,
    filename: str,
    data: bytes,
    *,
    kind: str = "document",
    bot_slot: str = "1",
) -> None:
    from money_bot.bot_tokens import token_for_slot

    token = token_for_slot(bot_slot)
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    payload = {"chat_id": str(chat_id)}
    if kind == "photo":
        _post(
            token,
            "sendPhoto",
            payload,
            files={"photo": (filename, data, mime)},
        )
    elif kind == "audio":
        _post(
            token,
            "sendAudio",
            payload,
            files={"audio": (filename, data, mime or "audio/mpeg")},
        )
    else:
        _post(
            token,
            "sendDocument",
            payload,
            files={"document": (filename, data, mime)},
        )

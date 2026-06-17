"""Расшифровка голосовых через Groq Whisper (на Mac)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def transcribe_bytes(audio_bytes: bytes, *, filename: str = "voice.ogg") -> tuple[str, str]:
    """Возвращает (text, error)."""
    key = os.getenv("GROK_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return "", "GROK_API_KEY не задан в .env на Mac"

    boundary = "----RemoteAgentVoice"
    body = b""
    for name, val in (("model", "whisper-large-v3"),):
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n{val}\r\n'.encode()
    body += f"--{boundary}\r\n".encode()
    body += (
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: audio/ogg\r\n\r\n"
    ).encode()
    body += audio_bytes
    body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        return "", e.read().decode()[:300]
    except Exception as e:
        return "", str(e)

    text = (data.get("text") or "").strip()
    if not text:
        return "", "Whisper вернул пустой текст"
    return text, ""


def download_tg_file(file_id: str) -> tuple[bytes, str]:
    token = os.getenv("MONEY_BOT_TOKEN", "").strip()
    if not token:
        return b"", "MONEY_BOT_TOKEN не задан"
    meta = json.load(
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}",
            timeout=30,
        )
    )
    if not meta.get("ok"):
        return b"", meta.get("description", "getFile failed")
    path = meta["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{token}/{path}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read(), ""


VOICE_PREFIX = "__VOICE__:"


def resolve_prompt(raw: str) -> tuple[str, str]:
    """Голосовая задача → текст. Возвращает (prompt, error)."""
    if VOICE_PREFIX not in raw:
        return raw, ""
    cap_parts: list[str] = []
    file_id = ""
    for line in raw.split("\n"):
        if line.startswith(VOICE_PREFIX):
            file_id = line[len(VOICE_PREFIX) :].strip()
        elif line.strip():
            cap_parts.append(line.strip())
    if not file_id:
        return raw, "Нет file_id голосового"
    audio, err = download_tg_file(file_id)
    if err:
        return "", f"Не скачал голос: {err}"
    text, err = transcribe_bytes(audio)
    if err:
        return "", f"Whisper: {err}"
    cap = "\n".join(cap_parts).strip()
    prompt = f"{cap}\n{text}".strip() if cap else text
    return prompt, ""

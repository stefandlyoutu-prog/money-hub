"""Расшифровка голосовых через Groq Whisper (на Mac)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

VOICE_PREFIX = "__VOICE__:"

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _groq_api_key() -> str:
    return (
        os.getenv("GROQ_API_KEY", "").strip()
        or os.getenv("GROK_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )


def _api_headers(*, content_type: str | None = None) -> dict[str, str]:
    key = _groq_api_key()
    headers = {
        "Authorization": f"Bearer {key}",
        "User-Agent": _BROWSER_UA,
        "Accept": "application/json",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _groq_error_message(raw: str) -> str:
    low = raw.lower()
    if "1010" in raw or "error code: 1010" in low:
        return (
            "Groq заблокировал запрос (Cloudflare 1010). "
            "Обновите воркер — в новой версии это исправлено."
        )
    if "401" in raw or "invalid api key" in low:
        return "Неверный GROQ_API_KEY / GROK_API_KEY в .env на Mac"
    return raw[:300]


def format_prompt_preview(raw: str, limit: int = 500) -> str:
    """Текст для показа пользователю (без служебного __VOICE__)."""
    if VOICE_PREFIX not in raw:
        return (raw or "").strip()[:limit].replace("<", "")
    cap_parts: list[str] = []
    for line in (raw or "").split("\n"):
        if line.startswith(VOICE_PREFIX):
            continue
        if line.strip():
            cap_parts.append(line.strip())
    cap = "\n".join(cap_parts).strip()
    if cap:
        return f"🎤 Голос + подпись: {cap[:limit]}"
    return "🎤 Голосовое сообщение"


def transcribe_bytes(audio_bytes: bytes, *, filename: str = "voice.ogg") -> tuple[str, str]:
    """Возвращает (text, error)."""
    key = _groq_api_key()
    if not key:
        return "", "GROQ_API_KEY (или GROK_API_KEY) не задан в .env на Mac"

    if len(audio_bytes) < 100:
        return "", "Голосовой файл слишком маленький или пустой"

    boundary = "----RemoteAgentVoice"
    body = b""
    for name, val in (
        ("model", "whisper-large-v3"),
        ("language", "ru"),
        ("response_format", "json"),
    ):
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
        headers=_api_headers(content_type=f"multipart/form-data; boundary={boundary}"),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        return "", f"Whisper: {_groq_error_message(e.read().decode()[:400])}"
    except Exception as e:
        return "", f"Whisper: {e}"

    text = (data.get("text") or "").strip()
    if not text:
        return "", "Whisper вернул пустой текст — попробуй говорить громче или текстом"
    return text, ""


def download_tg_file(file_id: str) -> tuple[bytes, str, str]:
    """Возвращает (audio_bytes, filename, error)."""
    token = os.getenv("MONEY_BOT_TOKEN", "").strip()
    if not token:
        return b"", "", "MONEY_BOT_TOKEN не задан"
    try:
        meta_req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}",
            headers={"User-Agent": _BROWSER_UA},
        )
        meta = json.load(urllib.request.urlopen(meta_req, timeout=30))
    except Exception as e:
        return b"", "", f"getFile: {e}"
    if not meta.get("ok"):
        return b"", "", meta.get("description", "getFile failed")
    path = meta["result"]["file_path"]
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else "ogg"
    filename = f"voice.{ext}"
    url = f"https://api.telegram.org/file/bot{token}/{path}"
    try:
        file_req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
        with urllib.request.urlopen(file_req, timeout=120) as r:
            return r.read(), filename, ""
    except Exception as e:
        return b"", "", f"download: {e}"


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
    audio, filename, err = download_tg_file(file_id)
    if err:
        return "", f"Не скачал голос: {err}"
    text, err = transcribe_bytes(audio, filename=filename)
    if err:
        return "", err
    cap = "\n".join(cap_parts).strip()
    prompt = f"{cap}\n{text}".strip() if cap else text
    return prompt, ""

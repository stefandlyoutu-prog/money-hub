"""Расшифровка голосовых через Groq Whisper (на Mac)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

VOICE_PREFIX = "__VOICE__:"

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Groq/OpenAI Whisper — по расширению файла в multipart
_GROQ_EXTS = frozenset({"flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "opus", "wav", "webm"})
_EXT_ALIASES = {"oga": "ogg", "ogv": "ogg", "aac": "m4a", "weba": "webm"}


def _groq_api_key() -> str:
    return (
        os.getenv("GROQ_API_KEY", "").strip()
        or os.getenv("GROK_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )


def _api_headers(*, content_type: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {_groq_api_key()}",
        "User-Agent": _BROWSER_UA,
        "Accept": "application/json",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _groq_error_message(raw: str) -> str:
    low = raw.lower()
    if "1010" in raw or "error code: 1010" in low:
        return "Groq заблокировал запрос (Cloudflare 1010)."
    if "invalid api key" in low or '"code":401' in raw:
        return "Неверный GROQ_API_KEY / GROK_API_KEY в .env на Mac"
    if "must be one of the following types" in raw:
        return (
            "Формат голосового не подошёл для Whisper. "
            "Попробуй ещё раз или напиши текстом."
        )
    try:
        data = json.loads(raw)
        msg = data.get("error", {}).get("message")
        if msg:
            return msg[:300]
    except json.JSONDecodeError:
        pass
    return raw[:300]


def _detect_ext(audio_bytes: bytes, ext: str) -> str:
    ext = (ext or "").lower().lstrip(".")
    if ext in _EXT_ALIASES:
        ext = _EXT_ALIASES[ext]
    if ext in _GROQ_EXTS:
        return ext
    head = audio_bytes[:16]
    if head.startswith(b"OggS"):
        return "ogg"
    if head.startswith(b"ID3") or head[:2] == b"\xff\xfb":
        return "mp3"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "m4a"
    if head.startswith(b"RIFF"):
        return "wav"
    if head.startswith(b"fLaC"):
        return "flac"
    return "ogg"


def _mime_for_ext(ext: str) -> str:
    return {
        "ogg": "audio/ogg",
        "opus": "audio/opus",
        "mp3": "audio/mpeg",
        "mpeg": "audio/mpeg",
        "mpga": "audio/mpeg",
        "m4a": "audio/mp4",
        "mp4": "audio/mp4",
        "wav": "audio/wav",
        "webm": "audio/webm",
        "flac": "audio/flac",
    }.get(ext, "application/octet-stream")


def _ffmpeg_bin() -> str | None:
    for name in ("ffmpeg", "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        p = shutil.which(name) if not name.startswith("/") else name
        if p and Path(p).is_file():
            return p
    return None


def _convert_with_ffmpeg(audio_bytes: bytes, src_ext: str) -> tuple[bytes, str, str]:
    """→ mp3 если установлен ffmpeg."""
    ff = _ffmpeg_bin()
    if not ff:
        return audio_bytes, "", "no ffmpeg"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        src = td_path / f"in.{src_ext or 'bin'}"
        dst = td_path / "out.mp3"
        src.write_bytes(audio_bytes)
        try:
            subprocess.run(
                [ff, "-y", "-i", str(src), "-ac", "1", "-ar", "16000", str(dst)],
                capture_output=True,
                timeout=120,
                check=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            return audio_bytes, "", str(e)
        if dst.is_file() and dst.stat().st_size > 100:
            return dst.read_bytes(), "mp3", ""
    return audio_bytes, "", "ffmpeg empty output"


def prepare_audio_for_whisper(audio_bytes: bytes, filename: str) -> tuple[bytes, str, str]:
    """Нормализует аудио для Groq. Возвращает (bytes, filename, error)."""
    if len(audio_bytes) < 100:
        return b"", "", "Голосовой файл пустой"

    raw_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    ext = _detect_ext(audio_bytes, raw_ext)

    if ext not in _GROQ_EXTS:
        converted, new_ext, err = _convert_with_ffmpeg(audio_bytes, raw_ext or ext)
        if new_ext:
            ext = new_ext
            audio_bytes = converted

    if ext not in _GROQ_EXTS:
        converted, new_ext, _ = _convert_with_ffmpeg(audio_bytes, raw_ext or "oga")
        if new_ext in _GROQ_EXTS:
            audio_bytes, ext = converted, new_ext

    if ext not in _GROQ_EXTS:
        return b"", "", f"Неподдерживаемый формат аудио (.{raw_ext or '?'})"

    return audio_bytes, f"voice.{ext}", ""


def format_prompt_preview(raw: str, limit: int = 500) -> str:
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
    if not _groq_api_key():
        return "", "GROQ_API_KEY (или GROK_API_KEY) не задан в .env на Mac"

    audio_bytes, filename, prep_err = prepare_audio_for_whisper(audio_bytes, filename)
    if prep_err:
        return "", prep_err

    ext = filename.rsplit(".", 1)[-1].lower()
    mime = _mime_for_ext(ext)
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
        f"Content-Type: {mime}\r\n\r\n"
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
        return "", f"Whisper: {_groq_error_message(e.read().decode()[:500])}"
    except Exception as e:
        return "", f"Whisper: {e}"

    text = (data.get("text") or "").strip()
    if not text:
        return "", "Whisper вернул пустой текст — попробуй громче или текстом"
    return text, ""


def download_tg_file(file_id: str, *, bot_token: str | None = None) -> tuple[bytes, str, str]:
    from money_bot.bot_tokens import token_for_slot

    token = (bot_token or os.getenv("MONEY_BOT_TOKEN", "")).strip()
    if not token:
        token = token_for_slot("1")
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
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else "oga"
    filename = f"voice.{ext}"
    url = f"https://api.telegram.org/file/bot{token}/{path}"
    try:
        file_req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
        with urllib.request.urlopen(file_req, timeout=120) as r:
            return r.read(), filename, ""
    except Exception as e:
        return b"", "", f"download: {e}"


def resolve_prompt(raw: str, *, bot_token: str | None = None) -> tuple[str, str]:
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
    audio, filename, err = download_tg_file(file_id, bot_token=bot_token)
    if err:
        return "", f"Не скачал голос: {err}"
    text, err = transcribe_bytes(audio, filename=filename)
    if err:
        return "", err
    cap = "\n".join(cap_parts).strip()
    return (f"{cap}\n{text}".strip() if cap else text), ""

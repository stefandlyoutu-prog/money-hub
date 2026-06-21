"""Извлечение аудио из видео (ffmpeg) для задач с телефона."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from remote_agent.attachments import _VIDEO_EXTS


def _ffmpeg_bin() -> str | None:
    for name in ("ffmpeg", "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        p = shutil.which(name) if not name.startswith("/") else name
        if p and Path(p).is_file():
            return p
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).is_file():
            return bundled
    except Exception:
        pass
    return None


def is_video_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in _VIDEO_EXTS


def extract_audio_mp3(video_path: str | Path, *, out_dir: Path | None = None) -> tuple[str, str]:
    """Возвращает (path_to_mp3, error)."""
    src = Path(video_path).expanduser()
    if not src.is_file():
        return "", f"Видео не найдено: {src}"
    ff = _ffmpeg_bin()
    if not ff:
        return "", "ffmpeg не найден (brew install ffmpeg или pip install imageio-ffmpeg)"
    dest_dir = out_dir or src.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    dst = dest_dir / f"{src.stem}_audio.mp3"
    try:
        proc = subprocess.run(
            [ff, "-y", "-i", str(src), "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(dst)],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return "", "Таймаут ffmpeg (видео слишком длинное)"
    except OSError as e:
        return "", str(e)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return "", f"ffmpeg: {err[:400]}"
    if not dst.is_file() or dst.stat().st_size < 100:
        return "", "Аудиодорожка пустая или в видео нет звука"
    return str(dst), ""


def extract_audio_from_paths(
    paths: list[str], *, download_dir: Path | None = None
) -> tuple[list[str], str]:
    """Для каждого видео в paths — mp3 рядом. Возвращает (extra_mp3_paths, error)."""
    extras: list[str] = []
    errors: list[str] = []
    for raw in paths:
        if not is_video_path(raw):
            continue
        mp3, err = extract_audio_mp3(raw, out_dir=download_dir)
        if mp3:
            extras.append(mp3)
        elif err:
            errors.append(err)
    return extras, "; ".join(errors)

"""Вложения: маркеры в ответе агента и скачанные из Telegram."""

from __future__ import annotations

import re
from pathlib import Path

FILES_MARKER = "__FILES__:"
FILE_PREFIX = "__FILE__:"
PHOTO_PREFIX = "__PHOTO__:"
DOC_PREFIX = "__DOC__:"


def strip_file_markers(text: str) -> tuple[str, list[str]]:
    """Убирает __FILES__:path1,path2 из текста, возвращает пути."""
    paths: list[str] = []
    out_lines: list[str] = []
    for line in (text or "").splitlines():
        if line.strip().startswith(FILES_MARKER):
            rest = line.strip()[len(FILES_MARKER) :].strip()
            for p in rest.split(","):
                p = p.strip()
                if p and Path(p).expanduser().is_file():
                    paths.append(str(Path(p).expanduser()))
            continue
        out_lines.append(line)
    cleaned = "\n".join(out_lines).strip()
    return cleaned, paths


def ingest_prompt_attachments(raw: str, *, download_dir: Path) -> tuple[str, list[str], str]:
    """
    __FILE__/ __PHOTO__/ __DOC__ file_id → локальные файлы.
    Возвращает (prompt_for_agent, local_paths, error).
    """
    from remote_agent.voice import download_tg_file

    download_dir.mkdir(parents=True, exist_ok=True)
    lines_out: list[str] = []
    local_paths: list[str] = []
    errors: list[str] = []

    for line in raw.split("\n"):
        stripped = line.strip()
        for prefix, default_name in (
            (FILE_PREFIX, "attachment.bin"),
            (PHOTO_PREFIX, "photo.jpg"),
            (DOC_PREFIX, "document.bin"),
        ):
            if stripped.startswith(prefix):
                rest = stripped[len(prefix) :].strip()
                file_id = rest
                name = default_name
                if "|" in rest:
                    file_id, name = rest.split("|", 1)
                    file_id = file_id.strip()
                    name = name.strip() or default_name
                data, fname, err = download_tg_file(file_id)
                if err:
                    errors.append(err)
                    break
                dest = download_dir / (name or fname)
                dest.write_bytes(data)
                local_paths.append(str(dest))
                lines_out.append(f"[Вложение с телефона: {dest}]")
                break
        else:
            lines_out.append(line)

    prompt = "\n".join(lines_out).strip()
    err = "; ".join(errors) if errors else ""
    return prompt, local_paths, err

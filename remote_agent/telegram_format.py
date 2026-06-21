"""Markdown-подобный текст агента → HTML для Telegram."""

from __future__ import annotations

import html
import re


def agent_text_to_telegram_html(text: str, *, limit: int = 12000) -> str:
    """Ссылки, жирный, код — кликабельно в Telegram."""
    t = (text or "").strip()
    if not t:
        return ""
    if len(t) > limit:
        t = t[: limit - 20] + "\n\n… (обрезано)"

    links: list[tuple[str, str]] = []

    def _link(m: re.Match) -> str:
        links.append((m.group(1), m.group(2)))
        return f"\x00L{len(links) - 1}\x00"

    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, t)
    t = re.sub(r"\*\*(.+?)\*\*", lambda m: f"\x00B{m.group(1)}\x00", t, flags=re.S)
    t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", lambda m: f"\x00I{m.group(1)}\x00", t)
    t = re.sub(r"`([^`\n]+)`", lambda m: f"\x00C{m.group(1)}\x00", t)

    t = html.escape(t)

    t = re.sub(r"\x00B(.+?)\x00", r"<b>\1</b>", t, flags=re.S)
    t = re.sub(r"\x00I(.+?)\x00", r"<i>\1</i>", t, flags=re.S)
    t = re.sub(r"\x00C(.+?)\x00", r"<code>\1</code>", t, flags=re.S)

    for i, (label, url) in enumerate(links):
        safe_url = html.escape(url.strip(), quote=True)
        safe_label = html.escape(label)
        t = t.replace(f"\x00L{i}\x00", f'<a href="{safe_url}">{safe_label}</a>')

    def _bare_url(m: re.Match) -> str:
        url = m.group(1).rstrip(".,);]")
        return f'<a href="{html.escape(url, quote=True)}">{html.escape(url)}</a>'

    t = re.sub(r"(?<![\"'=])(https?://[^\s<>\"]+)", _bare_url, t)

    t = re.sub(r"^###?\s+(.+)$", r"<b>\1</b>", t, flags=re.M)
    t = re.sub(r"^##\s+(.+)$", r"<b>\1</b>", t, flags=re.M)
    return t

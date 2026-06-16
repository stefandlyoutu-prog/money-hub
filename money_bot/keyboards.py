"""Клавиатуры Money Hub бота."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from business_dashboard.config import public_dashboard_url, public_miniapp_url


def kb_main() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    mini = public_miniapp_url()
    site = public_dashboard_url()
    if mini.startswith("https://"):
        rows.append(
            [
                InlineKeyboardButton(
                    text="📱 Приложение",
                    web_app=WebAppInfo(url=mini),
                )
            ]
        )
    if site.startswith("https://"):
        rows.append([InlineKeyboardButton(text="🌐 Полный дашборд", url=site)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else InlineKeyboardMarkup(inline_keyboard=[])

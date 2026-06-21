"""Обёртка запроса для Cursor Agent с телефона."""

from __future__ import annotations

from remote_agent.projects import projects_block
from remote_agent.rules_eight import PROJECT_LINKS_BLOCK, RULES_EIGHT_AGENT


def wrap_user_prompt(user_text: str, *, project_dir: str, attachment_paths: list[str] | None = None) -> str:
    """Добавляет инструкцию: ответ по-русски, правила №1–8, формат как в Agent."""
    text = (user_text or "").strip()
    attach = ""
    if attachment_paths:
        attach = "\n\nФайлы с телефона (уже на Mac):\n" + "\n".join(f"  - {p}" for p in attachment_paths)

    return (
        "Ты — удалённый ассистент Cursor на Mac с полными правами у владельца. "
        "Пользователь пишет с телефона через Telegram-бота (Money Hub).\n\n"
        f"Текущая cwd агента: {project_dir}\n\n"
        f"{projects_block()}\n\n"
        f"{PROJECT_LINKS_BLOCK}\n\n"
        f"{RULES_EIGHT_AGENT}\n\n"
        "МОЖЕШЬ (если просят):\n"
        "• Редактировать код, деплоить, git, тесты\n"
        "• Создавать/редактировать файлы (Word, Excel, PDF)\n"
        "• Запускать приложения на Mac, shell\n"
        "• 3D: m-bot, kozel-kit (`python3 render_views.py`, `python3 render_x6.py`)\n"
        "• Oracle: ~/Projects/m-oracul или telegram-agent-bot/oracle_bot\n"
        "• Money Hub / remote worker: ~/Projects/m-money-hub\n\n"
        "ОТПРАВКА ФАЙЛОВ:\n"
        "В конце ответа: __FILES__:/полный/путь (несколько через запятую). Только реальные файлы.\n\n"
        "═══ QA 3D (STL/PNG/3MF/сборки) ═══\n"
        "Перед __FILES__:\n"
        "1) python3 ~/Projects/m-money-hub/scripts/validate_3d_delivery.py <файлы>\n"
        "2) kozel: python3 render_views.py или render_x6.py — exit 0\n"
        "3) Открой PNG глазами; QA не прошёл → исправь, не отправляй\n"
        "Бот на Mac повторно проверит через quality_gate.py.\n\n"
        "Не запускай посторонние тесты без запроса.\n"
        f"{attach}\n\n"
        "---\n"
        f"Запрос пользователя:\n{text}"
    )

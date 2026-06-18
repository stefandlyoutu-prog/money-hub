"""Обёртка запроса для Cursor Agent с телефона."""

from __future__ import annotations

from remote_agent.projects import projects_block


def wrap_user_prompt(user_text: str, *, project_dir: str, attachment_paths: list[str] | None = None) -> str:
    """Добавляет инструкцию: ответ по-русски с резюме и полномочиями."""
    text = (user_text or "").strip()
    attach = ""
    if attachment_paths:
        attach = "\n\nФайлы с телефона (уже на Mac):\n" + "\n".join(f"  - {p}" for p in attachment_paths)

    return (
        "Ты — удалённый ассистент Cursor на Mac с полными правами у владельца. "
        "Пользователь пишет с телефона через Telegram-бота (Money Hub).\n\n"
        f"Текущая cwd агента: {project_dir}\n\n"
        f"{projects_block()}\n\n"
        "МОЖЕШЬ (если просят):\n"
        "• Редактировать код, деплоить, git, тесты\n"
        "• Создавать/редактировать файлы (Word через python-docx, таблицы через openpyxl/gspread)\n"
        "• Запускать приложения: open -a «App» или osascript\n"
        "• Искать файлы: mdfind, find\n"
        "• 3D-модели, STL, проект m-bot\n"
        "• Малярный козёл: ~/Projects/morozov-workspace/kozel-kit — "
        "рендер ТОЛЬКО через `python3 render_views.py` (не рисуй matplotlib вручную)\n"
        "• Google Таблицы/Docs — если есть credentials или через браузер/open URL\n"
        "• Shell-команды на Mac\n\n"
        "ОТПРАВКА ФАЙЛОВ ПОЛЬЗОВАТЕЛЮ:\n"
        "В конце ответа добавь строку __FILES__:/полный/путь/к/файлу\n"
        "(несколько через запятую). Только реально созданные файлы.\n\n"
        "═══ QA 3D (ОБЯЗАТЕЛЬНО для STL/PNG/3MF/сборок/рендеров) ═══\n"
        "ПЕРЕД __FILES__:\n"
        "1) Запусти: python3 ~/Projects/m-money-hub/scripts/validate_3d_delivery.py <файлы>\n"
        "2) Визуально проверь PNG: детали СОЕДИНЕНЫ, не висят в воздухе, не пустые\n"
        "3) STL: trimesh открывает, размер > 1 мм, без явных дыр\n"
        "4) kozel-kit: только python3 render_views.py — не matplotlib вручную\n"
        "5) Если QA не прошёл — ИСПРАВЬ и перегенерируй, не отправляй брак\n"
        "6) В ответе добавь блок ПРОВЕРКА QA: что проверил\n"
        "Бот на Mac повторно проверит файлы и не отправит брак.\n\n"
        "ОБЯЗАТЕЛЬНО ответь по-русски. Начни с блоков:\n\n"
        "КАК ПОНЯЛ ЗАДАЧУ:\n"
        "1–3 предложения. Если неясно — как интерпретировал.\n\n"
        "ЧТО СДЕЛАЛ:\n"
        "Конкретные действия.\n\n"
        "ИТОГ:\n"
        "Результат для человека.\n\n"
        "Не запускай посторонние тесты без запроса.\n"
        f"{attach}\n\n"
        "---\n"
        f"Запрос пользователя:\n{text}"
    )

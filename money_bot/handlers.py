"""Telegram-команды Money Hub: /money и Mini App."""

from __future__ import annotations

import json
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from business_dashboard.config import MONEY_ADMIN_IDS, public_dashboard_url, public_miniapp_url
from money_bot.keyboards import kb_main

logger = logging.getLogger(__name__)
router = Router()


def _allowed(user_id: int | None) -> bool:
    if not MONEY_ADMIN_IDS:
        return True
    return user_id is not None and user_id in MONEY_ADMIN_IDS


def _ensure_db() -> None:
    from business_dashboard.storage import init_db, rollover_day_if_needed

    init_db()
    rollover_day_if_needed()


async def _summary_text() -> str:
    from business_dashboard.daily import get_money_metrics, get_today_plan
    from business_dashboard.storage import list_blockers

    m = get_money_metrics()
    plan = get_today_plan()
    blockers = list_blockers(open_only=True)[:5]
    lines = [
        "💰 <b>Центр доходов</b>",
        f"План: {m['target_today']:.0f} ₽ · Факт: {m['actual_today']:.0f} ₽ · Разрыв: {m['gap']:.0f} ₽",
        f"Потенциал онлайн: {m['potential_if_launch_online']:.0f} ₽",
        "",
    ]
    if plan:
        lines.append("<b>План на сегодня:</b>")
        for p in plan:
            lines.append(f"  • {p.get('title', p['slug'])} — {p.get('expected_rub', 0):.0f} ₽")
    else:
        lines.append("План пуст — /money plan slug-идеи")
    if blockers:
        lines.append("\n<b>Нужно от вас:</b>")
        for b in blockers:
            lines.append(f"  ⚠️ {b['description'][:100]}")
    site = public_dashboard_url()
    if site.startswith("https://"):
        lines.append(f"\n🌐 Дашборд: {site}")
    lines.append("\n/money online · /money plan slug · /money +500 slug · /money report")
    lines.append("/money assets · /money scout · /help")
    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа.")
        return
    _ensure_db()
    mini = public_miniapp_url()
    await message.answer(
        "◈ <b>Money Hub</b>\n\n"
        "План, факт, идеи и отчёты — с телефона или Mac.\n\n"
        "• /money — сводка и быстрые команды\n"
        "• Кнопка «Приложение» — упрощённый вид\n"
        "• «Полный дашборд» — все таблицы и графики\n\n"
        + (f"Mini App: {mini}\n" if mini.startswith("https://") else ""),
        parse_mode="HTML",
        reply_markup=kb_main(),
    )
    args = (command.args or "").strip()
    if args == "report":
        await _cmd_report(message)
    elif args == "online":
        await _cmd_online(message)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа.")
        return
    await message.answer(
        "<b>Money Hub — команды</b>\n\n"
        "/money — сводка\n"
        "/money +500 slug — добавить доход\n"
        "/money plan slug — в план на сегодня\n"
        "/money report — закрыть день\n"
        "/money online — что запустить онлайн\n"
        "/money assets · /money scout\n\n"
        "Полный UI — кнопка «Полный дашборд» или «Приложение».",
        parse_mode="HTML",
        reply_markup=kb_main(),
    )


@router.message(Command("money"))
async def cmd_money(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа к /money")
        return
    _ensure_db()
    args = (message.text or "").split(maxsplit=1)
    sub = args[1].strip().lower() if len(args) > 1 else ""

    if sub.startswith("+"):
        parts = sub[1:].split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Формат: /money +500 slug-идеи")
            return
        try:
            amount = float(parts[0].replace(",", "."))
        except ValueError:
            await message.answer("Сумма должна быть числом")
            return
        if amount <= 0:
            await message.answer("Сумма должна быть больше 0")
            return
        slug = parts[1].strip()
        from business_dashboard.storage import add_revenue

        row = add_revenue(slug, amount, note="telegram", source="telegram")
        if not row:
            await message.answer(f"Идея «{slug}» не найдена")
            return
        await message.answer(f"✅ +{amount:.0f} ₽ → {row['title']}")
        return

    if sub.startswith("plan "):
        slug = sub[5:].strip()
        from business_dashboard.daily import add_to_today_plan

        if add_to_today_plan(slug):
            await message.answer(f"📋 В план на сегодня: {slug}")
        else:
            await message.answer("Уже в плане или slug не найден")
        return

    if sub == "report":
        await _cmd_report(message)
        return

    if sub == "online":
        await _cmd_online(message)
        return

    if sub == "assets":
        await _cmd_assets(message)
        return

    if sub == "scout":
        await _cmd_scout(message)
        return

    await message.answer(await _summary_text(), parse_mode="HTML", reply_markup=kb_main())


async def _cmd_report(message: Message) -> None:
    from business_dashboard.daily import close_day_report

    report = close_day_report(note="из Telegram")
    text = (
        f"📊 <b>Отчёт {report['report_date']}</b>\n\n"
        f"План: {report['expected_total']:.0f} ₽\n"
        f"Факт: {report['actual_total']:.0f} ₽\n"
        f"Разрыв: {report['gap_rub']:.0f} ₽\n\n"
        f"<b>Почему:</b>\n{report['gap_reason']}\n\n"
        f"<b>Изменить:</b>\n{report['suggestions']}"
    )
    await message.answer(text[:4000], parse_mode="HTML")


async def _cmd_online(message: Message) -> None:
    from business_dashboard.storage import list_ideas

    ideas = [i for i in list_ideas() if i.get("channel") == "online" and i["status"] == "needs_action"]
    lines = ["🌐 <b>Онлайн — запустить первыми</b>\n"]
    for i in sorted(ideas, key=lambda x: -(x.get("expected_daily_rub") or 0))[:8]:
        lines.append(f"• {i['title'][:50]} — ~{i.get('expected_daily_rub', 0):.0f} ₽/день")
    await message.answer("\n".join(lines), parse_mode="HTML")


async def _cmd_assets(message: Message) -> None:
    from business_dashboard.storage import list_user_assets

    assets = list_user_assets()
    lines = ["🔑 <b>Сделал один раз:</b>"]
    for a in assets:
        mark = "✅" if a.get("done") else "⬜"
        lines.append(f"{mark} {a['label']}")
    lines.append("\nОтметь в дашборде — подтянется во все проекты.")
    await message.answer("\n".join(lines), parse_mode="HTML")


async def _cmd_scout(message: Message) -> None:
    from business_dashboard.idea_scout import list_opportunities

    opps = list_opportunities()[:6]
    lines = ["🔍 <b>Тренды → решения:</b>"]
    for o in opps:
        if o["pipeline_stage"] in ("launched", "rejected"):
            continue
        lines.append(f"• {o['query_text'][:40]} — {o.get('expected_daily_rub', 0):.0f} ₽/д")
    await message.answer("\n".join(lines) or "Пусто", parse_mode="HTML")


@router.message(F.web_app_data)
async def on_webapp_data(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if not _allowed(uid):
        await message.answer("Нет доступа.")
        return
    try:
        data = json.loads(message.web_app_data.data)
    except (TypeError, json.JSONDecodeError):
        return
    action = data.get("action")
    _ensure_db()

    if action == "report":
        await _cmd_report(message)
        return

    if action == "summary":
        await message.answer(await _summary_text(), parse_mode="HTML", reply_markup=kb_main())
        return

    if action == "revenue":
        slug = (data.get("slug") or "").strip()
        try:
            amount = float(data.get("amount", 0))
        except (TypeError, ValueError):
            await message.answer("Неверная сумма")
            return
        if amount <= 0 or not slug:
            await message.answer("Нужны slug и сумма")
            return
        from business_dashboard.storage import add_revenue

        row = add_revenue(slug, amount, note="miniapp", source="telegram")
        if not row:
            await message.answer(f"Идея «{slug}» не найдена")
            return
        await message.answer(f"✅ +{amount:.0f} ₽ → {row['title']}")
        return

    if action == "open_dashboard":
        site = public_dashboard_url()
        await message.answer(f"🌐 Полный дашборд:\n{site}")
        return

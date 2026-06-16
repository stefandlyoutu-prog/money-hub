# Money Hub

План, факт, идеи, отчёты — **сайт (PWA) + Telegram-бот + Mini App**.

## Локально

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-money-hub.txt

# Терминал 1 — дашборд
.venv/bin/python scripts/run_dashboard.py --no-open

# Терминал 2 — бот (polling)
.venv/bin/python scripts/run_money_bot.py
```

Тест: `.venv/bin/python scripts/test_money_hub.py`

## Облако (Render — бесплатно, Mac не нужен)

Как у M-oracul: [Render](https://render.com) free tier, git-push deploy.

1. Создай репо `money-hub` на GitHub, push из этой папки
2. Render → **New Blueprint** → `render.yaml`
3. Env vars: `MONEY_BOT_TOKEN`, `MONEY_ADMIN_IDS`, `MONEY_DASHBOARD_TOKEN`, `MONEY_BOT_USERNAME`
4. После деплоя URL вида `https://money-hub-xxxx.onrender.com`

**Ограничения free tier:** сервис «засыпает» через ~15 мин без трафика, первый запрос 30–60 сек. SQLite на диске Render **не переживает** redeploy без paid disk — для продакшена позже Turso/Postgres.

### Альтернативы хостинга

| Платформа | Free | Для Money Hub |
|-----------|------|---------------|
| **Render** | Да, без карты | ✅ уже используем для оракула |
| Railway | ~$1/мес кредит | быстрее cold start |
| Fly.io | нет free для новых | не рекомендую |
| Vercel | только static | не подходит (нужен Python+бот) |

## Структура

| Часть | URL |
|-------|-----|
| PWA дашборд | `/` |
| Mini App | `/mini` |
| Health | `/health` |
| Webhook бота | `/webhook` |

## Бот

- `/start`, `/money`, `/help`
- Кнопки: Mini App + ссылка на полный дашборд

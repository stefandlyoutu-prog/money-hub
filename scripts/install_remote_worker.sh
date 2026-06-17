#!/usr/bin/env bash
# Установка Cursor Agent CLI + launchd-воркер для управления с телефона.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.morozov.remote-worker.plist"
LOG_DIR="$HOME/Library/Logs/remote-worker"

echo "=== 1/4 Cursor Agent CLI ==="
if ! command -v agent >/dev/null 2>&1; then
  curl https://cursor.com/install -fsS | bash
  echo "Добавь в ~/.zshrc: export PATH=\"\$HOME/.local/bin:\$PATH\""
else
  echo "agent уже установлен: $(command -v agent)"
fi

echo ""
echo "=== 2/4 Секрет воркера ==="
ENV_FILE="$ROOT/.env"
if ! grep -q '^REMOTE_WORKER_SECRET=' "$ENV_FILE" 2>/dev/null; then
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(24))")
  echo "REMOTE_WORKER_SECRET=$SECRET" >> "$ENV_FILE"
  echo "Создан REMOTE_WORKER_SECRET в $ENV_FILE"
  echo "⚠️  Скопируй то же значение в Render → money-hub → Environment"
else
  echo "REMOTE_WORKER_SECRET уже есть в .env"
fi

echo ""
echo "=== 3/4 launchd ==="
mkdir -p "$LOG_DIR"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.morozov.remote-worker</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd "$ROOT" &amp;&amp; set -a &amp;&amp; source .env &amp;&amp; set +a &amp;&amp; exec caffeinate -dims python3 scripts/remote_worker.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/stderr.log</string>
</dict>
</plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Воркер запущен: $PLIST"
echo "Логи: $LOG_DIR/"

echo ""
echo "=== 4/4 CURSOR_API_KEY ==="
if ! grep -q '^CURSOR_API_KEY=' "$ENV_FILE" 2>/dev/null; then
  echo "Добавь в .env и Render:"
  echo "  CURSOR_API_KEY=ключ с https://cursor.com/settings"
fi

echo ""
echo "Готово. В Telegram @MS_Moneybot:"
echo "  /agent on  — пиши задачи текстом"
echo "  /cmd …     — одна задача"
echo "  /agent status — Mac онлайн?"

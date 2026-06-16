#!/usr/bin/env bash
# Деплой Money Hub на Render (нужен RENDER_API_KEY или ручной Blueprint).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
RENDER="${RENDER:-$HOME/.local/bin/render}"

REPO_URL="${GITHUB_REPO_URL:-https://github.com/stefandlyoutu-prog/money-hub}"
BRANCH="${GITHUB_BRANCH:-main}"

echo "=== Git push ==="
git push -u origin "$BRANCH"

if [ -z "${RENDER_API_KEY:-}" ]; then
  echo ""
  echo "Код на GitHub: ${REPO_URL}"
  echo ""
  echo "Render (вручную, 2 минуты):"
  echo "  1. https://dashboard.render.com/blueprints → New Blueprint"
  echo "  2. Connect → stefandlyoutu-prog / money-hub"
  echo "  3. Apply → задай секреты:"
  echo "     MONEY_BOT_TOKEN, MONEY_BOT_USERNAME=MS_Moneybot"
  echo "     MONEY_ADMIN_IDS=5845195049, MONEY_DASHBOARD_TOKEN"
  exit 0
fi

export RENDER_API_KEY
echo "=== Render Blueprint ==="
curl -sf -X POST "https://api.render.com/v1/blueprints" \
  -H "Authorization: Bearer ${RENDER_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"money-hub\",\"repo\":\"${REPO_URL}\",\"branch\":\"${BRANCH}\"}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Blueprint:', d.get('id','created'))" 2>/dev/null \
  || echo "Открой Blueprint вручную: ${REPO_URL}"

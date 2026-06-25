#!/usr/bin/env bash
# One-command local run: venv + deps + server. Zero external services (SQLite).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/backend"

if [ ! -d .venv ]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
fi
./.venv/bin/python -m pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env

echo ""
echo "  AI Engineer Mastery is starting."
echo "  Open  http://localhost:8000   (dev login: visakh@local / learn)"
echo "  Set ANTHROPIC_API_KEY in backend/.env to enable the live AI tutor."
echo ""
exec ./.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

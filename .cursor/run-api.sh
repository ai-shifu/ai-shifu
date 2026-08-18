#!/usr/bin/env bash
# Backend API dev server (gunicorn + gevent, hot reload).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${AI_SHIFU_VENV:-$HOME/.venvs/ai-shifu}"

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
cd "$REPO_ROOT/src/api"
export FLASK_APP=app.py
exec gunicorn -k gevent -w 1 -b 0.0.0.0:"${AI_SHIFU_API_PORT:-5800}" "app:app" \
  --timeout 300 --log-level info --reload --access-logfile -

#!/usr/bin/env bash
# Celery beat: dispatches scheduled tasks (billing renewals, expirations, etc.).
# Mirrors the beat service in the Docker dev stack.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${AI_SHIFU_VENV:-$HOME/.venvs/ai-shifu}"

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
cd "$REPO_ROOT/src/api"
export FLASK_APP=app.py
exec python -m celery -A celery_app:celery_app beat --loglevel info

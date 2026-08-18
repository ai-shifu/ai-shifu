#!/usr/bin/env bash
# Celery worker: processes async tasks (billing, TTS, etc.) enqueued on the
# local Redis broker. Mirrors the worker in the Docker dev stack.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${AI_SHIFU_VENV:-$HOME/.venvs/ai-shifu}"

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
cd "$REPO_ROOT/src/api"
export FLASK_APP=app.py
exec python -m celery -A celery_app:celery_app worker --loglevel info

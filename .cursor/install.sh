#!/usr/bin/env bash
# Idempotent dependency setup for the AI-Shifu Cloud Agent environment.
# Installs system packages (MySQL, Redis, ffmpeg, build tools), the backend
# Python virtualenv, and the frontend node_modules. Runtime services and DB
# migrations are handled by start.sh, not here.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "[install] Ensuring system packages (mysql-server, redis-server, ffmpeg, build tools)..."
if ! command -v mysqld >/dev/null 2>&1 \
  || ! command -v redis-server >/dev/null 2>&1 \
  || ! command -v ffmpeg >/dev/null 2>&1 \
  || ! dpkg -s build-essential >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    mysql-server redis-server ffmpeg \
    python3-venv build-essential pkg-config default-libmysqlclient-dev
else
  echo "[install] System packages already present; skipping apt-get."
fi

echo "[install] Setting up backend Python virtualenv (src/api/.venv)..."
pushd src/api >/dev/null
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade "pip<25" setuptools wheel
pip install -r requirements.txt
deactivate
popd >/dev/null

echo "[install] Installing frontend dependencies (src/cook-web/node_modules)..."
pushd src/cook-web >/dev/null
npm ci
popd >/dev/null

echo "[install] Done."

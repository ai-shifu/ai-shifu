#!/usr/bin/env bash
# Per-boot reconciliation: bring up MySQL and Redis and wait until ready.
# Idempotent - safe to run when the services are already running.
set -euo pipefail

# MySQL
if ! sudo mysqladmin ping >/dev/null 2>&1; then
  echo "[start] starting mysql"
  sudo service mysql start || true
fi
for _ in $(seq 1 60); do
  sudo mysqladmin ping >/dev/null 2>&1 && break
  sleep 1
done
sudo mysqladmin ping >/dev/null 2>&1 || { echo "[start] ERROR: mysql did not become ready" >&2; exit 1; }

# Redis
if ! redis-cli ping >/dev/null 2>&1; then
  echo "[start] starting redis"
  sudo service redis-server start || true
fi
for _ in $(seq 1 30); do
  redis-cli ping >/dev/null 2>&1 && break
  sleep 1
done
redis-cli ping >/dev/null 2>&1 || { echo "[start] ERROR: redis did not become ready" >&2; exit 1; }

echo "[start] mysql + redis are ready"

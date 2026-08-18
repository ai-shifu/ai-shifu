#!/usr/bin/env bash
# Per-boot reconciliation: bring up Redis and MySQL and wait until ready.
# Idempotent - safe to run when the services are already running.
#
# Note on the MySQL self-heal below: when this environment is booted from a
# prebuilt snapshot, the restored InnoDB data files can live on inodes whose
# O_DIRECT access fails on the overlay filesystem (mysqld aborts in InnoDB init
# with "close returned OS error 122 / EINVAL"). Rewriting the datadir to fresh
# inodes with a plain copy resolves it without touching the data itself.
set -uo pipefail

MYSQL_DATADIR="${AI_SHIFU_MYSQL_DATADIR:-/var/lib/mysql}"

wait_redis() {
  for _ in $(seq 1 30); do
    redis-cli ping >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

wait_mysql() {
  local tries="${1:-60}"
  for _ in $(seq 1 "$tries"); do
    sudo mysqladmin ping >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

# --- Redis (independent of MySQL) ---
if ! redis-cli ping >/dev/null 2>&1; then
  echo "[start] starting redis"
  sudo service redis-server start || true
fi
if wait_redis; then
  echo "[start] redis is ready"
else
  echo "[start] ERROR: redis did not become ready" >&2
fi

# --- MySQL ---
if ! sudo mysqladmin ping >/dev/null 2>&1; then
  echo "[start] starting mysql"
  sudo service mysql start || true
fi

if ! wait_mysql 25; then
  echo "[start] mysql did not start; reallocating datadir inodes (overlay O_DIRECT workaround)"
  sudo service mysql stop >/dev/null 2>&1 || true
  if [ -d "$MYSQL_DATADIR" ]; then
    sudo rm -rf "${MYSQL_DATADIR}.reinit"
    sudo cp -a "$MYSQL_DATADIR" "${MYSQL_DATADIR}.reinit"
    sudo rm -rf "$MYSQL_DATADIR"
    sudo mv "${MYSQL_DATADIR}.reinit" "$MYSQL_DATADIR"
  fi
  sudo service mysql start || true
  wait_mysql || true
fi

if sudo mysqladmin ping >/dev/null 2>&1; then
  echo "[start] mysql is ready"
else
  echo "[start] ERROR: mysql did not become ready" >&2
  exit 1
fi

echo "[start] redis + mysql are ready"

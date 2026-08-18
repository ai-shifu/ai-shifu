#!/usr/bin/env bash
# Per-boot reconciliation: bring up Redis and MySQL and wait until ready.
# Idempotent - safe to run when the services are already running.
#
# Note on the MySQL self-heal below: when this environment is booted from a
# prebuilt snapshot, the restored InnoDB data files can live on inodes whose
# O_DIRECT access fails on the overlay filesystem (mysqld aborts in InnoDB init
# with "Operating system error number 22" / "close returned OS error 122").
# Rewriting the datadir to fresh inodes with a plain copy resolves it without
# touching the data itself. The rewrite is transactional: the original datadir
# is preserved until a verified copy is swapped in, so a failed copy can never
# destroy the only datadir.
set -uo pipefail

MYSQL_DATADIR="${AI_SHIFU_MYSQL_DATADIR:-/var/lib/mysql}"
MYSQL_ERROR_LOG="${AI_SHIFU_MYSQL_ERROR_LOG:-/var/log/mysql/error.log}"

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

# True only when mysqld's error log shows the documented overlay/O_DIRECT
# failure that the datadir-reallocation workaround actually fixes.
mysql_has_odirect_error() {
  sudo grep -qiE "OS error 122|Operating system error number 22" "$MYSQL_ERROR_LOG" 2>/dev/null
}

# Rewrite the datadir to fresh inodes without ever leaving the data unprotected.
reallocate_mysql_datadir() {
  local backup="${MYSQL_DATADIR}.bak.$$"
  local staged="${MYSQL_DATADIR}.reinit.$$"
  sudo rm -rf "$staged"
  if ! sudo cp -a "$MYSQL_DATADIR" "$staged"; then
    echo "[start] ERROR: datadir copy failed; original left intact" >&2
    sudo rm -rf "$staged"
    return 1
  fi
  # Swap: keep the original as a backup until the fresh copy is in place.
  if ! sudo mv "$MYSQL_DATADIR" "$backup"; then
    echo "[start] ERROR: could not move original datadir aside" >&2
    sudo rm -rf "$staged"
    return 1
  fi
  if ! sudo mv "$staged" "$MYSQL_DATADIR"; then
    echo "[start] ERROR: could not install fresh datadir; restoring original" >&2
    sudo mv "$backup" "$MYSQL_DATADIR"
    return 1
  fi
  sudo rm -rf "$backup"
  return 0
}

# --- Redis (independent of MySQL) ---
if ! redis-cli ping >/dev/null 2>&1; then
  echo "[start] starting redis"
  sudo service redis-server start || true
fi
if ! wait_redis; then
  echo "[start] ERROR: redis did not become ready" >&2
  exit 1
fi
echo "[start] redis is ready"

# --- MySQL ---
if ! sudo mysqladmin ping >/dev/null 2>&1; then
  echo "[start] starting mysql"
  sudo service mysql start || true
fi

if ! wait_mysql 25; then
  if mysql_has_odirect_error; then
    echo "[start] mysql failed with the known overlay O_DIRECT error; reallocating datadir inodes"
    sudo service mysql stop >/dev/null 2>&1 || true
    if [ -d "$MYSQL_DATADIR" ] && reallocate_mysql_datadir; then
      sudo service mysql start || true
      wait_mysql 60 || true
    fi
  else
    echo "[start] ERROR: mysql did not start and the known overlay O_DIRECT error was not found; not touching the datadir" >&2
  fi
fi

if sudo mysqladmin ping >/dev/null 2>&1; then
  echo "[start] mysql is ready"
else
  echo "[start] ERROR: mysql did not become ready" >&2
  exit 1
fi

echo "[start] redis + mysql are ready"

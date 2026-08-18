#!/usr/bin/env bash
# Per-boot reconciliation: bring up Redis and MySQL and wait until ready.
# Idempotent - safe to run when the services are already running.
#
# Note on the MySQL self-heal below: when this environment is booted from a
# prebuilt snapshot, the restored InnoDB data files can live on inodes whose
# O_DIRECT access fails on the overlay filesystem (mysqld aborts in InnoDB init
# with "Operating system error number 22" / "close returned OS error 122").
# Rewriting the datadir to fresh inodes with a plain copy resolves it without
# touching the data itself. The rewrite is transactional and guarded so it can
# never destroy the only datadir:
#   * it runs only when THIS start attempt logged the O_DIRECT error (the error
#     log is inspected from the offset captured just before starting mysqld, so
#     a historical entry cannot trigger a false heal);
#   * it runs only after mysqld is confirmed stopped (never copies live files);
#   * it stages a verified copy and keeps the original as a backup until the
#     fresh copy is swapped in, rolling back on any failure.
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

# Current size of the error log, so later checks can ignore historical entries.
mysql_error_log_offset() {
  sudo stat -c %s "$MYSQL_ERROR_LOG" 2>/dev/null || echo 0
}

# True only when the documented overlay/O_DIRECT failure was logged *after* the
# given byte offset, i.e. by the start attempt we just made.
mysql_has_odirect_error_since() {
  local offset="${1:-0}"
  sudo test -f "$MYSQL_ERROR_LOG" 2>/dev/null || return 1
  sudo tail -c "+$((offset + 1))" "$MYSQL_ERROR_LOG" 2>/dev/null \
    | grep -qiE "OS error 122|Operating system error number 22"
}

# Confirm no mysqld process is running (do not copy a datadir mysqld may write).
mysqld_stopped() {
  ! pgrep -x mysqld >/dev/null 2>&1 && ! sudo mysqladmin ping >/dev/null 2>&1
}

# Rewrite the datadir to fresh inodes without ever leaving the data unprotected.
reallocate_mysql_datadir() {
  local backup="${MYSQL_DATADIR}.bak.$$"
  local staged="${MYSQL_DATADIR}.reinit.$$"

  # Clear any leftovers from an interrupted prior recovery (e.g. a reused PID)
  # so cp/mv cannot nest the datadir inside a pre-existing directory.
  sudo rm -rf "$staged" "$backup"
  if [ -e "$staged" ] || [ -e "$backup" ]; then
    echo "[start] ERROR: could not clear stale recovery paths" >&2
    return 1
  fi

  if ! sudo cp -a "$MYSQL_DATADIR" "$staged"; then
    echo "[start] ERROR: datadir copy failed; original left intact" >&2
    sudo rm -rf "$staged"
    return 1
  fi

  # Swap with no-target-directory moves so an unexpected existing destination
  # fails loudly instead of nesting. Keep the original as a backup until the
  # fresh copy is in place.
  if ! sudo mv -T "$MYSQL_DATADIR" "$backup"; then
    echo "[start] ERROR: could not move original datadir aside" >&2
    sudo rm -rf "$staged"
    return 1
  fi
  if ! sudo mv -T "$staged" "$MYSQL_DATADIR"; then
    echo "[start] ERROR: could not install fresh datadir; restoring original" >&2
    sudo mv -T "$backup" "$MYSQL_DATADIR"
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
  log_offset="$(mysql_error_log_offset)"
  echo "[start] starting mysql"
  sudo service mysql start || true

  if ! wait_mysql 25; then
    if mysql_has_odirect_error_since "$log_offset"; then
      echo "[start] mysql failed with the known overlay O_DIRECT error; reallocating datadir inodes"
      if ! sudo service mysql stop; then
        echo "[start] WARNING: 'service mysql stop' reported failure; waiting for shutdown" >&2
      fi
      # Never touch the datadir while mysqld might still be writing to it.
      for _ in $(seq 1 20); do
        mysqld_stopped && break
        sleep 1
      done
      if ! mysqld_stopped; then
        echo "[start] ERROR: mysqld still running; refusing to reallocate datadir" >&2
        exit 1
      fi
      if [ -d "$MYSQL_DATADIR" ] && reallocate_mysql_datadir; then
        sudo service mysql start || true
        wait_mysql 60 || true
      fi
    else
      echo "[start] ERROR: mysql did not start and the current start attempt did not log the known overlay O_DIRECT error; not touching the datadir" >&2
    fi
  fi
fi

if sudo mysqladmin ping >/dev/null 2>&1; then
  echo "[start] mysql is ready"
else
  echo "[start] ERROR: mysql did not become ready" >&2
  exit 1
fi

echo "[start] redis + mysql are ready"

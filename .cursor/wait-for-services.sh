#!/usr/bin/env bash
# Block until the local MySQL (3306) and Redis (6379) accept TCP connections.
#
# The `start` hook is responsible for starting and, if needed, repairing these
# services; it runs as a non-blocking background hook, so a terminal launched by
# the environment can otherwise start before the backend is ready (the O_DIRECT
# datadir heal in start.sh can be slow). Terminals source this to WAIT only -
# they never start or heal services themselves, so there is no race with the
# datadir reallocation.
set -uo pipefail

wait_tcp() {
  local host="$1" port="$2" name="$3" tries="${4:-300}"
  for _ in $(seq 1 "$tries"); do
    if (exec 3<>"/dev/tcp/${host}/${port}") 2>/dev/null; then
      exec 3>&- 3<&-
      echo "[wait] ${name} (${host}:${port}) is accepting connections"
      return 0
    fi
    sleep 1
  done
  echo "[wait] ERROR: ${name} (${host}:${port}) not reachable after ${tries}s" >&2
  return 1
}

wait_tcp 127.0.0.1 3306 mysql || exit 1
wait_tcp 127.0.0.1 6379 redis || exit 1

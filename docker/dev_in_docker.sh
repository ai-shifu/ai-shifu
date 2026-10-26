#!/bin/bash
set -euo pipefail

script_path=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

if [ ! -e "$script_path/.env" ]; then
  printf '%s\n' "Missing docker/.env. For a NEW installation, run python3 ../scripts/prepare_env.py from docker/. For an existing installation, restore the original configuration from backup." >&2
  exit 1
fi

docker build -f "$script_path/../src/api/Dockerfile" -t ai-shifu-api-dev "$script_path/.."

if app_build_sha=$(git -C "$script_path/.." rev-parse HEAD 2>/dev/null); then
  printf '%s\n' "$app_build_sha" > "$script_path/../src/web/.app-build-sha"
else
  # Source archives have no revision; never reuse a marker from another checkout.
  rm -f "$script_path/../src/web/.app-build-sha"
fi

docker build "$script_path/../src/web" -t ai-shifu-cook-web-dev -f "$script_path/../src/web/Dockerfile_DEV"
docker compose -f "$script_path/docker-compose.dev.yml" up

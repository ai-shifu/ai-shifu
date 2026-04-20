#!/usr/bin/env bash
set -euo pipefail

container="ai-shifu-api-dev"
if [[ "${1:-}" != "" && "${1}" != -* ]]; then
  container="${1}"
  shift
fi

docker exec \
  -e PYTHONUNBUFFERED=1 \
  -w /app \
  "${container}" \
  python scripts/test_litellm_responses_providers.py "$@"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}/.."

IMAGE_TAG="ai-shifu-cook-web:dev"

echo "Building Cook Web image from repo root with i18n included..."
docker build \
  -f "${REPO_ROOT}/src/cook-web/Dockerfile" \
  -t "${IMAGE_TAG}" \
  "${REPO_ROOT}"

echo "\n✅ Build complete: ${IMAGE_TAG}"

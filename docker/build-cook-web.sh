#!/usr/bin/env bash
set -euo pipefail

# Build Cook Web Docker image from the repo root context so shared i18n is available.
# Usage: ./build-cook-web.sh [tag]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TAG="${1:-ai-shifu-cook-web:dev}"

echo "Building Cook Web image as $TAG from $ROOT_DIR"
docker build \
  -f "$ROOT_DIR/src/cook-web/Dockerfile" \
  "$ROOT_DIR" \
  -t "$TAG"

echo "Done: $TAG"

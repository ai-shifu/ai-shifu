#!/usr/bin/env bash
# Cook Web (Next.js) dev server. In dev, Next.js proxies /api/* to the backend
# (NEXT_PUBLIC_API_BASE_URL, default http://127.0.0.1:5800), so this is the
# single browser entry point.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$REPO_ROOT/src/cook-web"
export NODE_ENV=development
export NEXT_TELEMETRY_DISABLED=1
export NODE_OPTIONS="--max-old-space-size=2048"
export NEXT_PUBLIC_LOGIN_METHODS_ENABLED="${NEXT_PUBLIC_LOGIN_METHODS_ENABLED:-phone}"
export NEXT_PUBLIC_DEFAULT_LOGIN_METHOD="${NEXT_PUBLIC_DEFAULT_LOGIN_METHOD:-phone}"
exec ./node_modules/.bin/next dev --turbopack -H 0.0.0.0 -p "${AI_SHIFU_WEB_PORT:-3000}"

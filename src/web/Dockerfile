FROM node:22.16.0-alpine@sha256:41e4389f3d988d2ed55392df4db1420ad048ae53324a8e2b7c6d19508288107e AS builder

WORKDIR /app

# Support building from repo root or from src/web with build args
ARG APP_DIR=src/web
ARG I18N_DIR=src/i18n

# Copy dependency manifests
COPY ${APP_DIR}/package.json ${APP_DIR}/package-lock.json ./

RUN apk add --no-cache libc6-compat python3 make g++

# Log the container runtime before dependency installation. Keep failure stages distinct.
RUN node --version && npm --version && node -p "process.platform + '/' + process.arch"

RUN npm config set fetch-retries 5 && \
    npm config set fetch-retry-mintimeout 20000 && \
    npm config set fetch-retry-maxtimeout 120000 && \
    npm config set fetch-timeout 300000

# Keep the source lockfile as the baseline for both installation and pruning.
RUN cp package-lock.json /tmp/package-lock.source.json && \
    npm ci && \
    cmp package-lock.json /tmp/package-lock.source.json

# Copy project source and shared i18n
COPY ${APP_DIR}/ ./
COPY ${I18N_DIR}/ ./i18n

RUN npm run build

# Reuse the target architecture's installed native modules instead of downloading twice.
FROM builder AS production-dependencies

# Reuse npm ci metadata for peer resolution; pruning must never fetch or rerun scripts.
RUN --network=none npm prune --omit=dev --offline --ignore-scripts --no-audit --no-fund --save=false && \
    cmp package-lock.json /tmp/package-lock.source.json && \
    npm cache clean --force && \
    rm -rf /root/.cache /root/.npm /tmp/*

RUN I18N_ROOT=/app/i18n node scripts/check-production-dependencies.mjs

FROM node:22.16.0-alpine@sha256:41e4389f3d988d2ed55392df4db1420ad048ae53324a8e2b7c6d19508288107e AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV I18N_ROOT=/app/i18n

RUN apk add --no-cache libc6-compat

COPY --from=builder /app/package.json ./
COPY --from=builder /app/package-lock.json ./
COPY --from=production-dependencies /app/node_modules ./node_modules
COPY --from=builder /app/scripts/check-production-dependencies.mjs ./scripts/check-production-dependencies.mjs
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/i18n ./i18n

EXPOSE ${PORT:-3000}

USER node

CMD ["npm", "start"]

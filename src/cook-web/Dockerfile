FROM node:22.16.0-alpine AS builder

WORKDIR /app

# Support building from repo root or from src/cook-web with build args
ARG APP_DIR=src/cook-web
ARG I18N_DIR=src/i18n

# Copy dependency manifests
COPY ${APP_DIR}/package.json ${APP_DIR}/package-lock.json ./

RUN apk add --no-cache libc6-compat python3 make g++ && \
    npm config set fetch-retries 5 && \
    npm config set fetch-retry-mintimeout 20000 && \
    npm config set fetch-retry-maxtimeout 120000 && \
    npm config set fetch-timeout 300000 && \
    npm ci && \
    # Ensure sharp is built/installed for the current musl/glibc + arch
    (npm rebuild sharp || npm install --include=optional sharp) && \
    npm cache clean --force

# Copy project source and shared i18n
COPY ${APP_DIR}/ ./
COPY ${I18N_DIR}/ ./i18n

RUN npm run build

FROM node:22.16.0-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV I18N_ROOT=/app/i18n

RUN apk add --no-cache libc6-compat

COPY --from=builder /app/package.json ./
COPY --from=builder /app/package-lock.json ./
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/i18n ./i18n

RUN npm ci --only=production && \
    npm cache clean --force && \
    rm -rf /root/.cache /root/.npm /tmp/*

EXPOSE ${PORT:-3000}

USER node

CMD ["npm", "start"]

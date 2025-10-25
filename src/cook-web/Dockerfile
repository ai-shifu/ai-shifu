ARG SRC_ROOT=src
ARG WEB_SRC=${SRC_ROOT}/cook-web
ARG I18N_SRC=${SRC_ROOT}/i18n

FROM node:20.11.1-alpine AS builder

WORKDIR /app

COPY ${WEB_SRC}/package.json ${WEB_SRC}/package-lock.json ./

RUN npm config set fetch-retries 5 && \
    npm config set fetch-retry-mintimeout 20000 && \
    npm config set fetch-retry-maxtimeout 120000 && \
    npm config set fetch-timeout 300000 && \
    npm ci && \
    npm cache clean --force

COPY ${WEB_SRC} ./
COPY ${I18N_SRC} ./src/i18n

RUN npm run build --ignore-scripts

FROM node:20.11.1-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV I18N_ROOT=/app/src/i18n

RUN apk add --no-cache libc6-compat

COPY --from=builder /app/package.json ./
COPY --from=builder /app/package-lock.json ./
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/src/i18n ./src/i18n

RUN npm ci --only=production --ignore-scripts && \
    npm cache clean --force && \
    rm -rf /root/.cache /root/.npm /tmp/*

EXPOSE ${PORT:-3000}

USER node

CMD ["npm", "start"]

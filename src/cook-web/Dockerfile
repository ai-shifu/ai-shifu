FROM node:20.11.1-alpine AS builder

WORKDIR /app

# Copy dependency manifests from current context (support building with context=src/cook-web)
COPY package.json package-lock.json ./

RUN npm config set fetch-retries 5 && \
    npm config set fetch-retry-mintimeout 20000 && \
    npm config set fetch-retry-maxtimeout 120000 && \
    npm config set fetch-timeout 300000 && \
    npm ci && \
    npm install --include=optional sharp || true && \
    npm cache clean --force

# Copy project source
COPY . ./

RUN npm run build

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
# i18n metadata is read at runtime via NEXT_PUBLIC_I18N_META; no need to copy shared tree here

RUN npm ci --only=production && \
    npm cache clean --force && \
    rm -rf /root/.cache /root/.npm /tmp/*

EXPOSE ${PORT:-3000}

USER node

CMD ["npm", "start"]

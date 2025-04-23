FROM node:20.11.1-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./

RUN npm ci && \
    npm cache clean --force

COPY . .

RUN npm run build  --ignore-scripts 

FROM node:20.11.1-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN apk add --no-cache libc6-compat

COPY --from=builder /app/package.json ./
COPY --from=builder /app/package-lock.json ./
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public

RUN npm ci --only=production  --ignore-scripts   && \
    npm cache clean --force && \
    rm -rf /root/.cache && \
    rm -rf /root/.npm && \
    rm -rf /tmp/*

EXPOSE ${PORT:-3000}

USER node

CMD ["npm", "start"]

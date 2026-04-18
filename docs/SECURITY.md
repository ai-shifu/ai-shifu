# Security

## Principles

- Keep secrets and environment-specific credentials out of versioned docs,
  scripts, compose files, and generated instruction mirrors.
- Route browser smoke tests through the existing local dev stack without
  introducing privileged bypasses.
- Prefer request-id correlation and trace hints over dumping broad logs into
  user-facing outputs.
- Keep local observability services anonymous or local-only in dev; do not
  expose them as remote production dependencies.

## Repository Rules

- Shared instructions must continue to forbid hardcoded secrets and
  environment-specific URLs.
- Generated knowledge files must not embed secret values.
- Diagnostics scripts may surface request-scoped evidence, but they must avoid
  printing unrelated log history when the request id is missing or ambiguous.
- Local observability compose config may expose loopback-only ports for Grafana,
  Loki, Tempo, Prometheus, and OTEL, but it must not require committed secrets.

## Follow-Up Areas

- If observability expands beyond local-only dev usage, document access control,
  retention, and credential handling before widening the scope.
- If browser smoke coverage expands to authenticated third-party providers,
  provider credentials must stay behind existing configuration layers.

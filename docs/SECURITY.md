# Security

## Principles

- Keep secrets and environment-specific credentials out of versioned docs,
  scripts, compose files, and generated instruction mirrors.
- Route browser smoke tests through the existing local dev stack without
  introducing privileged bypasses.
- Prefer request-id correlation and trace hints over dumping broad logs into
  user-facing outputs.

## Repository Rules

- Shared instructions must continue to forbid hardcoded secrets and
  environment-specific URLs.
- Generated knowledge files must not embed secret values.
- Diagnostics scripts may surface request-scoped evidence, but they must avoid
  printing unrelated log history when the request id is missing or ambiguous.

## Follow-Up Areas

- If a richer observability stack is added later, document credential
  management and local isolation before enabling it by default.
- If browser smoke coverage expands to authenticated third-party providers,
  provider credentials must stay behind existing configuration layers.

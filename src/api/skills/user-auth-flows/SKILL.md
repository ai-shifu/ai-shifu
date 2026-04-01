---
name: user-auth-flows
description: Use when changing backend user auth, verification codes, token
  persistence, temp-user behavior, or auth-provider integration. Keep provider
  dispatch and credential state centralized.
---

# User Auth Flows

## Core Rules

- Keep repository, token-store, and auth-factory paths as the source of truth.
- Preserve verification-code consumption semantics and retry safety.
- Update frontend-facing auth payloads together with backend persistence logic.

## Workflow

1. Start from `repository.py`, `token_store.py`, `auth/factory.py`, and the
   specific flow file such as `email_flow.py` or `phone_flow.py`.
2. Confirm whether the change affects credentials, tokens, temp users, or
   provider dispatch.
3. Update validation and persistence together; avoid one-sided changes in route
   or provider code.
4. Add or update tests under `src/api/tests/service/user/`.

## Regression Checklist

- Happy-path login or verification.
- Retry or duplicate submission path.
- Invalid or expired verification code.
- Token persistence and logout semantics when affected.

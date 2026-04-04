---
name: gen-mdf-proxy
description: Use when changing the backend MDF proxy, request validation,
  timeout handling, or frontend/backend ownership for MDF conversion. Keep the
  external service hidden from the browser.
---

# MDF Proxy

## Core Rules

- The frontend must call the backend proxy, not the external MDF service.
- Preserve validation for text length, language, and timeout before proxying.
- Return error payloads that remain localizable and do not leak upstream config.

## Workflow

1. Start from `src/api/flaskr/service/gen_mdf/route.py` and `funcs.py`.
2. Check whether the change affects request validation, upstream request shape,
   timeout handling, or response normalization.
3. Keep secrets and external URLs on the backend side only.
4. Add or update focused tests under `src/api/tests/service/gen_mdf/` if this
   module gains broader behavior.

## Regression Checklist

- Valid conversion request.
- Validation failure for oversize or unsupported language input.
- Upstream timeout or provider error.
- Frontend still calls the backend proxy contract.

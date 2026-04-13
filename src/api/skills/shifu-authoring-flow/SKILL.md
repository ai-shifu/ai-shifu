---
name: shifu-authoring-flow
description: Use when changing backend shifu authoring, draft history, publish,
  outline structure, or import/export behavior. Keep draft and publish flows
  consistent and protect outline integrity.
---

# Shifu Authoring Flow

## Core Rules

- Preserve the separation between draft state, publish state, and history logs.
- Route structural changes through the dedicated shifu helper modules instead of
  mutating trees directly in routes.
- Keep import/export payload changes synchronized with validation, permissions,
  and history behavior.

## Workflow

1. Start from `route.py`, `funcs.py`, and the relevant `shifu_*` helper module.
2. Identify whether the change affects draft state, publish state, or both.
3. Update permissions, structural validation, and import/export behavior
   together when the payload contract moves.
4. Add or update tests under `src/api/tests/service/shifu/`.

## Regression Checklist

- Draft save and reload.
- Publish path.
- Import/export if payload shape changed.
- Permission failure path.

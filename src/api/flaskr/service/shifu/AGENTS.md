# Backend Service: shifu

This module owns core shifu authoring, outline structure, draft history,
publish, import/export, permissions, and resource-link management.

Entry files in this directory: `route.py`, `funcs.py`, `models.py`,
`permissions.py`, `shifu_history_manager.py`.

## Do

- Preserve the separation between draft state, publish state, and history logs
  so authoring recovery remains trustworthy.
- Keep outline and structural mutations going through the dedicated shifu
  helper modules instead of ad-hoc tree edits.
- Treat import/export, ask-provider config, and permissions as cross-cutting
  contracts that need coordinated updates.

## Avoid

- Do not mutate outline structures directly from route handlers when the shifu
  helper modules already own those transitions.
- Do not change publish or import/export payload shapes without updating
  related history and validation behavior together.
- Do not bypass permission checks when adding authoring or admin operations in
  this module.

## Tests

`cd src/api && pytest tests/service/shifu/ -q`

## Related Skills

- `src/api/skills/shifu-authoring-flow/SKILL.md`

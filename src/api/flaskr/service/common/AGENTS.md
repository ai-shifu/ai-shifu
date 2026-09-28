# Backend Service: common

This module owns shared backend DTOs, app exceptions, dictionaries, storage
helpers, and other cross-service primitives.

Entry files in this directory: `dtos.py`, `models.py`, `dicts.py`,
`storage.py`.

Shared compatibility, i18n, privacy and verification rules are inherited from
the root and `src/api/AGENTS.md`; the constraints below are local.

## Do

- Treat shared DTOs and app exceptions as compatibility surfaces used by many
  backend modules.
- Keep storage-provider selection and helper behavior centralized here instead
  of branching it in every service.
- Add new cross-service primitives here only when they are genuinely shared
  and not just convenient for one module.

## Avoid

- Do not reimplement storage or dictionary helpers inside feature services
  when the shared layer should own them.
- Do not let this module become a grab bag for service-specific logic that
  belongs in a dedicated domain directory.

## Tests

`cd src/api && pytest tests/service/common/ -q`

# Cook Web Domain: lib/shifu

This module owns course business orchestration for shifu and state transform
helpers consumed by learner flows and shared stores.

Entry files in this directory: `Shifu.ts`, `shifuUtils.ts`, `storeUtil.ts`.

Shared compatibility, i18n, privacy and verification rules are inherited from
the root and `src/web/AGENTS.md`; the constraints below are local.

## Do

- Keep course business transformations centralized so `c` pages and stores do
  not all reshape the same payloads differently.
- Preserve compatibility with `api` response shapes and `store` state
  expectations when business behavior changes.
- Treat this subtree as the right place for course orchestration, not for
  low-level request or UI-only helpers.

## Avoid

- Do not duplicate shifu or state transformations in pages when this service
  layer already owns them.

## Tests

Cover transformation contracts in tests under `src/web/src/lib/shifu/` and the
affected stores or learner flows.

## Related Skills

- `src/web/skills/chat-element-streaming/SKILL.md`
- `src/web/skills/interaction-user-input-defaults/SKILL.md`

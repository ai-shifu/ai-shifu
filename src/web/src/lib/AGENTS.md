# Cook Web Domain: lib

This module owns shared frontend infrastructure such as request handling,
generated API wrappers, i18n helpers, normalization, and testable utility
code.

Entry files in this directory: `request.ts`, `api.ts`, `shifu-normalize.ts`,
`unified-i18n-backend.ts`.

Shared compatibility, i18n, privacy and verification rules are inherited from
the root and `src/web/AGENTS.md`; the constraints below are local.

## Do

- Keep raw Umami calls in tracking.ts; preserve identify, queue, drain, SPA
  pageview deduplication, and tracked-referrer ordering.
- Preserve shared URL, interaction, lesson-feedback, audio, and storage
  semantics when changing helpers.
- Keep request transport, business-code handling, and shared API generation
  logic centralized in this domain.
- Treat this directory as the right home for cross-cutting frontend logic that
  should not live inside route components.

## Avoid

- Do not move request or auth-header behavior into pages or components when
  `lib/request.ts` already owns that path.
- Do not reimplement shared normalization helpers in feature code when they
  belong here.

## Tests

`cd src/web && npm run test -- src/lib/`

## Related Skills

- `src/web/skills/module-augmentation-guardrails/SKILL.md`
- `src/web/skills/deep-link-lessonid-routing/SKILL.md`
- `src/web/skills/interaction-user-input-defaults/SKILL.md`
- `src/web/skills/listen-mode-audio-streaming/SKILL.md`

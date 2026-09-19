# Cook Web Domain: lib

This module owns shared frontend infrastructure such as request handling,
generated API wrappers, i18n helpers, normalization, and testable utility
code.

Entry files in this directory: `request.ts`, `api.ts`, `shifu-normalize.ts`,
`unified-i18n-backend.ts`.

## Do

- Keep raw Umami calls in tracking.ts; preserve identify, queue, drain, SPA
  pageview deduplication, and tracked-referrer ordering.
- Keep analytics fail-open and accept only approved flat scalar fields;
  truncation or hashing does not make sensitive data safe.
- Preserve shared URL, interaction, lesson-feedback, audio, and storage
  semantics when changing helpers.
- Keep request transport, business-code handling, and shared API generation
  logic centralized in this domain.
- Preserve shared normalization and utility behavior used by multiple pages,
  hooks, or stores before changing payload assumptions.
- Treat this directory as the right home for cross-cutting frontend logic that
  should not live inside route components.

## Avoid

- Do not move request or auth-header behavior into pages or components when
  `lib/request.ts` already owns that path.
- Do not reimplement shared normalization helpers in feature code when they
  belong here.
- Do not change shared utility contracts without rerunning affected tests and
  type checks across consumers.

## Tests

`cd src/web && npm run test -- src/lib/`

## Related Skills

- `src/web/skills/module-augmentation-guardrails/SKILL.md`
- `src/web/skills/deep-link-lessonid-routing/SKILL.md`
- `src/web/skills/interaction-user-input-defaults/SKILL.md`
- `src/web/skills/listen-mode-audio-streaming/SKILL.md`

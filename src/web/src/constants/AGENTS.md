# Cook Web Domain: constants

This module owns shared course and UI constants used across learner and
teacher flows.

Entry files in this directory: `uiConstants.ts`, `courseConstants.ts`.

Shared compatibility, i18n, privacy and verification rules are inherited from
the root and `src/web/AGENTS.md`; the constraints below are local.

## Do

- Keep shared breakpoint, course, and UI constants as the single source of
  truth for all consumers.
- Treat this directory as configuration data rather than a place to hide
  behavior that belongs in hooks or services.

## Avoid

- Do not duplicate breakpoints or query-parameter constants in legacy pages
  when they already exist here.
- Do not mix runtime branching logic into constant files unless the logic is
  truly configuration-oriented.

## Tests

Run the tests of affected consumers when constant values or exports change.

## Related Skills

- `src/web/skills/chat-layout-width-detection/SKILL.md`

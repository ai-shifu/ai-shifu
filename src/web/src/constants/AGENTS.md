# Cook Web Domain: constants

This module owns shared course and UI constants used across learner and
teacher flows.

Entry files in this directory: `uiConstants.ts`, `courseConstants.ts`.

## Do

- Keep shared breakpoint, course, and UI constants as the single source of
  truth for all consumers.
- Preserve constant names and semantics when skills or stores already depend
  on them indirectly.
- Treat this directory as configuration data rather than a place to hide
  behavior that belongs in hooks or services.

## Avoid

- Do not duplicate breakpoints or query-parameter constants in legacy pages
  when they already exist here.
- Do not mix runtime branching logic into constant files unless the logic is
  truly configuration-oriented.
- Do not rename exported constants casually because many files import them
  directly.

## Tests

Run the tests of affected consumers when constant values or exports change.

## Related Skills

- `src/web/skills/chat-layout-width-detection/SKILL.md`

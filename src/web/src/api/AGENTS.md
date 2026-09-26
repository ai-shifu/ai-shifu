# Cook Web Domain: api

This module owns thin endpoint definition wrappers that expose Cook Web API
calls on top of the shared request and generated-client helpers.

Entry files in this directory: `api.ts`, `index.ts`, `user.ts`, `course.ts`,
`studyV2.ts`.

Shared compatibility, i18n, privacy and verification rules are inherited from
the root and `src/web/AGENTS.md`; the constraints below are local.

## Do

- Preserve learner request payloads and stream contracts alongside generated
  endpoint wrappers.
- Keep this layer declarative and thin so endpoint wiring stays easy to audit
  against backend contracts.
- Prefer the shared `lib/request.ts` and `lib/api.ts` stack instead of
  creating per-endpoint fetch wrappers here.

## Avoid

- Do not add ad-hoc response-shape parsing here when centralized business-code
  handling already exists lower in the stack.
- Do not duplicate route constants or auth-header behavior that belongs in
  shared request utilities.
- Do not duplicate endpoint wrappers or change learner request shapes while
  reorganizing API modules.

## Tests

`cd src/web && npm run test -- src/api/`

## Related Skills

- `src/web/skills/deep-link-lessonid-routing/SKILL.md`

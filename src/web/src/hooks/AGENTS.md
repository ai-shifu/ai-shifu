# Cook Web Domain: hooks

This module owns shared React hooks for auth, audio coordination, and other
reusable frontend behavior.

Entry files in this directory: `useAuth.ts`, `useExclusiveAudio.ts`,
`useGoogleAuth.ts`, `useToast.tsx`.

Shared compatibility, i18n, privacy and verification rules are inherited from
the root and `src/web/AGENTS.md`; the constraints below are local.

## Do

- Keep business events on useTracking and delegate Umami transport to
  lib/tracking.ts.
- Preserve browser and server assumptions explicitly so hooks do not
  accidentally run client-only code on the server.
- Treat hooks as reusable orchestration layers that should call shared stores
  and libs instead of duplicating low-level logic.

## Avoid

- Do not hide API calls or state transitions in hooks without keeping the
  underlying shared utilities testable.
- Do not couple hooks to one page or one route if the behavior should stay
  generally reusable.

## Tests

`cd src/web && npm run test -- src/hooks/`

## Related Skills

- `src/web/skills/hook-contract-refactor-safety/SKILL.md`

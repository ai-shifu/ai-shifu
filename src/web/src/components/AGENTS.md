# Cook Web Domain: components

This module owns shared React UI and business components used across learner,
admin, auth, settings, preview, and chat-oriented experiences.

Entry files in this directory: `auth/EmailLogin.tsx`,
`shifu-edit/ShifuEdit.tsx`, `ui/Button.tsx`.

Shared compatibility, i18n, privacy and verification rules are inherited from
the root and `src/web/AGENTS.md`; the constraints below are local.

## Do

- Preserve learner mobile, modal, branding, and chat styling and props when
  moving shared components.
- Treat chat, preview, and auth components as shared behavior that often needs
  coordinated store and skill updates.

## Avoid

- Do not hide domain logic in styling-only components when the behavior
  belongs in hooks, stores, or shared libs.
- Do not add one-off request logic inside components that should call shared
  API helpers.
- Do not copy interaction or streaming behavior between components when an
  existing shared component or skill already describes it.

## Tests

`cd src/web && npm run test -- src/components/`

## Related Skills

- `src/web/skills/chat-element-streaming/SKILL.md`
- `src/web/skills/chat-actionbar-ask-placement/SKILL.md`
- `src/web/skills/listen-mode-audio-streaming/SKILL.md`

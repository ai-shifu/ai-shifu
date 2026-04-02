# Claude Rule: Cook Web Frontend

This rule narrows Claude's attention to the Cook Web subtree when the task is
rooted in Next.js routes, stores, shared libs, or `c-*` code.

- Start with `src/cook-web/CLAUDE.md`, then prefer the closest
  `src/cook-web/src/<domain>/CLAUDE.md` for domain-specific work.

- Keep frontend changes aligned with `src/cook-web/AGENTS.md` and the
  frontend sections of `docs/engineering-baseline.md`.

- Keep frontend request work on `src/cook-web/src/lib/request.ts` and
  `src/cook-web/src/lib/api.ts`, preserve the unified business-code handling
  path, and do not add ad-hoc component fetch logic.

- Route user-facing strings through shared i18n JSON under `src/i18n/`, keep
  Next.js route-entry files on `page.tsx`, `layout.tsx`, and `route.ts`, and
  treat `c-*` directories as active compatibility surfaces.

- Follow existing focused frontend skills for chat streaming, ask placement,
  layout width detection, route deep-linking, hook contract refactors, and
  listen-mode audio behavior.

- Ignore backend path rules unless the task explicitly changes the HTTP
  contract or shared translation/config boundary.

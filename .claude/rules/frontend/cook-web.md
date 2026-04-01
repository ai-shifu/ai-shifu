# Claude Rule: Cook Web Frontend

This rule narrows Claude's attention to the Cook Web subtree when the task is
rooted in Next.js routes, stores, shared libs, or `c-*` code.

- Start with `src/cook-web/CLAUDE.md`, then prefer the closest
  `src/cook-web/src/<domain>/CLAUDE.md` for domain-specific work.

- Keep frontend changes aligned with `src/cook-web/AGENTS.md` and the
  frontend sections of `docs/engineering-baseline.md`.

- Follow existing focused frontend skills for chat streaming, ask placement,
  layout width detection, route deep-linking, hook contract refactors, and
  listen-mode audio behavior.

- Ignore backend path rules unless the task explicitly changes the HTTP
  contract or shared translation/config boundary.

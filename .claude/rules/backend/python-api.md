# Claude Rule: Backend Python API

This rule narrows Claude's attention to the backend subtree when the task is
rooted in Flask services, migrations, or backend scripts.

- Start with `src/api/CLAUDE.md`, then prefer the closest
  `src/api/flaskr/service/<module>/CLAUDE.md` if a single service owns the
  task.

- Keep backend changes aligned with `src/api/AGENTS.md` and the backend
  sections of `docs/engineering-baseline.md`.

- Reuse the shared API response envelope with `code`, `message`, and `data`,
  keep translations in `src/i18n/`, and keep provider integration behind the
  LiteLLM and shared helper layers.

- Generate and review new Alembic migrations instead of editing applied
  revisions, and do not add hard database foreign-key constraints for
  business-key relationships unless the architecture changes deliberately.

- Reach for backend skills when work touches shifu authoring, user auth flows,
  or the MDF proxy boundary.

- Ignore frontend-specific subtree rules unless the task clearly crosses the
  backend/frontend contract boundary.

# Claude Rule: Backend Python API

This rule narrows Claude's attention to the backend subtree when the task is
rooted in Flask services, migrations, or backend scripts.

- Start with `src/api/CLAUDE.md`, then prefer the closest
  `src/api/flaskr/service/<module>/CLAUDE.md` if a single service owns the
  task.

- Keep backend changes aligned with `src/api/AGENTS.md` and the backend
  sections of `docs/engineering-baseline.md`.

- Reach for backend skills when work touches shifu authoring, user auth flows,
  or the MDF proxy boundary.

- Ignore frontend-specific subtree rules unless the task clearly crosses the
  backend/frontend contract boundary.

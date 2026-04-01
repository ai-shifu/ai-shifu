# AI Collaboration Rules

This repository uses layered AI instructions. Start at the nearest
`AGENTS.md`, inherit parent guidance only when the local file does not
override it, and use `CLAUDE.md` as a thin Claude-specific wrapper.

## Scope

- This root file owns repository-wide AI collaboration rules that apply across
  backend, frontend, scripts, Docker, shared i18n assets, and future
  first-class development surfaces.

- Shared engineering conventions live in the
  [engineering baseline](docs/engineering-baseline.md). Keep this file focused
  on AI execution behavior, not the full engineering handbook.

- Keep shared rules here only when both Codex and Claude should follow them.
  Move subsystem details into [src/api/AGENTS.md](src/api/AGENTS.md),
  [src/cook-web/AGENTS.md](src/cook-web/AGENTS.md), or deeper module files.

- Any new directory that becomes a primary engineering surface must add its
  own `AGENTS.md` and `CLAUDE.md` before the split is considered complete for
  that area.

## Do

- Start every task by locating the nearest `AGENTS.md`, then inherit the root
  rules only for topics not redefined in the local scope.

- Before modifying code, inspect the current implementation, adjacent call
  sites, and the nearest tests or docs so decisions are grounded in the
  existing system instead of assumptions.

- Maximize reuse of existing modules, utilities, stores, DTOs, provider
  layers, and established patterns. Extend the current implementation before
  creating a new abstraction.

- Use [docs/engineering-baseline.md](docs/engineering-baseline.md) for
  repository-wide engineering conventions such as architecture, testing,
  naming, i18n, API contracts, migrations, and environment workflow.

- Treat `AGENTS.md` and `CLAUDE.md` as the primary instruction source. Before
  each commit, review the touched ones and keep Cursor, Copilot, and Claude
  routing docs aligned when shared guidance changes or becomes stale.

- Before implementing a complex design or cross-module architecture change,
  create a design doc under `docs/` and a paired `tasks.md` checklist under
  the same `docs/` topic folder. Execute the work from that checklist and keep
  it current as the visible source of truth for progress.

- Run the smallest relevant verification first, then widen to shared checks
  when a change crosses API boundaries, shared DTOs, i18n files, or common
  frontend libraries.

## Avoid

- Do not duplicate the same rule in multiple `AGENTS.md` files. Promote
  shared rules upward and keep local files additive instead of repetitive.

- Do not start modifying code based on guesswork when the local
  implementation, references, or tests have not been inspected yet.

- Do not build a new helper, abstraction, or code path when an existing one
  can be reused or extended cleanly.

- Do not create a commit that changes implementation contracts while leaving
  the affected `AGENTS.md`, `CLAUDE.md`, or compatibility instructions
  outdated.

- Do not start a complex design implementation without a design doc in `docs/`
  and a linked `tasks.md` checklist that tracks done and pending work.

- Do not hardcode user-facing strings, secrets, or environment-specific URLs
  in code or docs. Route text through i18n and credentials through the
  existing configuration layers.

- Do not place long troubleshooting runbooks in `AGENTS.md`. Use `SKILL.md`
  for repeatable workflows that need step-by-step guidance.

## Commands

- `pre-commit run -a` from the repository root is the shared quality gate
  before any commit-sized change lands.

- `cd src/api && pytest -q` is the broad backend verification baseline when a
  change touches shared backend contracts or multiple services.

- `cd src/cook-web && npm run type-check && npm run lint` is the broad
  frontend verification baseline for shared Cook Web changes.

- `python scripts/check_ai_collab_docs.py` validates the layered AI-doc layout
  and the hand-maintained engineering baseline links.

## Tests

- Run targeted backend pytest modules under `src/api/tests/` when a change
  touches Flask services, models, DTOs, or migration-related code.

- Run targeted Jest or React tests under `src/cook-web/src/` when a change
  touches frontend pages, stores, shared hooks, or request code.

- Run translation validation scripts whenever shared i18n namespaces or
  translation file inventories change.

- When a task updates only docs or instruction files, at minimum run the
  AI-doc validation script and note that no runtime code changed.

## Related Skills

- `SKILL.md` is the repository-level skill index and boundary map.

- `src/api/SKILL.md` is the backend skill entry for Flask services and
  backend-specific recurring workflows.

- `src/cook-web/SKILL.md` is the frontend skill entry for Cook Web and its
  focused troubleshooting skills.

- Claude-only path routing belongs under `/.claude/rules/`; Cursor and
  Copilot mirrors live under `/.cursor/rules/` and `/.github/`.

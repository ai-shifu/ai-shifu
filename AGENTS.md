# AI Collaboration Rules

This root file is the repository entry point for coding agents. Start here,
then move to the nearest subtree `AGENTS.md` and the knowledge docs it points
to.

## Scope

- Apply this file across the repository unless a deeper `AGENTS.md` narrows
  the rules.
- Treat `ARCHITECTURE.md`, `PLANS.md`, and `docs/engineering-baseline.md` as
  the main source documents behind this entry point.
- Use `docs/QUALITY_SCORE.md`, `docs/RELIABILITY.md`, and `docs/SECURITY.md`
  to understand repository-wide quality gaps and harness constraints.

## Do

- Read the nearest `AGENTS.md` before editing and use `ARCHITECTURE.md` to
  orient yourself when work crosses multiple surfaces.
- Inspect the current implementation, adjacent call sites, and nearby tests or
  docs before changing behavior.
- Reuse existing modules, DTOs, stores, provider wrappers, and request paths
  before creating new abstractions.
- Use ExecPlans for complex work. `PLANS.md` defines the format, and active
  plans live under `docs/exec-plans/active/`.
- Keep shared instruction surfaces aligned. When shared rules move, update the
  touched `AGENTS.md`, `CLAUDE.md`, generated `.cursor` rules, and generated
  `.github` instructions in the same change.
- Keep code-facing text in English and keep user-facing text in shared i18n
  JSON under `src/i18n/`.

## Avoid

- Do not rely on chat-only context for repository decisions that should be
  discoverable from versioned files.
- Do not start modifying code from guesswork when the local implementation and
  neighboring tests have not been inspected.
- Do not hardcode user-facing strings, secrets, or environment-specific URLs.
- Do not create new root `tasks.md` checklists. Complex execution now belongs
  in ExecPlans under `docs/exec-plans/`.
- Do not let shared guidance drift from generated mirrors or from the current
  repository structure.

## Commands

- `python scripts/generate_ai_collab_docs.py` regenerates compatibility
  instruction surfaces.
- `python scripts/build_repo_knowledge_index.py` regenerates repository
  knowledge indexes and the doc inventory.
- `python scripts/check_repo_harness.py` validates AI-doc ownership, knowledge
  metadata, and generated harness artifacts.
- `python scripts/check_architecture_boundaries.py` validates the committed
  frontend/backend boundary baseline and blocks new drift.
- `pre-commit run -a` is the repository-wide verification gate before a
  commit-sized change lands.

## Tests

- Run the smallest relevant backend, frontend, or script checks first, then
  widen only when the change crosses a shared contract or multiple surfaces.
- When a task touches only docs or instruction files, at minimum run
  `python scripts/check_repo_harness.py`.
- When a task changes shared boundaries or introduces new app/service
  dependencies, run `python scripts/check_architecture_boundaries.py`.
- When a task touches the browser harness, run `cd src/cook-web && npm run test:e2e`.

## Related Skills

- `SKILL.md` is the repository-level skill routing index.
- `src/api/SKILL.md` owns backend workflow skills.
- `src/cook-web/SKILL.md` owns frontend workflow skills.

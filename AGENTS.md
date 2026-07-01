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
- Before committing, run `python scripts/check_dev_tools.py` to confirm
  lefthook and its underlying tools are installed; the local checks are
  silently skipped if lefthook was never installed.
- When a branch already has an open PR, keep the PR title and description in
  sync with the latest code changes so they accurately describe the current
  implementation and verification state.
- Keep shared instruction surfaces aligned. When shared rules move, update the
  touched `AGENTS.md`, `CLAUDE.md`, generated `.cursor` rules, and generated
  `.github` instructions in the same change.
- Keep code-facing text in English and keep user-facing text in shared i18n
  JSON under `src/i18n/`.
- Store and compute all timestamps in UTC. On the backend, use the shared
  `now_utc()` helper in `src/api/flaskr/util/datetime.py` for any time written
  to the database, and default new model timestamp columns to
  `default=now_utc` / `onupdate=now_utc`. The DB session is pinned to UTC in
  `src/api/flaskr/dao/__init__.py`; treat that as a safety net, not a license
  to write local time.
- In Chinese user-facing text and Chinese docs, do not use `创作者` as a
  generic product term. Use `老师` for the general course-building or teacher
  account role; use `课程负责人` or, inside an existing course context,
  `负责人` when referring to a specific course owner.
- Keep English and French translations aligned with that distinction: use
  `teacher` / `enseignant` for the generic role, while a specific course
  owner may still be translated as `creator` / `créateur`.

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
- Do not introduce mixed-timezone timestamps: avoid `func.now()` /
  `CURRENT_TIMESTAMP` defaults and naked `datetime.now()` / `datetime.utcnow()`
  for stored times. They depend on the DB session or process time zone and
  reintroduce the UTC-vs-local drift; use `now_utc()` instead.

## Commands

- `python scripts/generate_ai_collab_docs.py` regenerates compatibility
  instruction surfaces.
- `python scripts/build_repo_knowledge_index.py` regenerates repository
  knowledge indexes and the doc inventory.
- `python scripts/check_repo_harness.py` validates AI-doc ownership, knowledge
  metadata, and generated harness artifacts.
- `python scripts/check_architecture_boundaries.py` validates the committed
  frontend/backend boundary baseline and blocks new drift.
- `python scripts/check_dev_tools.py` verifies lefthook and its underlying
  tools are installed, so the pre-commit hooks are not silently skipped.
- `lefthook run pre-commit --all-files` is the repository-wide verification
  gate before a commit-sized change lands.

## MarkdownFlow component libraries

ai-shifu consumes two MarkdownFlow component libraries. Changing either is
usually done in order to use it here, so the overall flow is: **change the
library → publish a build → point ai-shifu at it → debug locally / on test / in
prod**.

| Library            | Kind             | Pinned in                                            | Published from                                                            |
| ------------------ | ---------------- | ---------------------------------------------------- | ------------------------------------------------------------------------- |
| `markdown-flow`    | Python (backend) | `src/api/requirements.txt` (`markdown-flow==<ver>`)  | [markdown-flow-agent-py](https://github.com/ai-shifu/markdown-flow-agent-py) (PyPI) |
| `markdown-flow-ui` | npm (frontend)   | `src/cook-web/package.json` (`"markdown-flow-ui"`)   | [markdown-flow-ui](https://github.com/ai-shifu/markdown-flow-ui) (npm)    |

### Trying a library change against this project

1. In the library repo, on your branch, run its **Publish** action to release a
   build — use a `dev` build (`X.Y.Z.devN` on PyPI, `X.Y.Z-dev.N` on npm) for a
   throwaway test package. Wait for the run to pass; the version is now published.
2. Point this project at that version:
   - **Locally (uncommitted)**: edit the pin in `src/api/requirements.txt`
     (backend) or `src/cook-web/package.json` (frontend).
   - **On an already-pushed feature branch**: run the matching bump action —
     **Bump markdown-flow** (`bump-markdown-flow.yml`) or **Bump markdown-flow-ui**
     (`bump-markdown-flow-ui.yml`). Each validates the version is published,
     updates the pin, and pushes the bump back to the branch. Both refuse to run
     on `main`. (The frontend bump pins an exact version and refreshes
     `src/cook-web/package-lock.json` so CI's `npm ci` stays green.)

### Rule: `main` must pin RELEASE versions of both libraries

dev builds are for feature-branch / cross-repo testing only. `main` must always
pin **release** versions (`X.Y.Z`) of both libraries. Two CI checks enforce this
on every PR into `main` and fail on a pre-release/dev pin:

- **Check markdown-flow release pin** (`check-markdown-flow-release.yml`) — backend.
- **Check markdown-flow-ui release pin** (`check-markdown-flow-ui-release.yml`) — frontend.

Pin release versions of both before merging.

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

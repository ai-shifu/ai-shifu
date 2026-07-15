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
- For git commit message title, body, and classification requirements, use
  [Git Commit Message Requirements](#git-commit-message-requirements); keep
  agent-specific rule files pointing there instead of duplicating the policy.
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
- Serialize timestamps as UTC ISO-8601 with a trailing `Z` on the read side.
  Prefer leaving DTO datetime fields as raw `datetime | None` and letting the
  single serialization sink `fmt()` in `src/api/flaskr/route/common.py` emit
  them (it treats naive values as UTC and converts aware values to UTC). When
  you must serialize by hand, use `to_utc_iso()` in
  `src/api/flaskr/util/datetime.py`; return `null` for missing times rather
  than `""` or a pre-formatted string. Display-time timezone conversion is a
  pure frontend concern: the browser renders UTC via helpers such as
  `formatAdminUtcDateTime`, so the API must not localize by request timezone.
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
- Do not bypass the read-side UTC contract: avoid emitting API datetimes with a
  naive `datetime.isoformat()` / `strftime(...)` (no `Z`), do not localize
  display times server-side from a request/browser `?timezone=` param, and do
  not compare timestamps that carry different serialization contracts (naive
  vs offset-aware, or string vs string) — normalize both to UTC before
  comparing. These are exactly the drifts that reappear when new code lands in
  modules the UTC sweep has not yet reached.

## Git Commit Message Requirements

All git commit message requirements live in this section. Other docs and
agent-specific rule files may point here for title, body, and classification
rules, but must not duplicate or redefine them.

- Human-authored and coding-agent-authored commit messages must follow the
  policy below. Existing workflow-generated bot commits are exempt unless the
  workflow is being updated for this policy.
- The local `commit-msg` hook is only a baseline Conventional Commits syntax
  check. It does not enforce the `Changed:` / `Benefit:` body or the
  classification rules below.
- Subject: use English Conventional Commits without scope parentheses, such as
  `type: summary`; do not use `type(scope): summary`. Write the summary in
  plain language that product users can understand. When a change affects
  users, describe the user-visible outcome or benefit instead of only naming
  the internal implementation detail (e.g., 'fix: prevent audio overlapping'
  instead of 'fix: update useExclusiveAudio state').
- Body: include exactly two sections, `Changed:` and `Benefit:`.
- Classification: use `chore` for repository-maintenance-only instruction or
  generated guidance updates like this file.
- Runtime prompt, template, and system-prompt changes affect product behavior:
  use `feat` when adding capability and `fix` when correcting behavior; do not
  use `docs`.

Example:

```text
chore: centralize commit message requirements

Changed:
Moved repository commit message requirements into the root AGENTS.md file.

Benefit:
Contributors have one place to check the required commit title and body format.
```

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

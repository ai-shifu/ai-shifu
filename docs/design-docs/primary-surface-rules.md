---
title: Primary Surface Rules Completion
status: implemented
owner_surface: repo
last_reviewed: 2026-04-17
canonical: true
---

# Primary Surface Rules Completion

## Summary

Close the remaining governance gap in the layered AI-doc system by giving the
three still-unowned primary engineering surfaces their own local rule entry
points:

- `.github/`
- `docker/`
- `scripts/`

The repo already treats these areas as first-class engineering surfaces in
practice, but they currently rely only on the root `AGENTS.md` and the
baseline handbook.

## Problems

- `.github/` owns test, release, and image-build automation, but no local
  `AGENTS.md` explains trigger safety, secret handling, or release coupling.
- `docker/` owns compose and deployment-facing behavior, but no local
  `AGENTS.md` explains the semantic split between dev, latest, and pinned
  compose files.
- `scripts/` owns generators and validators that can rewrite tracked files,
  but no local `AGENTS.md` states idempotence, ownership, or generator/checker
  alignment rules.
- `docs/engineering-baseline.md` mentions release flow only at a high level,
  while the repository has concrete GitHub workflows for tests, release
  preparation, latest-image builds, and release-image builds.

## Decisions

### Local rule ownership

- Add hand-maintained `AGENTS.md` files for `.github/`, `docker/`, and
  `scripts/`.
- Keep these files concise and operational, with the standard `Scope`, `Do`,
  `Avoid`, `Commands`, `Tests`, and `Related Skills` headings.
- Generate thin `CLAUDE.md` wrappers for the same surfaces.

### Handbook expansion

- Add a `## CI/CD And Release Workflow` section to
  `docs/engineering-baseline.md`.
- Document the actual workflow inventory that exists in
  `.github/workflows/`.
- Describe the expected release path and how `prepare-release`, latest-image
  builds, and published-release image builds relate to each other.

### Mirror coverage

- Extend the generator so it creates:
  - `.github/CLAUDE.md`
  - `docker/CLAUDE.md`
  - `scripts/CLAUDE.md`
  - path-scoped Cursor rules for Docker, scripts, and GitHub workflows
  - Copilot path instructions for Docker, scripts, and GitHub workflows
- Keep the manual docs as the source of truth and the new mirrors derived.

### Validation

- Extend `scripts/check_ai_collab_docs.py` so missing manual AGENTS files for
  the three new surfaces fail validation.
- Require the new handbook heading to exist.
- Keep the existing generated-vs-manual ownership checks intact.

## Compatibility

- No runtime API, database, or product behavior changes
- No change to the layered AI-doc inheritance model
- No change to existing backend or frontend ownership split

## Verification

- `python scripts/generate_ai_collab_docs.py`
- `python scripts/check_ai_collab_docs.py`
- `pre-commit run --files .github/AGENTS.md docker/AGENTS.md scripts/AGENTS.md docs/design-docs/primary-surface-rules.md docs/engineering-baseline.md scripts/generate_ai_collab_docs.py scripts/check_ai_collab_docs.py .cursor/rules/*.mdc .github/instructions/*.instructions.md .github/CLAUDE.md docker/CLAUDE.md scripts/CLAUDE.md`

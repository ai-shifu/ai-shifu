---
title: AI Doc Generator Shrink And Baseline Restoration
status: implemented
owner_surface: repo
last_reviewed: 2026-04-17
canonical: true
---

# AI Doc Generator Shrink And Baseline Restoration

## Summary

This change moves the repository from a fully generated AI-instruction layer
to a hybrid model:

- Hand-maintained core AI docs for repository, backend, and frontend scopes
- One canonical engineering baseline doc under `docs/`
- Generated thin wrappers and repetitive compatibility surfaces only

The goal is to restore the engineering conventions that were compressed away
when the split AI-doc structure was introduced, without returning to a single
large root `AGENTS.md`.

## Problems

- The generator currently owns the root, backend, and frontend `AGENTS.md`
  files, which pushed stable engineering guidance into oversimplified
  templates.
- Some high-value conventions from the old root `AGENTS.md` are no longer
  clearly available from the nearest scope.
- The current ownership model makes it too easy to lose engineering baseline
  content when AI-collaboration templates are adjusted.

## Decisions

### Core doc ownership

- `AGENTS.md`, `src/api/AGENTS.md`, and `src/cook-web/AGENTS.md` become
  hand-maintained files.
- These files stay concise and focused on AI collaboration behavior, local
  execution rules, and links to the shared engineering baseline.
- They continue to use the standard `Scope`, `Do`, `Avoid`, `Commands`,
  `Tests`, and `Related Skills` headings so inheritance remains predictable.

### Engineering baseline

- Add `docs/engineering-baseline.md` as the canonical engineering baseline.
- Restore the near-full normative guidance from the old root `AGENTS.md`,
  including architecture notes, database conventions, API response norms,
  testing structure, workflow expectations, performance guidance, environment
  workflow, i18n rules, naming rules, and troubleshooting commands.
- Keep this document hand-maintained. It is a stable engineering reference,
  not a generated derivative.

### Generated surfaces

- Keep generation for:
  - root and nested `CLAUDE.md` wrappers
  - module-level backend service `AGENTS.md`
  - module-level frontend domain `AGENTS.md`
  - Cursor rules under `.cursor/rules/**`
  - Copilot instruction files under `.github/**`
- Stop generating:
  - `AGENTS.md`
  - `src/api/AGENTS.md`
  - `src/cook-web/AGENTS.md`
  - `.claude/rules/**`

### Validation model

- The validator must distinguish generated docs from hand-maintained docs.
- Generated docs still require the generated marker, line-count checks, and
  structure checks.
- Hand-maintained core docs must exist, include the expected anchor headings,
  and link to `docs/engineering-baseline.md` where appropriate.
- `docs/README.md` should remain valid for the flat design-doc plus root
  `tasks.md` workflow while allowing evergreen docs such as
  `docs/engineering-baseline.md`.

## Compatibility

- No runtime product behavior changes
- No database or API contract changes
- No change to the external AI-instruction surface names

Agents still interact with:

- `AGENTS.md` as the shared instruction source
- `CLAUDE.md` as the Claude wrapper
- `.claude/rules/**` for Claude-only routing
- `.cursor/rules/**` for Cursor compatibility
- `.github/**` for Copilot compatibility

## Verification

- `python scripts/check_ai_collab_docs.py`
- `python scripts/generate_ai_collab_docs.py`
- `python scripts/check_ai_collab_docs.py`
- `pre-commit run --files AGENTS.md src/api/AGENTS.md src/cook-web/AGENTS.md docs/engineering-baseline.md docs/README.md scripts/generate_ai_collab_docs.py scripts/check_ai_collab_docs.py`

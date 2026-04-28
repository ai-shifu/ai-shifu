---
title: AI Tool Compatibility Layer Design
status: implemented
owner_surface: repo
last_reviewed: 2026-04-17
canonical: true
---

# AI Tool Compatibility Layer Design

## Summary

Add a compatibility layer so the repository instruction system works not only
for Codex and Claude, but also for Cursor and GitHub Copilot.

The existing `AGENTS.md` and `CLAUDE.md` structure remains the primary source
of truth. Cursor and Copilot files become generated compatibility surfaces that
mirror the shared guidance instead of introducing a second independent rule
system.

## Goals

- Keep `AGENTS.md` and `CLAUDE.md` as the canonical shared instruction source.
- Add Cursor project rules in `.cursor/rules` and nested `.cursor/rules`
  directories for the main repository, backend, frontend, and docs workflow.
- Add GitHub Copilot repository and path-specific instructions in `.github/`.
- Generate the compatibility files from the same Python script that already
  generates layered `AGENTS.md` and `CLAUDE.md`.
- Validate the generated compatibility files so future changes do not leave
  Cursor or Copilot stale.

## Non-Goals

- Full one-to-one parity for every backend service and every frontend domain in
  Cursor-specific files during this step.
- Replacing the existing `AGENTS.md` hierarchy with Cursor or Copilot-native
  files.
- Creating a persistent backlog in root `tasks.md`.

## Design Decisions

### Source of truth

- `AGENTS.md` and `CLAUDE.md` stay primary.
- `.claude/rules`, `.cursor/rules`, `.github/copilot-instructions.md`, and
  `.github/instructions/*.instructions.md` are derived compatibility layers.

### Cursor structure

- Add one repository-wide always-apply rule in `.cursor/rules/`.
- Add nested rules in `docs/.cursor/rules/`, `src/api/.cursor/rules/`, and
  `src/cook-web/.cursor/rules/`.
- Keep the Cursor rules short and aligned with the existing repository
  behavior: inspect first, reuse first, docs/tasks workflow, and backend or
  frontend subsystem guidance.

### Copilot structure

- Add `.github/copilot-instructions.md` for repository-wide defaults.
- Add `.github/instructions/ai-instructions.instructions.md` for AI
  collaboration files.
- Add `.github/instructions/backend.instructions.md`,
  `.github/instructions/frontend.instructions.md`, and
  `.github/instructions/docs.instructions.md` for path-specific behavior.

### Validation

- Extend `scripts/check_ai_collab_docs.py` so it validates the generated Cursor
  and Copilot file presence plus basic frontmatter shape.
- Keep the validation lightweight: existence, generated marker, and required
  metadata fields.

## Implementation Plan

1. Extend the generator to emit Cursor and Copilot compatibility files.
2. Extend the validator to check the new generated file types.
3. Add this design doc and, while implementation is active, use root
   `tasks.md`.
4. Generate files, run validation, and run focused `pre-commit`.

## Acceptance Criteria

- Cursor compatibility files exist and are generated from the shared Python
  script.
- Copilot compatibility files exist in `.github/`.
- Validation covers the new generated files.
- The repository-level rules still pass line-count and section-order checks.
- Focused `pre-commit` passes for the changed files.

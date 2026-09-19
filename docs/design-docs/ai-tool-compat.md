---
title: AI Tool Compatibility Layer Design
status: implemented
owner_surface: repo
last_reviewed: 2026-09-19
canonical: true
---

# AI Tool Compatibility Layer Design

## Summary

`AGENTS.md` (root plus nested package and module files) is the only
project-instruction body for coding agents. Claude Code, Cursor, Codex,
Copilot coding agent, and Windsurf read `AGENTS.md` natively.

Tool-private files exist only for capabilities `AGENTS.md` cannot express:
Cursor globs / `alwaysApply` / descriptions, Claude path rules under
`.claude/rules/`, and optional zero-cost symlinks. They are thin pointers,
not a second rulebook.

This repository does not use Amazon Bedrock, Vertex, or Foundry for Claude
Code, so there is no Bedrock exception and no `CLAUDE.md` tree.

## Goals

- Keep layered `AGENTS.md` as the sole instruction body.
- Keep Cursor `.mdc` files and Copilot `applyTo` files as short pointers.
- Keep Claude-only path routing in `.claude/rules/` and skill playbooks in
  `SKILL.md`.
- Validate that `CLAUDE.md` never reappears and that generated mirrors stay
  thin.

## Non-Goals

- Parallel Windsurf, Cline, or Aider rule trees.
- Restating Umami, PR, or terminology rules in Cursor or Copilot files.
- Inventing dedicated `AGENTS.md` files for every backend service in this
  change. `creator_analytics` and `profile_research` remain a follow-up.

## Design Decisions

### Source of truth

- Nearest `AGENTS.md` is the only project-instruction body.
- Do not add `CLAUDE.md`. Nested `@AGENTS.md` wrappers block Claude Code
  native `AGENTS.md` loading on Claude Code 2.1.277 and later.
- `.claude/rules/` holds Claude-only path routing.
- `.cursor/rules/*.mdc` and nested `src/api/.cursor`, `src/web/.cursor`,
  and `docs/.cursor` rules keep Cursor-private frontmatter and point to
  `AGENTS.md`.
- `.github/copilot-instructions.md` and
  `.github/instructions/*.instructions.md` keep `applyTo` routing and point
  to `AGENTS.md`. Copilot coding agent should rely on native `AGENTS.md`.

### Intentional special cases

- `.cursorrules` is a legacy zero-cost symlink to `AGENTS.md`. Harmless;
  do not expand it into a second copy.
- `GEMINI.md` is a zero-cost symlink to `AGENTS.md`.
- `.github/instructions/agents.instructions.md` is a zero-cost symlink to
  `../../AGENTS.md`.
- `.cursor/environment.json`, run scripts, and `.codex/environments` are
  runtime configuration, not instruction surfaces.

### Generator and harness

- `scripts/generate_ai_collab_docs.py` emits module-level `AGENTS.md` from
  backend and frontend metadata, plus thin Cursor and Copilot pointers.
- The generator must not emit any `CLAUDE.md` file.
- Unused `ROOT_SPEC` / `API_SPEC` / `WEB_SPEC` templates are removed so they
  cannot look like sources of truth for hand-maintained `AGENTS.md`.
- `scripts/check_repo_harness.py` fails if a `CLAUDE.md` file exists, if the
  generator would recreate one, or if a generated-marker `AGENTS.md` is not
  owned by the generator.
- Hand-maintained module files such as `billing/AGENTS.md` and
  `referral/AGENTS.md` are registered in `MANUAL_AGENTS`.

### Validation

- Existence and generated-marker checks still apply to Cursor and Copilot
  files.
- Compatibility files must stay thin pointers and must not restate the
  root `AGENTS.md` hard-rule dump.

## Acceptance Criteria

- Zero `CLAUDE.md` files in the repository.
- Regenerating AI-collab docs does not recreate `CLAUDE.md`.
- Cursor and Copilot generated files are short pointers.
- `python scripts/check_repo_harness.py` is green.

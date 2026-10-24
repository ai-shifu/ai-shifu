---
title: AI Tool Compatibility Layer Design
status: implemented
owner_surface: repo
last_reviewed: 2026-09-20
canonical: true
---

# AI Tool Compatibility Layer Design

## Instruction Ownership

The root and nested `AGENTS.md` files are the only project-instruction body.
Each file adds constraints for its directory to the rules
in its ancestors; keep module files focused on their own behavior, contracts,
and verification. There is no instruction generator or minimum line count.

Root, backend, frontend, GitHub automation, Docker, and repository scripts
retain their own entry points. Mandatory constraints belong
in these instructions, close to the work they govern. The
[engineering baseline](../engineering-baseline.md) supplies expanded rationale,
examples, and troubleshooting, including the CI/CD and release workflow.
Reusable procedures belong in `SKILL.md` files. Complex work uses ExecPlans
under `docs/exec-plans/` according to [PLANS.md](../../PLANS.md).

This document replaces the earlier generator-shrink, hard-rules-restoration,
and primary-surface-rules designs. Their useful ownership and handbook
boundaries remain; their generated instruction mirrors and root `tasks.md`
workflow are retired.

## Compatibility Entry Points

- Codex and Cursor use the layered `AGENTS.md` tree. Cursor supports nested
  instructions, so no `.mdc` pointers or `.cursorrules` are needed. See
  [Cursor rules](https://cursor.com/docs/rules#agentsmd).
- `.github/copilot-instructions.md` is one short navigation entry
  pointing to the root and relevant nested `AGENTS.md` files. It covers
  Copilot surfaces whose native agent-instruction support differs; no
  parallel `.github/instructions/` tree is maintained. See the
  [Copilot support matrix](https://docs.github.com/en/copilot/reference/custom-instructions-support).
- `GEMINI.md` remains a symlink to the root `AGENTS.md` for Gemini CLI's
  default context filename. It contains no separate rules. See
  [Gemini context files](https://geminicli.com/docs/cli/gemini-md/).
- Claude Code uses native `AGENTS.md` under the conditions below. No
  `CLAUDE.md` files or shared-rule copies under `.claude/rules/` are tracked.
- `.cursor/environment.json`, Cursor run scripts, and `.codex/environments`
  are runtime configuration and remain independent of this cleanup.

## Claude Code Requirements

Use Claude Code 2.1.277 or later, with native `AGENTS.md` support active.
Confirm the startup `AGENTS.md loaded` message under the default Project
instructions setting. Nested files load when Claude reads files in those
directories. See the official
[AGENTS.md documentation](https://code.claude.com/docs/en/memory#agentsmd).

Native loading is unavailable in the first session after installing or
upgrading to a supporting version; start another session. It is also
unavailable when the session cannot fetch Anthropic feature flags (including
third-party provider or telemetry-disabled sessions), when `disableAllHooks`
or `allowManagedHooksOnly` is set, or when the built-in `agents-md` plugin is
disabled. These sessions are outside this repository's automatic-loading
support; use a supported session before relying on project instructions.

With the default setting, an ancestor or local `CLAUDE.md`,
`.claude/CLAUDE.md`, or `CLAUDE.local.md` takes precedence. If an existing
personal file must remain, select `claude-md-and-agents-md` in user-level
Project instructions and verify the loaded rules. Repository-local settings
cannot configure that choice. Existing explicit imports are deduplicated by
Claude; their removal here is a maintenance decision, not a claim that an
import necessarily loads rules twice.

## Validation

`scripts/check_repo_harness.py` validates instruction structure, required
shared constraints, references, and repository knowledge metadata without
rendering instruction bodies. It rejects tracked `CLAUDE.md` and
`CLAUDE.local.md` files, Markdown files under any `.claude/rules/` directory,
and stale generated-instruction markers. Untracked or ignored personal files
remain allowed under the user-level configuration described above.

Instruction links use repository-local paths or explicit `http`, `https`, or
`mailto` URLs. Host-specific file URLs, UNC paths, and other schemes are rejected;
remote URLs are not fetched during validation.
Use Markdown syntax for links and images; raw HTML navigation or resource
attributes are rejected. HTML formatting and comments remain allowed.
The Copilot entry point must contain a Markdown link resolving to the local
root `AGENTS.md`; a plain mention or external link does not establish that route.

`scripts/build_repo_knowledge_index.py` remains responsible for the generated
knowledge indexes, document inventory, and harness health snapshot. CI
regenerates the committed indexes and inventory and checks them for drift.
The optional, Git-ignored health snapshot is generated for local inspection and
CI summaries/artifacts; its absence or staleness does not fail validation.
See [harness health snapshots](../README.md#harness-health-snapshots) for refresh
and access instructions. These outputs describe repository facts rather than
maintaining a second copy of the instructions.

Run `python scripts/check_repo_harness.py` after instruction edits. When
documents or inventory inputs change, regenerate the knowledge outputs and
run the harness again. The repository-wide pre-commit gate remains required.

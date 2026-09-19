# Retire the AI Instruction Generator

## Purpose / Big Picture

Keep the layered `AGENTS.md` files as the instruction sources of truth. Remove
the Python instruction generator and redundant tool-specific routers while
preserving module-specific constraints and the small Copilot and Gemini entry
points needed for compatibility. Runtime application behavior is unchanged.

## Progress

- [x] 2026-09-19 06:12 UTC: Synced PR #2861 and inventoried instruction owners,
      generated files, compatibility entry points, and checker dependencies.
- [x] 2026-09-19 06:21 UTC: Simplified module instructions
      and removed the generator, routers, and superseded designs.
- [x] 2026-09-19 06:21 UTC: Removed obsolete generator checks and updated CI, hooks,
      shared instructions, canonical design, and generated knowledge indexes.
- [x] 2026-09-19 06:21 UTC: Passed repository gates;
      independent review confirmed all module constraints and skill references remain.
- [x] 2026-09-19 07:20 UTC: Separated new validation capabilities and their
      toolchain changes from the instruction-document cleanup.

## Surprises & Discoveries

- The generator rendered only the first three module invariants, even where
  its metadata declared more. The simplified instructions must preserve every
  metadata invariant as well as all currently rendered local constraints.
- Claude rule files have no path frontmatter and repeat shared instructions.
  Their explicit stop-on-missing-development-tools rule belongs in root guidance.
- The local Ruff version differs from the repository pin. Use an isolated
  temporary tool environment for verification without changing the global install.

## Decision Log

- 2026-09-19: Remove all 24 reviewed redundant files plus the instruction
  generator. Keep `GEMINI.md` linked to root `AGENTS.md` and one Copilot
  navigation file. The user authorized this scope after the redundancy review.
- 2026-09-19: Keep local module rules, targeted commands, and skill references;
  remove repeated parent guidance and arbitrary minimum line counts. Check
  required entry points and guardrails without regenerating instruction bodies.
- 2026-09-19: Keep the knowledge-index generator, architecture checks, and
  runtime configuration. These still derive useful facts or validate contracts.
- 2026-09-19: At the user's request, publish new instruction checks, tests,
  parser tooling, and removal of the old checker alias in a separate dependent
  PR. This plan covers the document cleanup and only the wiring required to
  stop invoking or importing the removed generator.

## Outcomes & Retrospective

Removed the instruction generator and redundant instruction files. The 25 module
instructions now contain 788 lines instead of 2234, preserving every local
constraint and restoring eight invariants omitted by the old renderer. Existing
checks for the root, backend, and frontend instruction entry points remain;
only knowledge indexes are regenerated.

The development-tool doctor and `lefthook run pre-commit --all-files` passed.
Independent review verified module metadata preservation and found no live
dependency on the retired generator. New instruction-validation regression
tests and parser dependencies belong to the separate validation PR.

## Context and Orientation

Before this change, `scripts/generate_ai_collab_docs.py` emitted 25 module
instruction files and 15 tool routers. `scripts/check_repo_harness.py` imported
its templates and required generated equality. CI regenerated those instruction
files; lefthook invoked the harness. Three superseded designs described older policies.
The canonical replacement is `docs/design-docs/ai-tool-compat.md`.

## Plan of Work

Simplify the 25 module documents, retaining all local rules.
Delete empty tool routing layers and consolidate the historical design decisions.
Remove generator dependencies from validation and automation. Preserve the
existing checks for shared rules and repository knowledge without introducing
new instruction-validation behavior in this PR.

## Concrete Steps

1. Update module files, shared entry points, and the canonical compatibility doc.
2. Remove retired files and update all live command references and CI steps.
3. Run `python3 scripts/build_repo_knowledge_index.py`.
4. Run the existing harness, architecture checks, and Ruff.
5. Run `python3 scripts/check_dev_tools.py` with the pinned toolchain and
   `lefthook run pre-commit --all-files`; inspect any auto-fixes before committing.
6. Update this plan and PR #2861 with the final implementation and verification.

## Validation and Acceptance

No instruction generator or redundant router remains. Module files retain their
local constraints without generated markers. The Copilot navigation file and
Gemini link still lead to shared instructions. Existing primary-entry-point
and repository knowledge checks run without importing generator templates.
Knowledge regeneration is deterministic and repository gates pass.

## Idempotence and Recovery

All edits are versioned on the existing PR branch. The former generator and
module metadata remain available from commit `f06c410`. Knowledge regeneration
is safe to rerun. Temporary verification environments are outside the repository.

## Interfaces and Dependencies

The existing harness remains a standard-library Python script and no longer
imports the retired generator.
CI keeps knowledge-index generation and the existing architecture, translation,
and runtime gates. Claude users need a version and session configuration that
supports native `AGENTS.md`; the compatibility document describes those requirements.

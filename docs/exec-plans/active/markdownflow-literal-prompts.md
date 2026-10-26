---
title: MarkdownFlow Literal Prompt Split
status: active
owner_surface: learner
last_reviewed: 2026-10-26
---

# MarkdownFlow Literal Prompt Split

## Purpose / Big Picture

Extract native 2.0 prompt substitution removal from PR #3181 into an independently
reviewable PR on current main. The durable contract is
[Literal Prompts](../../references/markdownflow-literal-prompts.md).

## Progress

- [x] 2026-10-26 CST: Keep recognized memory JSON fresh when authored sections are unmatched; preserve the entire unknown suffix. All 2,769 engine/envelope checks pass. Fix the independent variable-field fixture separately (38 reference checks).

- [x] 2026-10-26 CST: Restore historical Profile option contracts only for issued pending objects, including siblings and fresh-call rejection; 331 shared host/Profile regressions pass. Shared matcher extraction preserves the service boundary.

- [x] 2026-10-26 CST: Fix review finding for unset retired references; 128 reference/compatibility regressions pass.

- [x] 2026-10-26 CST: Fetch main and PR #3181; save local recovery branches.
- [x] 2026-10-26 CST: Create isolated managed worktree and copy local environment files.
- [x] 2026-10-26 CST: Separate literal prompt assembly and historical host refresh from field renaming.
- [x] 2026-10-26 CST: Verify 2,770 engine/compatibility checks and 127 focused prompt/Profile regressions; full pre-commit passes. Broad host/authoring regression readback remains in progress.
- [x] 2026-10-26 CST: Stack PR #3181 on this branch and update both descriptions; initial combined backend and frontend verification passes. Review fixes will be synchronized before final readback.
- [ ] 2026-10-26 CST: Read current-head CI and reviews after the five-minute review window.

## Surprises & Discoveries

The source PR head is `4d834bea2d6a255abc287073cbfaa29427eb46e4`; main advanced
to `8a055ce9a`. Prompt refresh, memory budgeting, Profile control comparisons and
verbatim completion anchors share the substitution behavior. Scanner ownership,
question validation and field renaming stay with the question-contract PR.

## Decision Log

- 2026-10-26: Use a stacked PR relationship. This PR targets main; #3181 targets
  this branch so shared changes are owned once and the remaining diff describes
  only the question contract, naming and authoring/preview migration.
- 2026-10-26: Keep existing field names and declaration eligibility in this PR.
  Historical rendering is private read-only matching, never new prompt assembly.

## Outcomes & Retrospective

Implementation and verification are in progress. No merge, auto-merge, package
publication or deployment is authorized by this plan.

## Context and Orientation

`markdownflow/engine/script.py` assembles model prompts; `engine.py` records the
initial snapshot and chooses verbatim anchors. The shared `flaskr/common/markdownflow_prompt.py` matcher (also exported through
the historical `learn/agent/legacy_prompt.py` path) recognizes historical native sections for deletion and nickname refresh.
Profile's authored-interaction checker must compare literal options.

## Plan of Work

Extract behavior under existing interfaces. Preserve fixed historical outputs
and original learner/tool history. Update runtime guidance and references.
Validate this branch first, then rebase the source PR onto it and audit the diff.

## Concrete Steps

Use the repository virtualenv with CI-pinned pydantic-ai 2.53.0 and markdown-flow
0.4.2 isolated under `/private/tmp` when needed. Run tests from `src/api`.
Generate documentation inventories with `scripts/build_repo_knowledge_index.py`.
Before commits run `scripts/check_dev_tools.py` and full pre-commit.

## Validation and Acceptance

Both branches must pass `tests/markdownflow/`, relevant learner/Profile and
shifu authoring/preview tests, repository harness and architecture checks. The
literal branch must retain old field names and no frontend/library-pin changes.
Combined runtime behavior must preserve the original PR's existing review fixes.
Read back current-head CI and effective review threads; report external blockers.

## Idempotence and Recovery

Recovery refs are `sunner/snapshot-3181-before-prompt-split-20261026` and
`sunner/snapshot-main-before-prompt-split-20261026`. Preserve the user's shared
checkout and original `cbbb` worktree. Use an explicit remote-head lease for any
source-branch history update. Never overwrite unrelated local changes.

## Interfaces and Dependencies

This PR has no new dependency or schema migration. It leaves the 1.0 SDK and
runtime untouched. PR #3181 retains markdown-flow-ui #261 and its existing
release-only gate; this independent branch uses main's release dependency pin.

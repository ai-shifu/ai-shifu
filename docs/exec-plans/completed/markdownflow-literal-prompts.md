---
title: MarkdownFlow Literal Prompt Sending
status: active
owner_surface: learner
last_reviewed: 2026-10-27
---

# MarkdownFlow Literal Prompt Sending

## Purpose / Big Picture

Narrow PR #3188 to stop server-side substitution before native model requests.
The approved contract is [literal prompts](../../references/markdownflow-literal-prompts.md).
Preserve memory and interaction protocols, and do not migrate existing sessions.
This scope supersedes the broader historical-normalization implementation.

## Progress

- [x] 2026-10-27 CST: Read live PR #3188 and main, preserve remote head `0f73a27b5` in a recovery branch, and restore superseded changes to main `e098392fe` before implementing the narrow contract.
- [x] 2026-10-27 CST: Separate request assembly, new-raw-session refresh and unchanged Profile protocol verification into independent file ownership.
- [x] 2026-10-27 CST: Verify 7,518 related backend cases (96 existing skips), including all 2,653 offline engine cases. Profile suite: 196 passed; focused refresh pack: 45 passed; gateway/memory pack: 33 passed. Development tools, full pre-commit, repository harness and architecture gates pass.
- [x] 2026-10-27 CST: Head `6032c2aba` passed all applicable CI and final live review readback with no open findings.
- [x] 2026-10-27 CST: Clarify that saved prompts remain as-is. Remove raw/expanded format detection and all script/brief rebuilding from nickname/deletion refresh.
- [x] 2026-10-27 CST: Verify the single memory-only refresh path: 7,514 related backend cases pass with 96 existing skips, including all offline engine cases. Full pre-commit passes.
- [x] 2026-10-27 CST: Push the simplification and follow the new head through CI and review. Closed at archival on 2026-10-29: #3188 is merged into main and deployed with it, so this review, merge or rollout step no longer applies.

## Surprises & Discoveries

The model may still interpret references using memory. Keeping the existing Profile
machine-value validator avoids introducing a second interaction protocol. Existing
sessions already contain expanded prompt history; the approved scope preserves it.
The initial simplification still maintained dynamic rebuilding for old expanded
prompts. That extra requirement was not approved: saved text can simply remain as-is,
so both refresh helpers now update only the independent memory envelope.

## Decision Log

- 2026-10-27: Stop interpolation for new script/brief request bodies. Keep memory budgets, referenced-key priority, public substitution helpers, snapshots and storage names unchanged.
- 2026-10-27: Supersede the former raw/expanded refresh split. Preserve saved script/brief/extra text and substitution snapshots as-is for every session; update only memory. Remove obsolete brief-rebuild arguments at all callers. Do not detect formats or maintain historical interpolation.
- 2026-10-27: Retain Profile option values, completion anchors and answer-reference fallbacks. Test the existing protocol rather than changing it.
- 2026-10-27: Work only in the attached literal-prompts worktree. Do not rewrite #3181 or the shared/cbbb checkouts, merge main, enable auto-merge, publish packages or deploy.

## Outcomes & Retrospective

The previous head completed local and remote validation. The follow-up removes the
remaining prompt-rebuild machinery instead of branching around it. Production changes
are confined to prompt assembly, syntax guidance and memory refresh with its caller.
Profile runtime, memory policy, public interfaces and stored-session schema match
main. Current-head remote CI and review readback remain tracked in PR #3188. The
previous broad implementation is recoverable but is no longer the approved contract.

## Context and Orientation

`markdownflow/engine/script.py` composes the initial memory/script/brief envelope;
its syntax guidance explains memory references. Learner nickname/deletion helpers
refresh only saved initial memory, preserving the complete authored-text suffix. Profile's
existing validator resolves authored machine values and must remain unchanged.

## Plan of Work

Send source text in new prompts, synchronize obsolete model guidance, and remove
authored-text rebuilding from memory refresh. Restore unrelated source/test changes to main.
Use focused request and host regressions, then the complete offline engine and
related backend suites. Follow effective review and current-head CI until terminal.

## Concrete Steps

Use the repository virtualenv with CI-pinned pydantic-ai 2.53.0 and markdown-flow
0.4.2. Run tests from `src/api`, regenerate knowledge indexes and run dev-tool,
harness, architecture and full pre-commit checks before committing. Push to the
existing literal-prompts branch with an explicit expected remote head.

## Validation and Acceptance

New script/brief/extra bodies reach the model unchanged. Memory filtering, priority,
limits and Profile machine values remain unchanged. Nickname and deletion refresh
preserve every stored script/brief/extra suffix without format checks. Expanded-session
history and pending choices remain readable without recomputation or migration. The complete offline engine and relevant hosts
pass, then all applicable current-head CI checks reach terminal states and no new
in-scope review remains unhandled. No main merge is authorized.

## Idempotence and Recovery

`sunner/snapshot-3188-before-minimal-20261027` records the previous remote head.
The working branch uses a normal follow-up commit so previous review evidence
remains traceable. Stop a push if the remote changed unexpectedly. Preserve the
shared source checkout and original cbbb worktree.

## Interfaces and Dependencies

No new dependencies, schema fields, feature flags or wire contracts. PR #3181 is
separate work and is not updated by this task. Its dependency/base synchronization
must be handled with that PR's own migration work.

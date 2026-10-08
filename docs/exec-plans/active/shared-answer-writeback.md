---
title: Write explicit named answers back to same-owner course variables
status: active
owner_surface: learner
last_reviewed: 2026-10-08
---

# Write explicit named answers back to same-owner course variables

## Purpose / Big Picture

Let an author explicitly collect a fresh answer for an existing variable in another
course they own, without copying values or weakening read-only `course:` references.
The durable contract is [Shared answers](../../references/shared-course-answers.md).
This is the first shared-writing increment; model notes and owner-wide storage are
separate work.

## Progress

- [x] 2026-10-08 05:24 UTC: Inspect current same-owner reads, author declarations,
  memory admission, original-answer persistence and deletion/version boundaries.
- [x] 2026-10-08 05:29 UTC: Implement explicit named-answer grants, source reads,
  transaction-owned writes and fresh authority/source-version revalidation.
- [x] 2026-10-08 05:40 UTC: Full learning/profile suite passed (2791 passed,
  1 skipped, 4 subtests) before the final two authoring/cap cases. Real local MySQL
  repeatable-read and concurrent/opposing-writer tests: 7 passed. Mutations of source
  versions, locking current reads and host grants fail 2 / 5 / 2 cases; restore bytes.
  Local deployed-module probe passes 135 isolated checks and 23 runtime hashes
  without provider calls or shared writes.
- [x] 2026-10-08 05:43 UTC: Final full learning/profile suite including local
  MySQL: 2800 passed, 1 skipped, 4 subtests; 39 standard and 7 opt-in MySQL cases
  added. Developer tools, architecture and all repository gates passed.
- [ ] 2026-10-08 05:32 UTC: Publish a focused non-draft PR, synchronize exact tree
  to sim, verify replicas and real provider behavior, and reply to every AI opinion.
- [ ] 2026-10-08 05:32 UTC: Final-head CI and sim acceptance before manual merge.

## Surprises & Discoveries

The memory facade intentionally refuses cross-course assignments. A named answer
needs a separate host-owned path inside the session save transaction, never a
model tool that can choose arbitrary storage scope. Read-only namespaces must
also be excluded from supplementary local-memory rows to prevent shadowing.

## Decision Log

- 2026-10-08: Continue approved same-owner explicit sharing with a narrow first
  writer: `%{{share:SOURCE_COURSE_ID:key}}` in the current published main lesson.
  Keep `course:` read-only; ordinary `remember` and settings cannot write aliases.
- 2026-10-08: Require live source/destination definitions, agreeing current and
  published nonempty owners, and an existing live value for this learner. Refuse
  deleted/missing values and changed source versions; do not restore or create them.
- 2026-10-08: Capture grants before model work; at persistence lock and recheck
  authority and exact source version. Acquire course-owner locks in sorted order.
  Share source updates and session persistence in one unit of work. No model I/O
  happens while these persistence locks are held.
- 2026-10-08: Preview/debug and regenerated-input replay cannot write shared values.
  Fresh answers after rewind may update a currently eligible source. Rejected
  assignments retain complete classroom answers but are removed from current memory.

## Outcomes & Retrospective

Local validation passes for exact source writeback, authority/version changes,
rollback, rewind/replay and preview. MySQL confirms fresh locking reads and
concurrent writers, and negative mutations prove the key guards. Final developer tools, architecture and all repository gates passed. Publication
and sim acceptance remain pending. No PR or deployment yet. This does not
complete cross-course model notes, owner-scoped storage or the memory milestone.

## Context and Orientation

`profile/shared_answers.py` owns pure snapshot resolution and transaction-local
staging through the existing profile writer. The profile reader exposes explicit
published aliases; normal profile writes and supplemental local rows exclude them.
`run_agent.py` captures grants, passes a pure per-turn answer-key set to Engine,
and stages interaction-sourced values inside session persistence. Engine keeps
model `remember` refusal and original answer history; portable defaults remain.

## Plan of Work

Validate real publication/ownership and source versions, engine/host lifecycle,
rollback and rewind; publish one focused PR, synchronize sim and collect isolated
replica and real-provider evidence. Audit reviews, inline and ordinary comments
and reply to each independent opinion. Main merge is manual.

## Concrete Steps

Run new shared-answer tests and nearby references/admission/factory tests, then
all learning/profile tests including vendored engine tests. Negatively remove
grants, source-version checking and transaction coupling to demonstrate coverage.
Stage new docs/prompts before generating repository indexes; run developer-tool
checks, architecture boundaries and the full pre-commit gate before publication.

## Validation and Acceptance

A fresh authored answer updates only the original source variable for the same
learner. Unicode/long answers and original classroom messages remain intact.
No scope/global/system/owner leak, draft-only authorization, local shadowing,
deleted-value resurrection or in-flight overwrite is allowed. Failed session
saves roll back shared values. Preview/replay cannot mutate sources. Old reads
remain read-only; source updates refresh before a later request. Existing source
course memory controls view/delete the value. Sim remains 2.0 and production 1.0.

## Idempotence and Recovery

Do not migrate or duplicate values. Recompute grants each request and revalidate
before writes. An identical accepted answer reuses the existing profile version.
Missing/changed authority or source versions refuse only that assignment; saved
answer history remains evidence. Reverting this increment removes shared writing
while retaining original source data and session history.

## Interfaces and Dependencies

Add `Engine.run_turn(memory_answer_keys=frozenset())` and matching per-run deps.
This allows named answers only; it does not grant `remember` access. Profile API
exports bounded shared snapshot/read/stage helpers and the reserved `share:`
prefix. No new database table, environment variable, dependency or SSE shape.

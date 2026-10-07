---
title: Course Memory Management
status: active
owner_surface: learner
last_reviewed: 2026-10-07
---

# Course Memory Management

## Purpose / Big Picture

Give learners control over persistent course memory. The canonical behavior and
analytics contract live in [the product spec](../../product-specs/course-memory-management.md).

## Progress

- [x] 2026-10-07 CST: Confirmed #3029 merged and the user selected continuation
  of the recommended view-and-delete scope. Inspected persistence and UI owners.
- [x] 2026-10-07 CST: Implement scoped list/delete and deletion-safe agent persistence.
- [x] 2026-10-07 CST: Add learner UI, translations, analytics and regression tests.
- [x] 2026-10-07 CST: Run local gates and open PR #3030.
- [x] 2026-10-07 CST: Fix review findings: URL serialization, replayed consent,
  legacy in-flight writes and omitted original script substitutions.
- [ ] 2026-10-07 CST: Validate the final sim revision and reply to AI reviews.

## Surprises & Discoveries

Values append historical rows, and active sessions retain an initial snapshot.
Deleting only the newest row would expose older values; updating storage alone
would leave resumed lessons using the old snapshot. Existing deleted rows can
hold an empty appended generation marker without introducing a schema migration.
Appending is required because legacy retired rows may have larger IDs than
the current live value; toggling flags alone would not always advance a generation.

## Decision Log

- 2026-10-07: Manage current-course custom variables; retain classroom history
  and canonical account settings. A later accepted input may recreate memory.

## Outcomes & Retrospective

Deleted declared keys also require a new explicit current-turn request or a new
named answer; restoring deferred consent and regeneration replay cannot recreate them.
Disabling the host deletion-generation guard made the actual-host regression fail.
Local learning/profile coverage passed 2433 tests plus two focused regeneration cases (one skipped, four subtests).
The five relevant frontend suites passed 52 tests. Full TypeScript checking reports
two pre-existing errors in unchanged admin user-detail tests (lines 964 and 1026);
no new errors are reported. Production Next.js build and all repository gates
passed. A repeated 2435-case run had one gevent concurrency failure while the
production build ran; the isolated gevent rerun passed in 0.85 seconds.
Review fixes passed the complete learning/profile suite: 2443 passed, one skipped,
four subtests. The three changed frontend suites passed 27 tests, including
query serialization and pagination/deletion exclusion. All repository gates passed.
Initial sim HTTP acceptance passed isolation, deletion, history/profile preservation,
idempotence and fresh explicit recreation. Final deployed revision acceptance is pending.

## Context and Orientation

`learn/memory` adapts profile variables; `agent/run_agent.py` loads and commits
turns. `route/user.py` owns authenticated learner routes. `MainMenuModal` is the
shared user menu, and `Settings` holds learner dialogs.

## Plan of Work

Add pagination and version-checked deletion, serialize deletion with agent writes,
refresh deleted host snapshot values on resume, then expose and test the dialog.

## Concrete Steps

Use conda `ai-shifu` for backend tests. Run targeted memory/agent and frontend
tests, the full learning/profile suite, type checks and repository pre-commit.
Stage source docs and regenerate the knowledge index before the final gate.

## Validation and Acceptance

Prove tenant/course isolation, complete pagination, no historical fallback,
idempotence/conflicts, transaction rollback, stale-turn suppression, deliberate
recreation, resumed prompt cleanup, retained answers and preview compatibility.
Verify UI request failures, confirmation loading, repeated clicks and analytics.
Sim writes use only fresh temporary learners in the fixed internal test course.

## Idempotence and Recovery

Deletion is idempotent. Failed writes roll back together; no migration or
configuration changes are needed. Source changes can be reverted normally.

## Interfaces and Dependencies

Authenticated GET/POST `/api/user/course-memory` use the shared response envelope
and request transport. Existing profile rows remain. Session JSON adds an optional initial substitution
snapshot, limited to referenced host variables; older sessions still load.
The 1.0 runtime captures deletion generations before validation, then stages
memory and progress in one unit of work before emitting variable events.
Replayed agent input cannot authorize restoration of a deleted key.

# Lesson content revision tracking with one nullable column

## Purpose / Big Picture

Simplify PR #3112 to compare lesson content revisions for formal and preview 2.0
attempts. Store current revisions in existing structure JSON and add only the
nullable session baseline column. Preserve the frontend boolean, retake
interaction and analytics contracts in
[Lesson Content Update Recommendations](../../product-specs/lesson-content-updates.md).

## Progress

- [x] 2026-10-12 CST: User approved reusing revisions and retaining a notice
  after text reversion. Selected one nullable column and conservative unknown
  baselines to simplify the implementation.
- [x] 2026-10-12 CST: Updated the existing product contract and this plan for
  the simplified implementation.
- [x] 2026-10-12 CST: Implemented authoring revision metadata, nullable
  baseline migration, capture with the first saved learning messages and scalar
  comparisons.
- [x] 2026-10-12 CST: Verified authoring, publication, learning lifecycle,
  migration compatibility and frontend contract regressions.
- [x] 2026-10-12 CST: Passed repository gates and prepared the simplified
  implementation and verification description for PR #3112.
- [x] 2026-10-12 CST: Clarified review terminology: lesson content means the
  MarkdownFlow script; a learning attempt records its baseline with its first
  saved messages. Aligned the model, migration and product documentation.
- [x] 2026-10-12 CST: Completed the changed `_resolve` return contract in the
  memory-evaluation CLI and remaining course-usage/evaluation test doubles.
- [ ] 2026-10-12 CST: Verify migration/deployment order and formal/preview
  behavior after release.

## Surprises & Discoveries

- Comparing lesson content extracted from session LONGTEXT still parses
  conversation history in the database. Revision metadata removes that work
  from detection and avoids maintaining JSON extraction and database-version branches.
- Missing historical revision metadata cannot establish what an existing
  learner originally studied. Old session baselines must stay `NULL`.
- Clearing a draft previously allowed history/reset to reach formal learning.
  Keep the scoped lifecycle safeguards while simplifying detection.
- Historical cleanup can cross a deleted intermediate content version and find
  earlier identical content. Protect the structure's recorded revision explicitly
  so reverting text still keeps its new version.
- Initializing legacy revision metadata during publish is a draft write. Use
  the existing course lock and current-read structure to avoid overwriting a
  concurrent edit.

## Decision Log

- Current revision belongs to `HistoryItem.content_revision` in existing
  structure JSON; only `LearnAgentSession.content_revision` adds a column.
- Save/publish paths establish missing structure revisions with the existing
  draft content revision calculation. Reads do not guess or backfill them.
- Capture the baseline with a new learning attempt's first saved messages.
  Use `0` for a started attempt with an unknown source revision; existing
  sessions retain `NULL`. Both unknown states suppress recommendations.
- Changed lesson content advances the revision even if a later edit restores
  its old text. Title/settings edits and republishing unchanged content retain
  the revision.
- Resume/follow-up/history reads preserve the baseline. Reset retires only the
  selected course/lesson/scope; the next attempt establishes its own baseline.
- Compare known positive revisions without parsing session JSON. Runtime
  deserialization errors remain on the existing session loading path; preview
  status retains the legacy `turn`/`finished` fallback.
- Treat an engine document ID change as a new attempt when existing loader
  compatibility handling restarts an unusable session; preserve the baseline
  on all same-ID continuations, including legacy NULL sessions.
- Keep frontend fields, missing-field behavior and analytics unchanged.
  Engine routing and the existing scriptless 1.0 execution fallback are outside
  this change.

## Outcomes & Retrospective

The revision replacement is implemented. Related backend learning, authoring,
API, adapter, golden and migration tests passed: 4,384 passed, 96 skipped.
Four frontend notice/history/retake suites passed 135 tests. Frontend lint
passed with existing warnings; type-check still reports the same two pre-existing
admin users test errors at lines 964 and 1026, previously reproduced on the
clean base with identical locked dependencies.

Eight isolated MySQL/SQLite benchmark scenarios use the existing active-key
index and one scalar query. Local MySQL 100 x 1 MiB sessions measured 4.45/4.83 ms
p50/sample p95; see the [measurement boundaries and migration verification](../../references/lesson-content-update-performance.md).
Tooling doctor, repository harness, architecture/UOW gates and all-files
pre-commit passed. The actual Alembic migration passed SQLite regression tests and isolated local
MySQL upgrade/NULL preservation/new-value/downgrade verification. No configured
development database was migrated and no deployment is claimed.

The terminology follow-up passed 76 migration, session-persistence and content
update tests. Backend CI then exposed remaining three-value `_resolve` test
doubles in `tests/test_llm.py`. The same return-contract audit found the
memory-evaluation CLI and its test double; these now accept the content revision
as the fourth value. All 83 focused course-usage and memory-evaluation tests
passed, including the 12 previously failing CI cases.

## Context and Orientation

Authoring history and publishing own the structure's content revision.
`agent/session_store.py` owns the persisted attempt baseline. Learning
history/directory helpers expose the comparison, and `active_key_for`
separates formal and preview sessions. The frontend already consumes the
records boolean and emits the two documented retake events.

## Plan of Work

Update authoring/publication revision propagation and add the nullable session
column. Capture it with the first saved learning messages, replace content
parsing with scalar revision comparison, retain scoped history/reset behavior,
and remove the superseded comparison branches. Verify the changed contracts before updating
PR #3112 and planning rollout.

## Concrete Steps

Use the repository's existing migration and unit-of-work workflows. Run
focused authoring, publication, session persistence and lesson update tests,
then related learn/API regressions. Recheck the frontend notice, scope-switch,
reset and analytics suites; run type-check and lint with locked dependencies.
Regenerate knowledge indexes after documentation settles. Run the tooling
doctor, harness, architecture, UOW ratchet and all-files pre-commit gates
before committing. Record actual outcomes here after they complete.

## Validation and Acceptance

- Lesson content changes advance revisions; settings-only changes and identical
  republication preserve them. A change followed by text restoration remains
  a revision change.
- The first saved learning messages record the baseline; preview reservation
  does not.
  Resume, follow-up and history reads never replace it. Old `NULL`, new
  unknown `0` and missing current metadata never prompt a retake.
- Directory and records agree for in-progress/completed attempts, use current
  structure revisions, and keep formal/preview histories and resets isolated,
  including cleared draft content and repeated retakes.
- Existing structure JSON loads without the optional field. Migration adds
  exactly one nullable baseline column without historical backfill. Detection
  needs neither stored-message parsing nor historical content transfer.
- Frontend absent-field behavior, late-response protection and the existing
  retake analytics contract remain covered. Earlier JSON-comparison benchmark
  numbers are not acceptance evidence for the new path.

## Idempotence and Recovery

Never backfill old session baselines with a current revision. Repeating a
title/settings save or unchanged publication must not manufacture updates. Apply
the additive migration before code that uses it. Application rollback can
retain the nullable column and optional structure metadata; remove neither
while deployed code depends on it. Keep test data isolated from development
or production learning records.

## Interfaces and Dependencies

The public boolean contracts remain unchanged. `HistoryItem` gains optional
revision metadata in its existing JSON, and `LearnAgentSession` gains one
nullable `BIGINT` baseline. No new revision table, digest, cache, dependency
version or frontend payload is required.

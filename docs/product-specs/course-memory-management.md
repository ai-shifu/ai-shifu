---
title: Course Memory Management
status: implemented
owner_surface: learner
last_reviewed: 2026-10-07
canonical: true
---

# Course Memory Management

Learners can inspect and individually delete their persistent custom variables
in the current course from the learner user menu. Guest sessions are eligible;
teacher/admin and preview surfaces are excluded. Account fields remain managed
by personal settings. No other learner, global scope, or other course is exposed.
The list includes stored values even when the prompt budget omits them. It is
paginated rather than silently capped, and displays values as plain text.

Deletion invalidates every stored version of the selected course key and appends
an empty deleted generation marker, preventing
an older value from resurfacing. A stale list cannot delete a newer value: the
client supplies the current value's opaque record version identifier and reloads after a
conflict. Missing/already-deleted values are idempotent successes. Later accepted
answers or explicit requests may remember the key again. A script declaration
alone cannot recreate a deleted value; restored/deferred earlier consent is not
a new request. Regeneration replay cannot restore an old named answer. Writes from turns that
started before deletion cannot resurrect it. Course memory deletion and agent
persistence lock the same course rows, without holding locks during model calls.

On the next turn, deleted keys are removed from session memory and the known
host-authored initial memory/script sections when the original rendering can be
recognized safely. Unrecognized legacy sections remain classroom history.
Conversation messages, original
answers, progress, and historical tool results remain available as classroom
history; this is deletion of persistent course memory, not erasure of all past
conversation. The interface explains this before confirmation. Account settings,
other courses, and preview data are unaffected. There is no schema migration.

## Analytics contract

- Business question: do learners inspect course memory and successfully remove it?
- Metric: weekly distinct learners opening the manager, and successful deletion
  results / deletion attempts; delivery is best-effort, not an audit source.
- Events: `learner_course_memory_opened`, `learner_course_memory_delete_attempt`,
  `learner_course_memory_delete_result`.
- Trigger: first committed open per dialog lifecycle; accepted confirmed delete;
  confirmed API success or terminal failure, respectively.
- Population: learner members and guests in a course, excluding preview/admin.
- Count unit: dialog open or delete attempt. Single-flight guards suppress repeats.
- Deduplication: component lifecycle open flag and synchronous pending ref.
- Correlation: course opaque record version identifier only; no memory identifier, key, value,
  free text, raw error, profile data, token, or URL is collected. Aggregate ratios
  do not promise exact per-attempt joins.
- Consumers: product adoption analysis; no existing dashboards require migration.
- Compatibility: additive new event family, no backfill or legacy dual write.
- Verification: UI tests cover population, timing, retries, pending state,
  repeated clicks, privacy allowlist, stale results, and tracking failure isolation.

| Field | Type | Allowed values | Cardinality | Privacy | Purpose |
| --- | --- | --- | --- | --- | --- |
| course_id | string | current course business ID | high | pseudonymous | course adoption |
| outcome | string | success / failed; result only | low | non-personal | completion ratio |

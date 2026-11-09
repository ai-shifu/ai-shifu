---
title: Course Memory Management
status: implemented
owner_surface: learner
last_reviewed: 2026-11-08
canonical: true
---

# Course Memory Management

Learners can inspect and individually delete their persistent course memory entries
in the current course from the learner user menu. Published learning supports
member and guest sessions. The manager also appears in the full-course preview
menu and reads or deletes the current account's own course memory across both
versions. Draft content access is authorized separately. Editor Debug uses its own
simulated memory. Account fields remain managed by personal settings. The list contains
only the current user's custom values for the current course, including values
omitted by the prompt budget. It is paginated and displays values as plain text.

The overall feature is "Memory"; "Course memory" names the learner's course-scoped
collection. Keep that scoped label and the existing deletion-scope explanation.
Entries use a question-and-answer structure backed by their existing keys and
values. They may include saved answers and information the learner explicitly
asked to remember. Show existing keys and values without rewriting keys as
questions or presenting every entry as an original learner answer. The display
structure does not establish a question, answer provenance or answer count for
every entry. This naming and structure change neither the mixed collection nor
its admission, exact-key matching, overwrite, scope or deletion rules.

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
conversation. The interface explains this before confirmation. Deleting a
course memory applies to both published learning and full-course preview.
Account settings and other courses are unaffected. There is no schema migration.

## Analytics contract

- Business question: do users inspect and remove course memory in published
  learning and full-course preview? Compare adoption separately to see whether
  users managing memory while testing a draft encounter more deletion failures.
- Metric: weekly distinct users opening the manager and successful deletion
  results divided by deletion attempts, grouped by course and event family.
- Published learning events: `learner_course_memory_opened`,
  `learner_course_memory_delete_attempt`, `learner_course_memory_delete_result`.
- Full-course preview events: `teacher_preview_course_memory_opened`,
  `teacher_preview_course_memory_delete_attempt`,
  `teacher_preview_course_memory_delete_result`.
- Trigger: first committed open per dialog lifecycle, accepted confirmed delete,
  and confirmed API success or terminal failure (including stale version
  conflict), respectively. Opening or dismissing confirmation emits no delete
  event. Pending responses after unmount or identity replacement emit no result.
- Population: members and guests in published learning, and users opening
  the manager from the full-course preview menu. Teacher/admin menus and editor Debug are excluded.
  Delivery follows shared account-level analytics exclusions.
- Deduplication: one event per dialog mount and one attempt with at most one
  result per confirmed deletion. Single-flight guards suppress repeated clicks
  while pending. Reopening the dialog or explicitly retrying counts separately.
- Payload: only the course ID and the outcome where applicable. Do not include
  memory identifiers, keys, values, course content, free text, raw errors,
  profile data, tokens, or URLs. Aggregate ratios are best-effort.
- Consumers and compatibility: product adoption analysis uses the same learner
  event series and the additive preview series separately. No backfill, dual
  write, or consumer migration.
- Verification: UI tests cover population, timing, retries, pending state,
  repeated clicks, exact allowlisted payloads, stale results, and continued use
  when analytics throws or rejects.

| Field | Type | Allowed values | Cardinality | Privacy | Purpose |
| --- | --- | --- | --- | --- | --- |
| course_id | string | current course business ID | high | pseudonymous | course adoption |
| outcome | string | success / failed; result only | low | non-personal | completion ratio |

New sessions retain the original values used for host script/constraints
substitutions, including values omitted from the budgeted memory JSON. Deletion
can therefore refresh those host sections after a value has changed. Legacy
sessions without this snapshot keep the conservative matching fallback. Both
1.0 and 2.0 persistence reject updates whose deletion generation changed while
processing. The 1.0 runtime emits variable update events only after persistence
succeeds.

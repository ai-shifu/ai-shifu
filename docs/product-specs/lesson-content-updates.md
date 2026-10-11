---
title: Lesson Content Update Recommendations
status: implemented
owner_surface: shared
last_reviewed: 2026-10-11
canonical: true
---

# Lesson Content Update Recommendations

A started or completed MarkdownFlow 2.0 lesson recommends a retake only when
its current authored body differs from the original body retained in its live
learning session. Published learning compares the current publication; teacher
preview compares the current draft. CRLF and standalone CR normalize to LF;
all other text, including case, whitespace and Markdown, remains significant.
Equal-length edits count. Reverting to the original body removes the notice.

Titles, ordering, models, audio settings, course/teaching briefs and follow-up
configuration do not participate. Continuing, asking a follow-up question or
reading history does not advance the original body baseline. Retaking starts
a new scoped session. Formal learning and preview do not read or retire each
other's baselines, including when a draft body has been cleared.

Only a correctly scoped, active session with a recognized schema, string body
and nonempty message array establishes a baseline. Formal learning additionally
requires current in-progress or completed progress. Missing, malformed,
unrecognized, unstarted and reset sessions, and legacy 1.0 records, do not
produce a recommendation. Unknown is not proof of unchanged content; it simply
does not justify a retake notice. Never infer a baseline from timestamps or
backfill one with the current body.

## API and storage contract

The outline tree retains `has_content_update_for_current_user`. The lesson
records response adds the same boolean, defaulting to false. The browser uses
the records response for both scopes and treats an absent field as false,
without falling back to timestamps or an older outline response.

Directory evaluation uses the existing active-session key index and the
physical outline row IDs named by the current structure. It batches eligible
lessons and projects only identifiers and state booleans, never complete
session JSON, message history or historical body text. SQL comparisons use
binary semantics after newline normalization and guard invalid JSON and
unexpected JSON types. Preview history reuses its already decoded document;
the equivalent in-memory predicate is covered by the same comparison cases.

There are no new database columns, indexes, migrations, fingerprints or caches.
Extracting values from the existing LONGTEXT JSON still costs database reads
and parsing. Small result sets do not imply small physical reads; benchmark
results must distinguish these costs and identify synthetic fixtures.
See the [measurement report](../references/lesson-content-update-performance.md)
for reproducible fixtures, execution plans and the database-CPU tradeoff.

## Retake analytics contract

This additive event family follows [frontend product analytics](../references/frontend-product-analytics.md).

- Business question: How often is a recommended retake accepted, and how often
  does the operation succeed, separately for learners and teacher previews?
- Metrics: Weekly raw accepted-attempt counts and the success/failed share of
  terminal results, grouped by course and surface. Best-effort event delivery
  does not support billing, audit counts or exact attempt-to-result joins.
- Events: `lesson_update_retake_attempt` and `lesson_update_retake_result`.
- Trigger: Attempt is emitted after a valid confirmation passes the existing
  single-flight guard, immediately before stopping the stream and resetting.
  Result is emitted once after the operation resolves or rejects.
- Population: Formal learners, including guests with access, and authorized
  teacher previews. Missing course/lesson identifiers, disabled or reentrant
  operations and cancellation before confirmation are excluded. Test traffic
  is excluded by the deployment's normal analytics configuration.
- Count unit and deduplication: One accepted operation; the single-flight guard
  prevents repeated confirmation from creating concurrent attempts. At most
  one terminal result is emitted for each accepted operation.
- Correlation: Course and outline business identifiers only; no attempt ID or
  additional user identifier. Aggregate weekly results may cross time windows.
- Consumer: The course team's weekly Umami usage/outcome queries grouped by
  `shifu_bid` and `surface`, using the exact new event names. Existing reset
  event queries remain unchanged and are not combined with this family.
- Compatibility: Additive events; no renamed event, historical backfill or
  changes to legacy reset-event eligibility.
- Failure isolation: Synchronous tracking errors and asynchronous rejections
  do not block, delay, fail or change the retake operation.

| Field | Type | Allowed values | Cardinality / privacy | Purpose |
| --- | --- | --- | --- | --- |
| `shifu_bid` | string | Stable course business identifier | High / pseudonymous | Course grouping |
| `outline_bid` | string | Stable lesson business identifier | High / pseudonymous | Lesson grouping |
| `surface` | string | `published_learning`, `teacher_preview` | Low / non-personal | Separate populations |
| `outcome` | string | `success`, `failed`; result event only | Low / non-personal | Terminal outcome |

No body, title, content fingerprint, profile, URL, token or raw error is sent.
Tests assert exact events/payloads, eligibility, timing, duplicate protection,
terminal outcomes and continued retake behavior under tracking failure.

## Delivery

Deploy the additive backend response before the frontend consumer. Old clients
keep the outline contract; new clients hide the notice on older responses.
Rollback is code-only. Engine routing and 1.0 storage remain unchanged.

---
title: Lesson Content Update Recommendations
status: implemented
owner_surface: shared
last_reviewed: 2026-10-11
canonical: true
---

# Lesson Content Update Recommendations

A started or completed MarkdownFlow 2.0 lesson recommends a retake when its
current body revision differs from the revision recorded when that learning
attempt first taught content. Published learning uses the published revision;
teacher preview uses the draft revision.

Saving a changed body advances its revision. CRLF, CR and LF are treated as
equivalent line endings; other whitespace, case and Markdown edits count.
Titles, ordering, models, audio
settings, course/teaching briefs and follow-up configuration do not advance
it. Publishing carries the draft body's revision into the published structure;
republishing unchanged content does not itself count as a body update.
Changing a body and later restoring its original text still advances the
revision and can keep the retake recommendation visible. The recommendation
means the lesson was revised since this attempt began, not that its present
text necessarily differs from the originally taught text.

Continuing, asking a follow-up question or reading history never advances the
attempt's baseline. Retaking retires that scoped session; its replacement
records a new baseline when teaching actually begins. Formal learning and
preview do not read or retire each other's baselines, including when a draft
body has been cleared.

## Revision and API contract

- `HistoryItem.content_revision` stores the body revision in existing draft and
  published structure JSON. Authoring save/publish paths establish missing
  metadata using the existing draft body-revision calculation. Read paths do
  not reconstruct a revision from timestamps, physical row IDs or session JSON.
- The only new database column is nullable `BIGINT`
  `LearnAgentSession.content_revision`. A new attempt records its baseline at
  its first actual teaching persistence, never when merely reserving a preview
  session. A positive value is a known baseline; `0` means teaching started
  while the source revision was unknown. Existing sessions retain `NULL` and
  are never backfilled, including when they resume.
- A notice requires an active, correctly scoped session, known positive
  current and baseline revisions, and unequal revisions. Formal learning also
  requires current in-progress or completed progress. Unknown revisions,
  legacy 1.0 records and reset/unstarted attempts do not produce a notice.
  Existing preview progress display retains its `turn`/`finished` fallback.
- If existing runtime compatibility handling starts a new engine session,
  its new document ID establishes a new attempt and baseline. Resuming the
  same engine session preserves even an unknown legacy baseline.
- Detection reads revision metadata and scalar session fields; it does not
  parse or compare the stored lesson body or message history. Session JSON
  validity is no longer a detection condition. Unusable stored conversations
  remain the responsibility of the existing session loading/error path.
- The outline tree retains `has_content_update_for_current_user`; lesson
  records return the same boolean, defaulting to false. The browser uses the
  records result for both scopes and treats an absent field as false, without
  falling back to timestamps or an older outline response.

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

Apply the additive nullable-column migration before deploying the backend,
then deploy the frontend consumer. Existing structure JSON remains readable
when revision metadata is absent; missing metadata produces no notice until
write paths establish it. Existing session baselines remain unknown.

Old clients retain the outline boolean contract; new clients hide the notice
on older records responses. An application rollback can leave the nullable
column and optional JSON metadata in place. Do not remove the column while
running code still reads or writes it. Engine routing and 1.0 storage remain
unchanged; preview history/reset isolation does not redefine the existing
scriptless 1.0 execution fallback.

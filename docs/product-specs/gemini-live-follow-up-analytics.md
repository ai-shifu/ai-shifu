---
title: Embedded Gemini Live Follow-Up Analytics
status: implemented
owner_surface: frontend
last_reviewed: 2026-09-04
canonical: true
---

# Embedded Gemini Live Follow-Up Analytics

This is the v2 product contract for Live input in the existing AskBlock. Follow
[the shared privacy and delivery rules](../references/frontend-product-analytics.md).
Umami is best-effort product telemetry, never billing, authorization, or audit.

## Decision and consumers

Product analytics compares keyboard adoption, deliberate microphone adoption,
and connection reliability in UTC daily and rolling seven-day windows. The
consumer is aggregate adoption/outcome reporting, not a row-level funnel.
There is no dedicated deployed dashboard or query implementation in this
repository; external/ad-hoc consumers must use the following definitions:

- Keyboard use: count accepted `learner_voice_follow_up_text_submit` events,
  grouped by `submission_method` and `interrupted`.
- Microphone use: count `learner_voice_follow_up_microphone_result` where
  `enabled=true`, grouped by `outcome` and `error_code`. Count successful off
  operations separately; implicit cleanup is not a deliberate off operation.
- Connection outcome: count `learner_voice_follow_up_result` by `outcome` over
  accepted `learner_voice_follow_up_attempt` counts in the same time window.
- Observed exchange share: session-end counts with `had_exchange=true` divided
  by all `learner_voice_follow_up_session_end` counts in that window; report
  `duration_ms` and `end_reason` alongside it.

These are raw event counts and aggregate ratios, not distinct users or sessions.
Best-effort delivery and window boundaries can produce unmatched records. No
attempt/session ID is collected, so exact conversion joins and attribution of
an exchange to one input method are not supported. Grouping by course, lesson,
mode, and surface uses only the IDs/enums below.

## Population, triggers, and deduplication

Formal guest and member learners in reading/listening are eligible. Teacher
preview and classroom are excluded. Capture originating dimensions per
operation; navigation cannot reclassify preview activity as learner activity.
Panel opening, disabled controls, invalid/empty/over-limit input, capacity
cooldown, re-renders, duplicate pending sends, and duplicate microphone requests
emit nothing. Later deliberate submissions/operations count again.

| Event | Exact trigger | Additional fields beyond common fields |
| --- | --- | --- |
| `learner_voice_follow_up_attempt` | Once after local guards accept a new connection, before activation/session POST | none |
| `learner_voice_follow_up_result` | Once per attempt: setup and playback ready, pre-connection failure, or cancellation | `outcome`, `error_code` |
| `learner_voice_follow_up_session_end` | Once per connected session after teardown and bounded local turn reconciliation, independent of HTTP persistence | `duration_ms`, `had_exchange`, `end_reason` |
| `learner_voice_follow_up_text_submit` | Once per locally accepted explicit text submit, before sending/queueing; not a delivery acknowledgement | `submission_method`, `interrupted` |
| `learner_voice_follow_up_microphone_result` | Once when an explicit on/off operation settles; editing/navigation may cancel a pending on operation | `enabled`, `outcome`, `error_code` |

In-memory attempt/generation, pending-text, and microphone-operation guards own
deduplication; no cross-session persisted dedupe. A retry starts a new attempt,
never automatically replays a question, and does not automatically enable mic.
Permission denial does not fail an otherwise ready connection. End is emitted
only for an already connected session, with the originally captured dimensions.

## Complete feature-owned payload

Common fields are exactly `shifu_bid` and `outline_bid` (stable, high-cardinality
pseudonymous course/lesson IDs for aggregate grouping), `learning_mode=read|listen`,
and `surface=read_content|listen_player` (low-cardinality non-personal enums).
All other fields are low-cardinality non-personal scalars:

- `submission_method=keyboard|button`; `interrupted` is boolean.
- `enabled` is the requested boolean microphone state.
- `outcome=success|failed|cancelled`.
- `error_code=none|microphone_denied|microphone_unavailable|microphone_busy|audio_unavailable|session_create_failed|session_expired|capacity_exceeded|origin_rejected|configuration_error|network_error|websocket_failed|server_error|unknown`.
- `duration_ms` is a finite nonnegative integer measured to transport teardown.
- `had_exchange` means a finalized turn has a final user input and nonempty
  actually-played answer transcript, not that its HTTP persistence succeeded.
- `end_reason=user_end|user_close|timeout|page_hidden|lesson_changed|connection_closed|connection_error|server_end|server_timeout|replaced`.

No event includes text, audio, transcripts, prompts, model, voice, user/anchor/
session ID, credential, URL, resumption handle, or raw errors. `useTracking`
delivers only these fields; shared identity and normalized page context remain
transport-owned, not duplicated in event data. Tracking failures cannot change
input, audio, connection, or persistence behavior.

## Compatibility and verification

v1 opened a separate dialog and started connection/microphone on the entry click.
v2 opens only the original panel and connects on actual input or retry. Keep
existing connection event names and payloads but split reports at the **actual
v2 deployment timestamp per environment**, not the code-authoring date. Do not
combine pre/post windows as unchanged connection or microphone adoption funnels.
New input events begin at v2 deployment, without backfill or legacy aliases;
never interpret missing historical rows as zero input usage. Ordinary
`learner_follow_up_submit` remains text-provider-only; no Live dual write.

Consumer fixture: three accepted connections, two successes, one failure, two
text submissions (keyboard and button), three microphone-on results (success,
failed, cancelled), one successful microphone-off, and two session ends (one
exchange) mean keyboard count 2, microphone-on count 3 with one success, an
aggregate connection ratio 2/3, and observed exchange share 1/2. The off event
does not inflate microphone-on adoption. Do not interpret these as three unique
people or correlate any typed question to a particular session-end row.

Producer tests assert exact names/allowlists, exclusions, pending-operation
dedupe, every terminal outcome, and throwing/rejecting tracker isolation.
Shared transport tests separately verify the final schema and fail-open path.
Local tests do not prove live external dashboard migration or delivery.

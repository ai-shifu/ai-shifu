---
title: Embedded Gemini Live Follow-Up Analytics
status: implemented
owner_surface: frontend
last_reviewed: 2026-09-05
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
- Pause adoption: count `learner_voice_follow_up_pause` by `reason`; count
  `learner_voice_follow_up_resume` separately to measure successful reuse of an
  existing connection. The aggregate resume/pause ratio is not a per-session
  conversion rate, and a resume is not a new connection success.

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
| `learner_voice_follow_up_pause` | Once when an already connected session transitions from active to paused and capture/playback are stopped | `reason` |
| `learner_voice_follow_up_resume` | Once when explicit typed input or microphone activation resumes the paused session after its playback is ready | none |

In-memory attempt/generation, pending-text, and microphone-operation guards own
deduplication; no cross-session persisted dedupe. A retry starts a new attempt,
never automatically replays a question, and does not automatically enable mic.
Permission denial does not fail an otherwise ready connection. End is emitted
only for an already connected session, with the originally captured dimensions.

Panel collapse, page hiding, and another exclusive-audio owner pause an existing
connected session instead of ending it. Repeated pause requests, opening the
panel, returning to the page, and pause/resume requests on an unconnected session
emit neither pause nor resume. A successful explicit resume uses the existing
session and emits no new attempt/result; it does not replay old audio or input,
and the microphone remains off unless the accepted action explicitly enables it.
If the connection cannot be recovered, the normal final-failure path applies.
Ending, changing the lesson, unloading, and natural expiry still end the session.
Natural expiry silently releases resources: only the next explicit input starts
a new attempt/session after old-session finalization. There is no automatic
session rollover or replay at expiry. These transitions share the original
guest/member eligibility, preview/classroom exclusions, and fail-open delivery.

The 2026-09-05 reliability revision permits one automatic recovery of a
resumable unexpected media-socket close in the same admitted session. It also
retries one transient HTTP heartbeat failure within the binding lifetime.
Neither is a new attempt, result, text submission, or microphone operation;
only an unrecoverable/final failure ends the connected session. Recovery cannot
replay an ambiguous typed question, mint another token, extend expiry, or change
the originating dimensions. The microphone action moved beside Send without
changing its explicit-operation event. A cooldown click preserves the original
failure instead of inventing a capacity result.

## Complete feature-owned payload

Common fields are exactly `shifu_bid` and `outline_bid` (stable, high-cardinality
pseudonymous course/lesson IDs for aggregate grouping), `learning_mode=read|listen`,
and `surface=read_content|listen_player` (low-cardinality non-personal enums).
All other fields are low-cardinality non-personal scalars:

- `submission_method=keyboard|button`; `interrupted` is boolean.
- `enabled` is the requested boolean microphone state.
- `reason=panel_closed|page_hidden|audio_replaced` for pause events only.
- `outcome=success|failed|cancelled`.
- `error_code=none|microphone_denied|microphone_unavailable|microphone_busy|audio_unavailable|session_create_failed|session_expired|capacity_exceeded|origin_rejected|configuration_error|network_error|websocket_failed|server_error|unknown`.
- `duration_ms` is a finite nonnegative integer measured to transport teardown,
  including paused wall-clock time; it is not active-speaking time.
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
With two pauses (`panel_closed`, `page_hidden`) and one successful resume added
to the fixture, pause count is 2 and resume count is 1. The connection ratio and
session-end count remain unchanged: neither transition creates an attempt,
result, or session end. Do not infer that the other pause failed to resume; it
may still be paused or may end after the reporting window.

Producer tests assert exact names/allowlists, exclusions, pending-operation
dedupe, every terminal outcome, and throwing/rejecting tracker isolation.
Shared transport tests separately verify the final schema and fail-open path.
Local tests do not prove live external dashboard migration or delivery.

For reliability comparisons, aggregate consumers must mark the actual deployment
timestamp of the recovery revision per environment. Session-end failures can
decrease because brief interruptions are now recovered, not because retries
became new successful attempts. Payloads, population, count unit, and the v2
input-adoption consumer fixture stay unchanged; no backfill or dual write.

The pause-lifecycle revision requires a separate **actual deployment timestamp
per environment** in the same consumers. Panel collapse/page hiding no longer
inflate session-end counts; resuming does not inflate attempts or successes.
Session durations now include pauses, so longer durations do not establish more
conversation time. Compare session-end counts, reasons, durations, pause counts,
and resume counts only within a consistent release cohort. New pause/resume
events start at deployment, without backfill or legacy aliases; missing older
events are not zero pause adoption. Timer and credential-deadline copy is hidden
without removing natural-expiry end telemetry or changing the bounded payloads.

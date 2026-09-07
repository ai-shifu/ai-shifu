---
title: Embedded Gemini Live Follow-Up Analytics
status: implemented
owner_surface: frontend
last_reviewed: 2026-09-07
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
- Readiness exposure: count `learner_voice_follow_up_readiness` with
  `initial=true` as eligible panel openings. Group these by `state` to measure
  initial gating; count each state's exposures separately to measure panels
  that encountered warming/unavailability or became ready. Divide ready-state
  counts by initial counts in the same UTC daily/seven-day window as an
  aggregate availability ratio, not an exact recovery or abandonment funnel.
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
Except for the readiness exposure event below, panel opening, disabled controls, invalid/empty/over-limit input, capacity
cooldown, re-renders, duplicate pending sends, and duplicate microphone requests
emit nothing. Later deliberate submissions/operations count again.

The 2026-09-06 readiness revision adds a non-minting service probe before
enabling Live input. Probe requests, automatic readiness refreshes, and actions
blocked while checking/warming/unavailable emit no attempt, text-submit, or
microphone-result events. The existing adoption/outcome consumer now counts
only actions accepted after this readiness gate; do not compare deployment
warm-up failures across the release boundary as connection reliability changes.
The server still checks admission atomically at mint time. A later service
failure uses the existing `server_error` result, not a new event or payload.

The additive readiness event describes committed, visible, expanded, editable
Live panels, including panels that never start a connection. Each mounted
AskBlock retains a set of observed states per opening and course/lesson/anchor/
surface. The first visible state has `initial=true`; each subsequently observed
state is emitted once with `initial=false`. Polling, repeated states, StrictMode
effects and rerenders do not inflate counts. Closing, unmounting, or changing
that scope starts a new exposure unit. Background-only states are not observed;
foregrounding can report the current state without resetting deduplication.
An active same-anchor connection reports `ready` even if a background service
probe is unready, matching the input's readiness bypass. Other disabling reasons
(pending sends, microphone operations, or capacity cooldown) do not change this
service-readiness metric. Readonly, print/classroom, preview, ordinary text, and
missing-controller panels emit nothing. These are state exposures, not attempts
with terminal cancellation events: closing before ready cannot prove abandonment.

| Event                                       | Exact trigger                                                                                                    | Additional fields beyond common fields      |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| `learner_voice_follow_up_readiness`         | First visible committed state per eligible opening, then once per distinct readiness state within that opening    | `state`, `initial`                          |
| `learner_voice_follow_up_attempt`           | Once after local guards accept a new connection, before activation/session POST                                  | none                                        |
| `learner_voice_follow_up_result`            | Once per attempt: setup and playback ready, pre-connection failure, or cancellation                              | `outcome`, `error_code`                     |
| `learner_voice_follow_up_session_end`       | Once per connected session after teardown and bounded local turn reconciliation, independent of HTTP persistence | `duration_ms`, `had_exchange`, `end_reason` |
| `learner_voice_follow_up_text_submit`       | Once per locally accepted explicit text submit, before sending/queueing; not a delivery acknowledgement          | `submission_method`, `interrupted`          |
| `learner_voice_follow_up_microphone_result` | Once when an explicit on/off operation settles; editing/navigation may cancel a pending on operation             | `enabled`, `outcome`, `error_code`          |
| `learner_voice_follow_up_pause`             | Once when an already connected session transitions from active to paused and capture/playback are stopped        | `reason`                                    |
| `learner_voice_follow_up_resume`            | Once when explicit typed input or microphone activation resumes the paused session after its playback is ready   | none                                        |

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
If setup completes while already paused, that readiness does not retroactively
create a connected pause. A later resume event requires an actual connected
pause transition, regardless of whether best-effort event delivery succeeded.
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

The controlled-rotation revision retains the same event names and count units.
After an explicit End, anchor/course change, or internal expiry, the next
accepted input can request a new connection under server-owned capacity and
ownership limits. This is one new attempt/result, not a resume; an already
connected predecessor ends once. A server quota rejection is a failed result
with `capacity_exceeded`; an ownership rejection is `session_create_failed`.
Pending issuance or a lost credential response is `network_error`. A disabled
backoff action remains excluded. A metadata-only status lookup and one safe
pre-mint clock correction share the accepted attempt's startup budget and emit
no extra attempt, text-submit, or microphone result. History finalization must
finish before minting. Failure keeps unsent input without automatic replay.
Same-token pause/resume and the eligible population remain unchanged. Neither
request IDs, ownership revisions, nor credential counts enter analytics.

## Complete feature-owned payload

### Minimal controls and continuous voice revision (2026-09-07)

The visible controls are microphone and Send only. A later accepted microphone
or text action also recovers a failed connection; there is no separate Retry or
End action. Microphone-off now pauses capture and playback and adds the bounded
pause reason `microphone_off`. Its one explicit off-result is retained; implicit
editing/collapse cleanup does not add an off-result. Voice activity animation
is local visual feedback, not a telemetry stream.

When an enabled microphone's connected session expires while visible and not
paused, one automatic successor is started after final played history is saved.
It reuses the authorized audio resource, never replays sent input, and does not
emit a microphone-operation event. A paused/idle session still expires silently
and waits for the next explicit input. Automatic renewal failure is terminal;
there is no infinite retry loop or idle token minting.

Credential lifetime includes an uncertainty window bounded by the monotonic
request start and response receipt. A transport/heartbeat failure after the
earliest possible expiry does not resume the possibly expired credential or
become a connection-failure event: input stays pending until the latest possible
expiry, then the ordinary timeout end and eligible renewal occur once. No new
admission can bypass the old risk lifetime, and the waiting interval emits no
extra adoption event.

During finalization/issuance/setup, retained input is gated and the microphone
button shows its pending spinner with `aria-busy`, not an enabled speech pulse.
It remains stoppable without a new action. Only confirmed successor readiness
releases that gate; this belongs to the existing renewal result, not another
microphone operation, exposure event, or new payload field.

The same pending gate covers initial setup and same-token socket resumption.
In this release, an explicit microphone-on success settles only when permission,
capture attachment, playback activation, and Gemini setup are all ready, not
merely when the device stream attaches. Cancellation before that boundary emits
one cancelled on-result, never a later success; explicit off remains separate.
Socket resumption neither starts another on-operation nor emits another result.
Consumers must separate pre/post-release microphone-success cohorts because the
older producer measured device attachment alone. Event names, payload fields,
eligibility, deduplication, and fail-open behavior are unchanged.

To distinguish user connection adoption from continuous-voice maintenance,
automatic successors emit `learner_voice_follow_up_renewal_attempt` and
`learner_voice_follow_up_renewal_result`, with exactly the corresponding normal
attempt/result payloads. Normal attempts/results remain explicit-input-only.
Both families use one per-generation attempt and one terminal result, original
guest/member eligibility and dimensions, preview/classroom exclusion, and
fail-open delivery. Session-end remains once per connected physical session.
The aggregate consumer reports renewal success/renewal-attempt separately from
explicit connection success/attempt in UTC daily/seven-day windows. Fixture:
one explicit successful connection plus two automatic successors (one successful,
one failed) means explicit success 1/1, renewal success 1/2, one microphone-on
operation, and two connected session ends after teardown. No exact row joins.
Consumers must split session-end/exchange and pause reports at this revision's
actual deployment timestamp; renewal events start then, without backfill or
dual write. This section supersedes earlier no-automatic-rollover wording.

Common fields are exactly `shifu_bid` and `outline_bid` (stable, high-cardinality
pseudonymous course/lesson IDs for aggregate grouping), `learning_mode=read|listen`,
and `surface=read_content|listen_player` (low-cardinality non-personal enums).
All other fields are low-cardinality non-personal scalars:

- `state=checking|warming|unavailable|ready` and boolean `initial` for readiness
  only; neither a retry countdown nor internal credential timing is collected.
- `submission_method=keyboard|button`; `interrupted` is boolean.
- `enabled` is the requested boolean microphone state.
- `reason=panel_closed|page_hidden|audio_replaced|microphone_off` for pause events only.
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

Readiness exposures begin at the actual readiness-telemetry deployment timestamp
per environment, without backfill or dual write. Existing attempts still measure
accepted connections only. Consumer fixture: one panel with checking, warming,
repeated warming, unavailable, ready produces four readiness events with one
initial event; a second panel initially ready adds one initial/ready event.
The initial denominator is 2, initial checking share 1/2, warming exposure count
1, unavailable exposure count 1, and aggregate ready/initial ratio 2/2. These
counts do not identify unique people, prove a connection, or correlate recovery
across events; no new session/anchor identifier is collected.

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

Controlled rotation requires its own **actual enablement timestamp per
environment** in reliability consumers. Previously locally blocked actions can
now reach server admission; do not pool their attempt denominators with the old
one-valid-credential cohort. There is no backfill, dual write, or new payload.
Extend the fixture above with two accepted replacements: one success and one
quota rejection, with the successful replacement later ending. There are now
five attempts, three successes, two failures (connection ratio 3/5), and three
session ends. Status recovery or clock correction within either replacement
adds zero events. A same-session resume still leaves these totals unchanged.
This aggregate fixture is not a join between particular questions and sessions,
and best-effort Umami results must never determine admission or billing.

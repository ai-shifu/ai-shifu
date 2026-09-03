# Gemini Live Voice Follow-Up

## Purpose / Big Picture

Courses whose effective follow-up model is
`gemini-3.1-flash-live-preview` open a fullscreen, voice-only follow-up dialog
from an explicit learner click. The click begins microphone acquisition in the
same browser activation. Learner and Gemini audio then flows continuously with
automatic VAD, interruption, mute, live transcripts, end, and retry. Completed
or interrupted turns appear in the existing ASK/ANSWER history; original audio
is never stored and no text fallback is offered.

The long-lived Gemini API key remains on the backend. The backend mints a
one-use, short-lived [Gemini ephemeral token](https://ai.google.dev/gemini-api/docs/live-api/ephemeral-tokens)
whose Live constraints lock the model, course system instruction, selected
voice, and session behavior. The browser uses that token to connect directly
to Gemini's constrained Live WebSocket. AI-Shifu continues to own admission,
capacity, session lifetime, transcript history, and non-billable usage through
ordinary authenticated HTTPS endpoints. Consequently, the feature does not
require a WebSocket Upgrade route or a different Gunicorn worker at the
AI-Shifu ingress.

The first release supports reading mode, listen mode, and teacher preview;
classroom remains excluded. It is available to every teacher only when
`GEMINI_LIVE_ENABLED=true`. Sessions warn 30 seconds before the issued token's
absolute 15-minute expiry and end at that expiry, including provisioning and
connection time. Usage and transcripts reported after the media plane moves into the
browser are explicitly client-reported and untrusted. They are bounded,
persisted only with `billable=0`, and must never drive settlement, permissions,
auditing, or another correctness-sensitive decision.

## Progress

- [x] 2026-09-02: Started from current `origin/main` on
      `sunner/gemini-live-voice-follow-up`; pull request #2732 is not a
      dependency.
- [x] 2026-09-02: Added the feature flag, capability-owned follow-up model
      catalog, 30 official voice choices, `live_voice` course configuration,
      effective lesson `follow_up_mode`, provider restrictions, and tests.
- [x] 2026-09-02: Added shared text/Live course context construction,
      deterministic ASK/ANSWER persistence, `billable=0` metering, Langfuse
      redaction, Redis capacity admission, and tests.
- [x] 2026-09-02: Added the fullscreen voice controller, AudioWorklet capture
      and playback, exclusive course-audio ownership, interruption, mute,
      timeout, lifecycle cleanup, five locales, privacy copy, analytics, and
      tests.
- [x] 2026-09-02: Hardened effective disable behavior, selected-voice
      preservation, Origin handling, bounded microphone buffering, responsive
      playback, and immediate history projection.
- [x] 2026-09-03: Replaced the Flask/Gemini WebSocket proxy with a backend
      ephemeral-token control plane and browser/Gemini media plane. Removed
      Flask-Sock, its internal WebSocket route, dedicated Nginx Upgrade config,
      proxy-only provider/accumulator code, and the feature-driven gthread
      startup changes.
- [x] 2026-09-03: Added direct-session Redis bindings and authenticated
      heartbeat, turn-report, and end endpoints. Browser-reported usage is
      reduced to a numeric allowlist and labeled
      `usage_attestation=client_reported_untrusted` before non-billable storage.
- [x] 2026-09-03: Focused browser-direct verification passes: 61 backend tests,
      39 frontend tests, and TypeScript type checking.
- [x] 2026-09-03: Wider affected suites pass: 209 backend tests passed with one
      expected skip, and 181 frontend integration tests passed. Ruff, Python
      formatting, frontend formatting/lint, TypeScript, and architecture
      boundaries also pass.
- [x] 2026-09-03: Closed direct-report security and lifecycle review gaps.
      Redis now atomically accepts only the next turn, caps a 15-minute session
      at 200 turns, and protects the in-flight write with an opaque claim.
      Turn/end requests use Fetch keepalive, turn bodies are capped at 60 KiB,
      and page teardown starts the final turn report before stopping audio.
      The focused Live suites pass with 72 backend and 49 frontend tests.
- [x] 2026-09-03: Corrected the token field mask to the protobuf JSON
      lower-camel contract, removed unsupported Gemini 3.1 proactivity and
      safety overrides so provider defaults apply, and bounded setup stalls at
      20 seconds. Capacity admission now remains reserved through the full
      disclosed token lifetime instead of being released by heartbeat loss or
      `/end`.
- [x] 2026-09-04: Anchored warning/end timers to the issued token expiry,
      preserved authenticated finalization for existing sessions after the
      feature flag is disabled, and prevented delayed turn acknowledgements
      from writing into a different lesson's active history state.
      Verification passes with 72 backend tests, 69 frontend tests,
      TypeScript, lint/format checks, architecture boundaries, repository
      harness, and the full pre-commit gate.
- [x] 2026-09-04: Kept a 30-second absolute post-expiry finalization window
      for turn reports and end cleanup, so an HTTP request carrying the last
      transcript can arrive after the browser stops audio at credential expiry.
      Heartbeat access, token lifetime, and capacity are not extended.
      The focused backend suite now passes 74 tests, including rejection of
      heartbeat after expiry and rejection of writes after the grace deadline.
- [x] 2026-09-04: Reject oversized HTTP bodies before buffering; show the
      credential-bound retry deadline and suppress impossible retries; hand
      outstanding turns off in one bounded lifecycle-safe finalization batch.
      Explicit end/close waits for the final worklet playback acknowledgement
      before materializing the last turn and restoring course-audio ownership.
      The focused suites pass 86 backend tests and 76 frontend tests, with
      TypeScript, translation, lint/format, architecture, and harness coverage.
- [x] 2026-09-04: Opted all Live HTTP endpoints into a sensitive-body policy.
      Generic request/response logging omits their bodies, responses use
      `Cache-Control: no-store`, and per-request size limits run before shared
      authentication/context JSON parsing. Other routes retain their existing
      logging and limits. Regression coverage includes known-length rejection
      without reading input and bounded unknown-length parsing.
- [x] 2026-09-04: Snapshot analytics dimensions and eligibility at the original
      click. Terminal events preserve that snapshot across lesson/mode/preview
      changes. `had_exchange` reflects a finalized local user/played-answer
      pair, including reports awaiting HTTP acknowledgement, and excludes
      usage-only or unheard turns. End duration stops at transport teardown.
      Verification passes with 101 focused backend tests, 89 frontend tests,
      TypeScript, and the full pre-commit gate. HTTP policy tests use the
      repository-pinned Flask 3.1.3 / Werkzeug 3.1.6 in an isolated dependency
      directory; the shared local virtualenv still had Flask 3.0.3.
- [x] 2026-09-04: Addressed CodeQL's reflected-HTML findings by returning
      explicit `application/json` responses with `X-Content-Type-Options:
      nosniff` from every Live endpoint. The shared envelope and unrelated
      routes are unchanged; tests cover markup-like values and MIME headers.
      All 102 focused backend tests and the full pre-commit gate pass.
- [ ] Exercise a real ephemeral token and direct Gemini WebSocket on the dev
      deployment with a valid credential and microphone.
- [x] 2026-09-03: Repository harness and the full
      `lefthook run pre-commit --all-files` gate pass after staging the
      proxy-file deletions.
- [ ] Complete Chrome, Safari/iOS, and mobile Chrome audio acceptance, including
      multi-turn speech, interruption, transcript accuracy, selected voice,
      15-minute ending, microphone release, and listen-audio restoration.

## Surprises & Discoveries

- The dev ingress returned HTTP 200 rather than WebSocket 101 for the original
  internal Live path because its outer proxy did not forward Upgrade headers.
  This was the concrete reason the voice dialog failed after session creation.
- Gemini explicitly supports browser client-to-server Live through ephemeral
  tokens and the constrained `BidiGenerateContentConstrained` endpoint. This
  lets AI-Shifu keep its API key and prompt policy server-side without owning
  the long-lived media socket.
- A browser-direct media plane removes the backend's independent observation of
  Gemini transcripts, playback, and token usage. Those reports can still power
  personal history and free-preview telemetry, but cannot be called trusted
  usage or used for billing.
- The browser can reuse a one-use ephemeral token for session resumption with a
  Gemini resumption handle. A new browser attempt still obtains a new token;
  disconnected browser state is not recovered across page loads or workers.
- The existing authenticated request client already resolves the configured API
  origin and sends the browser Origin. Reusing it keeps split-domain and local
  development deployments working without any feature-specific Nginx Host
  handling.
- Gemini may deliver final input transcription after `turnComplete`. The
  browser accumulator therefore keeps the completed turn mutable for 500 ms
  before sending the HTTP turn report.
- Fetch keepalive has a bounded request-body budget. Keeping the authenticated
  request under 60 KiB makes lifecycle-safe transcript persistence explicit
  instead of relying on browser behavior for an oversized payload.
- The Gemini `auth_tokens` resource exposes token creation but no revocation.
  After a credential reaches the browser, closing the AI-Shifu control-plane
  binding cannot prove that the Google socket closed. Capacity therefore has
  to remain reserved until `expireTime`; otherwise one client can overlap an
  old socket and a newly minted credential.

## Decision Log

- Decision: implement from current `origin/main` and do not inspect, repair,
  merge, or depend on pull request #2732.
  - Why: the user explicitly replaced the earlier delivery-order instruction.
- Decision: route by backend `interaction_mode` and resolved
  `follow_up_mode`, never model labels or `-live-` string matching in Cook Web.
  - Why: capability and availability are server-owned contracts.
- Decision: expose only `gemini-3.1-flash-live-preview` when the flag is on and
  discovery reports `bidiGenerateContent`; retain normal text models in the
  existing primary model path.
  - Why: the allowlist and discovered operation are independent safety gates.
- Decision: allow Live only with built-in `llm + provider_only`, store the
  official voice ID under `ask_provider_config.config.live_voice`, and default
  to `Kore`.
  - Why: external Dify, Coze, and knowledge-provider contracts do not implement
    Gemini Live, while voice is provider configuration rather than a new DB
    entity.
- Decision: supersede the server WebSocket proxy with a one-use constrained
  ephemeral token and direct browser-to-Gemini socket.
  - Why: this removes the failed ingress Upgrade dependency while keeping the
    API key and private course instruction on the backend.
- Decision: lock model, system instruction, audio-only response, selected
  voice, minimal thinking, VAD, transcription, context compression, tools,
  and initial-history behavior in the token's effective Bidi setup and
  lower-camel JSON field mask. Leave only `sessionResumption` unlocked and
  omit proactivity and safety overrides so Gemini 3.1's native defaults apply.
  - Why: a browser must not widen the token into a different Gemini session,
    but it must be able to send the server-issued resumption handle after
    `GoAway`.
- Decision: retain authenticated HTTPS endpoints, resolved through the existing
  API client, for session creation, a 15-second heartbeat, turn reports, and
  terminal cleanup. Bind the session to user, course, outline, anchor, preview
  state, Origin, model, voice, language, and absolute token expiry in Redis.
  - Why: access and capacity remain trusted even though the media plane is not.
- Decision: reserve per-worker, global, and per-user Redis capacity for the
  full 15-minute credential lifetime plus the 30-second connection margin.
  Keep the authenticated control-plane binding on a separate 45-second TTL,
  refreshed by a 15-second heartbeat. Never release capacity after the token
  has been disclosed; only roll it back when provisioning/storage fails before
  the response reaches the browser.
  - Why: Gemini exposes no token revocation. Releasing admission on `/end` or a
    missed heartbeat would let a modified browser retain the old Google socket
    and mint another token outside the 24/6/1 limits.
- Decision: apply the feature flag only to new-session admission. Already
  issued sessions keep authenticated heartbeat, turn-report, and end access
  until their binding or credential expires.
  - Why: disabling the feature cannot revoke Google's credential, and must not
    discard the final transcripts of an already active direct session.
- Decision: after a credential is issued, disable retry until its expiry plus
  the capacity safety margin and display the eligible retry time in all five
  locales. Re-entry shares that guard; no microphone, API request, or analytics
  attempt starts while the credential reservation is known to remain active.
  - Why: an immediate retry cannot succeed under the deliberately retained
    one-credential-per-user admission limit.
- Decision: carry the original outline ID through every asynchronous turn
  acknowledgement and compare it with the history store's current lesson
  scope at write time.
  - Why: a terminal HTTP report may complete after navigation; its durable
    history belongs to the original lesson, not the newly displayed one.
- Decision: allow authenticated turn/end requests against the existing Redis
  binding for up to 30 seconds after token expiry. Keep heartbeat access on
  the original expiry and reject finalization after the absolute grace deadline,
  even if a prior report refreshed the Redis TTL.
  - Why: network transit means the browser's final report cannot reach the
    backend at exactly the instant its audio session ends.
- Decision: treat every browser turn report as untrusted. Accept only bounded
  transcript strings, bounded numeric usage fields, a bounded turn index and
  latency, and an interruption boolean. Force `billable=0` and never settle it.
  - Why: the client can fabricate any report after direct connection.
- Decision: accept at most 200 reports per session and require the exact next
  one-based turn index. Reserve that index atomically in the Redis session with
  a server-only claim, advance it only after durable persistence, and release
  only the matching claim after a failed write.
  - Why: authentication alone must not let a modified client manufacture an
    unbounded number of history and usage rows or race duplicate turn reports.
- Decision: retain a bounded in-memory outbox of unacknowledged turns. Normal
  reports use ordinary requests, leaving the keepalive budget for one
  `/finalize` request initiated synchronously on pagehide/unmount. That request
  includes the in-flight predecessor and queued turns; the backend waits at
  most five seconds total for a held claim, skips durable indices, persists the
  remaining consecutive turns in order, then consumes the binding.
  - Why: keepalive cannot protect a fetch that is still behind a JavaScript
    promise. One batch also avoids consuming the browser's shared keepalive
    byte budget with multiple outstanding turn requests.
- Decision: cap each report/batch at 60 KiB before buffering it on the backend,
  and fail visibly if the frontend's unacknowledged backlog exceeds the bounded
  handoff budget. Explicit end/close waits for the bounded final playback ACK
  before creating final commits. Pagehide/unmount instead immediately sends
  the latest acknowledged playback checkpoint, which can conservatively omit
  the last unacknowledged audio quantum.
  - Why: unload cannot reliably wait for another worklet callback; it must
    initiate its final network request while the document still exists.
- Decision: save only final user transcript and answer text through the local
  playback watermark. Keep deterministic turn BIDs; save an empty interrupted
  ANSWER when appropriate; do not create history when final user transcript is
  absent.
  - Why: history should reflect what the learner said and heard, while retries
    must remain idempotent.
- Decision: use the same ephemeral token and newest handle for Gemini `GoAway`
  recovery only while the current browser controller remains alive.
  - Why: cross-page recovery would require durable audio and playback state
    outside this release.
- Decision: keep all failures in the voice dialog with retry or end controls;
  never fall back to text.
  - Why: Live is the teacher-selected provider and safety behavior.
- Decision: analytics retain only reviewed stable IDs, bounded enums,
  booleans, numbers, and duration. They exclude model, voice, audio,
  transcripts, prompt, URL, token, handle, and raw error.
  - Why: adoption can be measured without collecting conversation or secrets.

## Outcomes & Retrospective

The implementation is now aligned with the deployment the user actually has:
the AI-Shifu ingress handles only ordinary HTTPS for Live, while the browser
opens Gemini's own WebSocket. The long-lived provider secret and private course
instruction are not returned to the browser; the returned credential is
short-lived, one-use, and constrained. The old Flask-Sock dependencies,
server-side Gemini WebSocket wrapper, cookie ticket, backend turn accumulator,
Nginx Live location, and gthread startup changes have been removed.

Automated evidence after the pivot currently covers token constraints,
Redis fail-closed behavior, admission and Origin binding, direct-session
lifecycle, report bounds, deterministic/non-billable persistence, protocol
parsing, transcript reconciliation, audio backpressure, interruption,
resumption, retry-only failures, analytics, and TypeScript. Real provider and
browser acceptance remains outstanding and is not inferred from unit tests.

## Context and Orientation

The Flask routes are registered through
`src/api/flaskr/service/learn/routes.py`. The browser-direct control plane is
implemented by:

- `gemini_live_token.py`: builds the locked Live configuration and mints the
  short-lived credential with the server API key;
- `live_follow_up_session_store.py`: stores the trusted session/capacity
  binding in Redis;
- `live_follow_up_routes.py`: validates session admission and exposes session,
  heartbeat, turn, finalization-batch, and end HTTPS endpoints;
- `live_follow_up_persistence.py`: saves deterministic history and
  client-reported, non-billable usage;
- `live_follow_up_capacity.py`: owns per-worker/global/user Redis leases.

The frontend direct transport is implemented by:

- `src/web/src/lib/liveVoiceFollowUp.ts`: control-plane requests, constrained
  URL validation, PCM base64 framing, and Gemini server-message parsing;
- `geminiLiveTurnAccumulator.ts`: 500 ms transcript reconciliation, playback
  checkpoints, interruption, usage snapshot, and ordered turn reports;
- `useLiveVoiceFollowUp.ts`: real-click activation, direct socket lifecycle,
  setup/history frames, audio, heartbeat, resumption, commit, cleanup, and
  analytics;
- `liveFollowUpTurnWriter.ts`: ordered normal writes, bounded pending outbox,
  lifecycle-safe batch handoff, and acknowledgement deduplication;
- the existing dialog and AudioWorklet modules for UI, 16 kHz capture, and
  24 kHz playback.

Model settings and lesson projection remain in the shared LLM, Shifu, and
learn DTO services. Shared locale JSON lives under `src/i18n/<locale>` for
`zh-CN`, `en-US`, `fr-FR`, `ar-SA`, and `th-TH`. Privacy copy is in
`src/web/src/components/legals/EnPrivacy.mdx` and `ZhCnPrivacy.mdx`.

## Plan of Work

### Phase 1: capability and course configuration

Keep normal model APIs text-only. The follow-up catalog emits
`interaction_mode`, `allowed_roles`, `billing_mode`, and official voice
choices. Gemini discovery distinguishes `generateContent` from
`bidiGenerateContent`; the Live allowlist and kill switch both apply. Reject
main-model use and unsupported provider combinations on save, import, publish,
copy, and session start. Project resolved `text | live_voice | disabled` mode
into the lesson tree so learner UI never guesses.

### Phase 2: browser-direct control and media planes

On authenticated session POST, validate learner or preview access, effective
model/provider/voice, outline, anchor, learning mode, and Origin. Reserve Redis
capacity through the credential lifetime. Build the shared follow-up system
instruction and latest ten turns. Mint a Gemini token with `uses=1`, a
30-second new-session window, 15-minute expiry, and a locked effective Bidi
setup. Store a separate 45-second Redis session binding and return only the
ephemeral token, allowlisted constrained WSS endpoint, prompt-free setup,
history frame, expiries, and heartbeat period.

The browser validates the exact Google origin/path before appending the token
as `access_token`. It sends setup first and history only after setup completion.
It captures mono PCM16 at 16 kHz, targets 40 ms frames, rejects frames above
8 KiB, and drops frames when buffered output exceeds the real-time bound.
Gemini audio is 24 kHz PCM. Parse every content part and both camel/snake JSON
spellings used by the API. Clear playback immediately on interruption. Resume
`GoAway` with the newest handle on another constrained socket using the same
ephemeral token.

Every 15 seconds the browser renews only the trusted Redis control-plane
binding over authenticated HTTPS; the independent capacity reservation expires
with the disclosed credential. A completed/interrupted turn waits 500 ms for
late transcription and waits for the playback watermark before POSTing. The
backend validates/bounds the report, filters usage to allowed numeric token and
modality fields, writes history idempotently, and forces `billable=0`. On close,
timeout, navigation, or error, stop capture immediately. When the document
remains active, flush playback before creating the final report and POST end
after pending writes. On unload, synchronously initiate one bounded keepalive
finalization batch instead. Capacity is not released early.

### Phase 3: voice experience, privacy, and rollout

The shared read/listen parent owns one dialog/controller. Entering Live pauses
course audio through the exclusive-audio hook and restores prior listening
intent on exit. The dialog shows connecting/listening/speaking/reconnecting,
both transcripts, mute, end, warning, and retry. Microphone denial, provider
rejection, failed history commit, heartbeat failure, and network loss remain in
that dialog. Page hide, lesson/course change, unmount, close, and timeout stop
tracks, clear buffers, close the AudioContext, and release the socket.

Maintain disclosure, five locales, privacy copy, and the existing event family:
`learner_voice_follow_up_attempt`, `learner_voice_follow_up_result`, and
`learner_voice_follow_up_session_end`. Include production guest/member learners
in read/listen; exclude teacher preview and classroom. Keep analytics best
effort and independent from the user-visible operation.

## Product Analytics Contract (v1)

The business question is the share of accepted production learner voice
attempts that connect, their bounded failure outcomes, and whether connected
sessions produce an exchange. An attempt fires after local ID validation and
before microphone/session startup. Each accepted initial click or retry is one
attempt. The local credential-cooldown guard runs before that point: a disabled
retry or re-entry while admission is still reserved starts no microphone,
request, or analytics attempt. The existing aggregate attempt/result consumer
and payload allowlist remain unchanged; the UI explains the retry deadline.
Result fires once per attempt: `success` after Gemini setup and local
audio readiness, `failed` on a pre-connection terminal failure, or `cancelled`
on explicit end/close/navigation before connection. Session end fires once for
a previously connected session, after final local playback/turn reconciliation
but without waiting for HTTP acknowledgement. Pagehide/unmount emits in the
same lifecycle callback using the latest acknowledged playback checkpoint.
Dimensions and eligibility are captured at the originating click, not read
from a later render. `duration_ms` ends when transport teardown starts;
`had_exchange` means at least one finalized turn contains both a nonempty final
user transcript and a nonempty played-answer transcript. It measures observed
conversation, not history-storage success; pending and already acknowledged
reports count equally, while usage-only and unheard turns do not count.
This corrects the v1 producer race without changing event names or payload
keys; the aggregate attempt/result/session-end consumer needs no migration.

Common fields are `shifu_bid`, `outline_bid`, `learning_mode=read|listen`, and
`surface=read_content|listen_player`. Result adds bounded `outcome` and
`error_code`; session end adds integer `duration_ms`, boolean `had_exchange`,
and bounded `end_reason`. Teacher preview and classroom emit no learner event.
In-memory generation flags deduplicate callbacks; an explicit retry is a new
count. These events are aggregate product telemetry, not billing, audit, or
authorization data. Model, voice, audio, transcripts, prompt, anchor/session
IDs, WSS/HTTP URLs, token, resumption handle, and raw error are prohibited.

## Concrete Steps

1. Keep capability/configuration and lesson-mode work from the initial
   implementation.
2. Replace proxy session creation with constrained ephemeral-token minting and
   a Redis direct-session binding.
3. Replace Flask-Sock with authenticated heartbeat, turn, and end HTTPS routes;
   retain capacity and deterministic persistence.
4. Move Gemini protocol parsing, transcript accumulation, playback checkpoint,
   and `GoAway` resumption into the frontend controller.
5. Remove proxy-only modules/tests/dependencies, Nginx Upgrade location, and
   feature-driven worker changes; update installation guidance.
6. Add focused token, store, route, protocol, accumulator, and controller
   coverage, then run existing Live persistence/audio/analytics suites.
7. Run repository static/harness/pre-commit gates and update the open PR.
8. Deploy with the flag off, enable on dev, test a real session, then complete
   supported-browser acceptance before production enablement.

## Validation and Acceptance

- Catalog/configuration tests prove text-model isolation, Bidi capability,
  allowlist/flag behavior, provider restrictions, all voice IDs, default Kore,
  preservation across model switching, and resolved lesson mode.
- Token tests assert one use, 30-second connection window, 15-minute expiry,
  exact constrained model/config, private system instruction placement, prompt-
  free browser setup, and bounded provider failure handling.
- Session tests cover permission and Origin binding, Redis fail-closed,
  capacity acquisition/pre-disclosure rollback/token-lifetime expiry, hashed
  Redis keys, the independent heartbeat TTL, consume-once end without early
  capacity release, and no internal AI-Shifu WebSocket route.
- Protocol/controller tests cover setup-before-history, exact Google endpoint
  validation, PCM encoding, over-8-KiB and buffered-frame drops, multi-part
  audio, transcripts, interruption, mute, resumption, session errors, explicit
  retry, cleanup, and analytics exclusions.
- Accumulator/persistence tests cover late final input, the 500 ms window,
  playback watermarks, interrupted/empty answer, no fabricated user history,
  deterministic retries, transaction rollback, numeric usage allowlist,
  untrusted attestation, `billable=0`, and no settlement.
- Run focused pytest/Jest, Ruff and formatting, frontend type/lint, five-locale
  i18n checks, architecture boundaries, repository harness, affected broader
  suites, and `lefthook run pre-commit --all-files`.
- On dev, verify the session POST returns an ephemeral token, the browser opens
  the Google constrained WSS directly, no request targets the removed internal
  `/api/learn/live-follow-up/ws/` path, and normal API ingress needs no 101.
- Manual Chrome, Safari/iOS, and mobile Chrome acceptance must prove multiple
  turns, VAD, interruption, both transcripts, voice choice, timeout/reopen,
  microphone release, no course-audio overlap, and no text fallback.

## Idempotence and Recovery

Each admitted attempt creates a fresh session BID, Redis binding, capacity
reservation, and ephemeral token. A token opens one new Gemini session;
resumption inside that session reuses the token with the newest handle. If
provisioning or Redis storage fails before the token is disclosed, release the
reservation. Once disclosed, the reservation expires naturally after the
maximum token lifetime. Missed heartbeats expire only the control-plane
binding. End consumes that binding atomically; repeated end is harmless from
the browser's perspective and cannot revoke or release the Gemini credential.

Turn BIDs derive deterministically from Live session and turn index. The
existing persistence transaction makes a repeated report idempotent and rolls
back partial ASK/ANSWER work. A commit failure ends the current controller and
offers voice retry; it does not silently continue with unsaved history.

If the browser socket closes without a usable resumption path, stop the session
and require an explicit retry. If Redis is unavailable, reject Live while text
follow-up and normal HTTP stay operational. Rollback is
`GEMINI_LIVE_ENABLED=false`; saved Live configuration remains intact and
learner entries resolve disabled rather than falling back to text.

## Interfaces and Dependencies

The model catalog returns `interaction_mode`, `allowed_roles`, `billing_mode`,
and optional `voices: [{voice_id, style}]`. Settings store
`ask_provider_config.config.live_voice`; lesson nodes return
`follow_up_mode: text | live_voice | disabled`.

`POST /api/learn/shifu/{shifu_bid}/live-follow-up/{outline_bid}/session`
returns `session_bid`, `ephemeral_token`, the fixed constrained
`websocket_url`, prompt-free `setup`, optional `history`, `expires_at`,
`new_session_expires_at`, and `heartbeat_interval_ms`.

`POST /api/learn/live-follow-up/session/{session_bid}/heartbeat` renews the
trusted control-plane binding only. `POST .../turn` accepts bounded
client-reported transcript/playback/usage data and returns deterministic
persisted element IDs. `POST .../end` consumes the binding; the independent
capacity reservation remains until the already-disclosed token expires.

The Gemini media socket is
`wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained`
with the ephemeral token in `access_token`. That URL/token must never enter
logs, analytics, Langfuse, or persisted payloads. The direct design uses the
existing `requests`, Redis, SQLAlchemy, metering, Langfuse, AudioWorklet,
exclusive-audio, i18n, and analytics infrastructure. It no longer depends on
Flask-Sock, simple-websocket, wsproto, a dedicated AI-Shifu WebSocket ingress,
or gthread.

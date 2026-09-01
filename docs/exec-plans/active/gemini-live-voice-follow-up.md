# Gemini Live Voice Follow-Up

## Purpose / Big Picture

Add a voice-only follow-up experience for courses whose effective follow-up
model is `gemini-3.1-flash-live-preview`. An explicit Follow Up click opens a
fullscreen bidirectional voice session and requests microphone access in the
same browser activation. The learner and Gemini can speak continuously, use
automatic voice activity detection, interrupt playback, mute, end, and retry,
while final transcripts become the existing ASK/ANSWER history. The feature
does not expose a text fallback and never stores original audio.

The first release supports reading mode, listen mode, and teacher course
preview. Classroom mode stays excluded. Every teacher can configure the model
when the global `GEMINI_LIVE_ENABLED` kill switch is enabled. Sessions are free
preview usage: trusted Gemini usage is persisted with `billable=0`, no points
settlement runs, and Gemini's native safety behavior is used without the
AI-Shifu follow-up text risk check. Each session lasts at most 15 minutes,
warns at 14 minutes 30 seconds, and can be reopened after ending.

## Progress

- [x] 2026-09-02 05:07 CST: Started the implementation directly from current
      `origin/main` on `sunner/gemini-live-voice-follow-up`; the superseded
      instruction to land pull request #2732 first is intentionally not part
      of this execution.
- [x] 2026-09-02 05:07 CST: Mapped the current Gunicorn, Docker, Nginx,
      configuration, privacy, model-catalog, follow-up, metering, and frontend
      audio ownership surfaces and recorded the implementation contract here.
- [x] 2026-09-02 06:33 CST: Completed phase 1: WebSocket dependencies and route,
      one-time Redis ticket, capacity leases, gthread deployment, and dedicated
      Nginx proxying while the feature flag remains off.
- [x] 2026-09-02 06:33 CST: Completed phase 2: follow-up model catalog, voice
      validation, Gemini Live provider, transcript persistence, Langfuse
      tracing, and non-billable trusted usage.
- [x] 2026-09-02 06:33 CST: Completed phase 3: fullscreen voice controller,
      AudioWorklets, analytics, five locales, privacy disclosures, browser
      lifecycle cleanup, and production-enable readiness.
- [x] 2026-09-02 06:33 CST: Focused backend tests passed (247 passed, one
      skipped); focused frontend tests passed (142), along with TypeScript,
      frontend lint, i18n generation, Ruff, and architecture-boundary checks.
- [x] 2026-09-02 06:37 CST: The repository-wide
      `lefthook run pre-commit --all-files` gate passed, including generated
      documentation, shared translation, architecture, Ruff, ESLint, and
      Prettier checks.
- [ ] 2026-09-02 06:33 CST: Complete environment acceptance: real
      Gunicorn/Nginx/Gemini WebSocket integration, Playwright fake-microphone
      E2E, supported browser/device audio QA, external-ingress audit, and
      rollout capacity verification. Docker and Nginx executables are not
      available in this workspace, and no production Gemini credential is
      used by automated tests.

## Surprises & Discoveries

- `src/api/gunicorn.conf.py` already documents gthread as the intended
  production worker and guards gevent monkey-patching, but the API Dockerfile,
  dev Compose, runtime harness, and Cursor launcher still explicitly select
  gevent. Every actual startup surface must be aligned rather than relying on
  the comment or one production command.
- The repository owns the bundled Nginx reverse proxy but no outer production
  ingress manifest. The in-repository Live location can be verified here;
  Upgrade and idle-timeout behavior at the external ingress remains an
  explicit deployment acceptance gate.
- Existing Nginx API routes disable response buffering and use long HTTP
  timeouts, but they do not set the Upgrade/Connection hop-by-hop headers. A
  narrower Live route is needed before the general `/api/` route.
- The English and Chinese privacy policies already mention microphone access,
  but do not explain that live audio is sent to an AI provider, that final
  transcripts are retained as follow-up history, or that AI-Shifu does not
  persist original audio.
- Existing billing aggregation and settlement queries filter to
  `BillUsageRecord.billable == 1`. Live must nevertheless force and test
  `billable=0` at its own persistence boundary rather than depend only on
  downstream filtering.
- `simple-websocket==1.1.0` owns an internal unbounded input list with no
  public message-count limit. The proxy therefore continuously consumes it,
  enforces the declared 32,000-byte-per-second PCM rate with a two-second
  burst, and closes on excess; a very short transient library buffer remains
  until upstream exposes a bounded queue option.
- Gemini can deliver interim input hypotheses independently from final input
  transcription, and can attach final usage to a `GoAway` envelope. Interim
  hypotheses replace the browser draft but never enter history; every envelope
  is reconciled before recovery or termination.

## Decision Log

- Decision: implement from current `origin/main` and do not inspect, repair,
  merge, or depend on pull request #2732.
  - Why: the user explicitly replaced the earlier delivery-order instruction.
- Decision: represent Live support through backend capability fields
  (`interaction_mode`, `allowed_roles`, and `billing_mode`) instead of display
  names or model-name substring detection in Cook Web.
  - Why: provider capability is a server-owned contract and must remain stable
    when labels or future model identifiers change.
- Decision: initial discovery allowlists only
  `gemini-3.1-flash-live-preview`, requires `bidiGenerateContent`, and hides it
  whenever `GEMINI_LIVE_ENABLED` is false.
  - Why: a narrow server allowlist provides a safe rollout boundary while
    capability discovery prevents false positives.
- Decision: Live is valid only for built-in `llm + provider_only` follow-up
  configuration; Dify, Coze, and knowledge-provider combinations fail clearly
  both when settings are saved and when a session starts.
  - Why: the Gemini bidirectional protocol cannot satisfy the external
    provider contracts.
- Decision: store the selected official voice ID under
  `ask_provider_config.config.live_voice`, default `Kore`, and validate against
  the 30 official IDs without a database migration.
  - Why: this is provider configuration, not a new course entity attribute.
- Decision: proxy Gemini through the Flask service and keep credentials,
  upstream recovery handles, and provider errors off the browser connection.
  - Why: access control, transcript persistence, non-billable usage, and secret
    handling all require a trusted server boundary.
- Decision: use a 256-bit random cookie ticket whose hash and bindings live in
  Redis for 30 seconds and are consumed atomically with GETDEL. Redis failure
  is fail-closed only for Live.
  - Why: a WebSocket cannot rely on the ordinary bearer-header flow, and the
    raw credential must never enter URLs, JavaScript, logs, or analytics.
- Decision: run Gunicorn gthread with four workers and 16 threads per worker;
  cap Live at six sessions per worker, 24 globally, and one per user using
  Redis leases renewed every 15 seconds with a 45-second expiry.
  - Why: Flask-Sock supports threaded Gunicorn, while explicit local and global
    limits reserve threads for ordinary HTTP requests and survive worker loss.
- Decision: end a session when the browser WebSocket disconnects. Resume an
  upstream Gemini `GoAway` only inside the still-open browser connection.
  - Why: cross-worker browser recovery would require durable audio/playback
    state that is intentionally outside the first-version contract.
- Decision: preserve actual completed or interrupted transcript turns in the
  existing ASK/ANSWER structures, use deterministic BIDs, and store an empty
  interrupted ANSWER when no answer text played. Do not fabricate history when
  no final user transcript exists.
  - Why: retries and late duplicate provider events must be idempotent while
    history must reflect what the learner actually said and heard.
- Decision: never offer text fallback from the Live dialog.
  - Why: voice-only behavior is the selected course configuration; fallback
    would silently run a different provider and safety contract.
- Decision: analytics include only reviewed stable IDs, bounded enums,
  booleans/numbers, and duration. They exclude model, voice, audio,
  transcripts, prompts, URLs, credentials, and raw errors.
  - Why: product adoption can be measured without collecting conversational
    or security-sensitive content.

## Outcomes & Retrospective

The disabled-by-default implementation now spans the secure server proxy,
capability-owned settings, transcript/metering persistence, and fullscreen
voice-only browser experience. It includes bounded browser/upstream writers,
PCM rate limiting, finite provider I/O and setup deadlines, one-time Redis
tickets, capacity leases, recovery safeguards, deterministic persistence, and
explicit analytics/privacy contracts.

Automated evidence currently consists of 247 focused backend tests (one
skipped), 142 focused frontend tests, TypeScript, frontend lint, i18n key
generation, Ruff, the repository architecture boundary check, and the complete
repository pre-commit gate. Production
enablement remains intentionally blocked on the unchecked environment gates
listed in Progress: a real Gemini credential, Gunicorn/Nginx 101 path,
fake-microphone Playwright, external ingress and 24-session capacity exercise,
and manual Chrome/Safari/iOS/mobile audio acceptance. The rollout switch stays
false until that evidence exists.

## Context and Orientation

The backend Flask app starts at `src/api/app.py`; domain routes and services
live under `src/api/flaskr/service/`. Existing course settings persist
`ask_provider_config` and the learning path already writes generated ASK and
ANSWER blocks/elements. Model/provider discovery lives in the shared LLM and
configuration service paths. The metering source of truth is
`src/api/flaskr/service/metering/models.py` plus its recorder, and Langfuse
helpers live in `src/api/flaskr/api/langfuse.py`.

The learner frontend lives under `src/web/src/app/c/[[...id]]`. Reading and
listen surfaces share the chat lesson hierarchy; follow-up UI currently uses
AskBlock. Listen-mode audio coordination must use the existing exclusive-audio
owner so course audio and Live output never overlap. Teacher preview flows
through the same course route with preview state, while classroom has a
separate learning-mode signal and must remain excluded.

Shared translations live under `src/i18n/<locale>` for `zh-CN`, `en-US`,
`fr-FR`, `ar-SA`, and `th-TH`. Canonical English and Chinese privacy documents
are `src/web/src/components/legals/EnPrivacy.mdx` and `ZhCnPrivacy.mdx`.

Container startup is defined by `src/api/Dockerfile`, the four
`docker/docker-compose*.yml` variants, and `.cursor/run-api.sh`; manual startup
is documented in `INSTALL_MANUAL.md`. `src/api/gunicorn.conf.py` is loaded from
the API working directory. The repository reverse proxies are
`docker/nginx.conf` and `docker/nginx.dev.conf`. An external production ingress
is not versioned in this repository and must be audited during rollout.

## Plan of Work

### Phase 1: disabled infrastructure

Add `Flask-Sock==0.7.0`, `simple-websocket==1.1.0`, and `wsproto==1.3.2`.
Register a Sock route and a token-authenticated session-creation HTTP route,
but return no Live model while `GEMINI_LIVE_ENABLED=false`. The HTTP route
validates learner/preview access, course and outline/anchor bindings, and the
effective Live configuration. It creates a random one-time credential, stores
only its hash and bounded bindings in Redis for 30 seconds, and sets the raw
value in a precise-path HttpOnly, SameSite=Strict cookie that is Secure outside
local development.

The WebSocket route atomically consumes the Redis ticket, verifies its user,
course, outline, anchor, preview, and Origin bindings, and rejects every
missing/mismatched/replayed ticket. It then acquires worker, global, and user
leases, renews them while connected, sends application state and 25-second
heartbeat pings, and releases resources on every terminal path. Reject inbound
audio frames above 8 KiB and apply bounded queues/backpressure before provider
integration.

Align all Gunicorn starts to `gthread`, four workers, and 16 threads. Add a
dedicated Nginx Live prefix with HTTP/1.1 Upgrade, explicit Connection,
request/response buffering disabled, and 75-second send/read idle timeouts.
Keep normal HTTP routing unchanged. Deploy this phase with the feature switch
off and verify readiness, WebSocket 101 at the bundled proxy, 24 controlled
connections, rejected connection 25, per-user rejection, lease expiry, and
ordinary HTTP health.

### Phase 2: capability, provider, and persistence

Keep the existing primary model API text-only. Add a follow-up-specific model
catalog that emits `interaction_mode: text | live_voice`,
`allowed_roles: [main, follow_up] | [follow_up]`,
`billing_mode: billable | free_preview`, and official voice choices. Gemini
discovery distinguishes `generateContent` from `bidiGenerateContent`; only the
allowlisted Live model is exposed behind the feature flag. Validate model use,
provider type, and `live_voice` on settings save, import, and session start.
Expose resolved `follow_up_mode` per lesson-tree chapter so Cook Web never
guesses from model text.

Implement `GeminiLiveProvider` over the existing `websocket-client` dependency,
independent from LiteLLM completion and TTS. Configure audio-only response,
the chosen `speechConfig.voiceName`, input/output transcription, minimal
thinking, automatic VAD with interruption, session resumption, and context
compression triggered at 25,000 tokens while retaining 8,000. Do not enable
tools, search, or proactive audio. Reuse an extracted shared follow-up-context
builder for the course prompt, follow-up prompt, learner profile, language,
anchor, and ten recent turns; the Live path deliberately skips AI-Shifu custom
text risk checking.

Accept 16 kHz mono PCM16 little-endian browser frames, targeted at 40 ms, and
send 24 kHz PCM output frames. Process every content part in each provider
event. Send only bounded control messages: state, transcript, interrupted,
turn_committed, error, and session_end. Resume provider `GoAway` inside the
connection with its private handle, and never expose that handle.

Use a `LiveTurnAccumulator` keyed by session and turn index to reconcile
out-of-order transcripts, latest trusted usage, interruption, and terminal
state. Keep a bounded 500 ms reconciliation window after turnComplete. Persist
each eligible turn in one transaction with deterministic ASK, ANSWER, and
element BIDs and payload fields `interaction_mode`, `live_session_bid`,
`live_turn_index`, and `interrupted`. Store final user transcript and answer
text actually played; never store audio. Emit one Langfuse trace per session
and generation per committed turn using only final transcript, stable IDs,
latency, and usage. Persist complete token/modality usage in one
`BillUsageRecord` per turn with `billable=0` and no settlement enqueue.

### Phase 3: voice experience and enabled rollout

At the common reading/listen parent, own exactly one fullscreen-aware Live
controller and dialog. A Live Follow Up click synchronously resumes the audio
context, starts microphone acquisition, and requests the session while browser
activation is valid; listen-mode custom actions need a synchronous activation
callback. Do not create or expand AskBlock for Live.

Use AudioWorklets for microphone capture/resampling and PCM playback scheduling
with echo cancellation, noise suppression, and automatic gain. Enter the
exclusive-audio owner before Live, pause course audio, and restore the prior
listen playback intention after Live ends. Interruption clears the output queue
immediately. Mute stops sending microphone frames without falling back to text.
Dialog controls show connection/listening/speaking/reconnecting/ended state,
live and final transcripts for both roles, mute, end, and retry. Microphone
denial and every other retryable failure stay inside the voice dialog.

On page hide, course/lesson change, dialog close, unmount, or timeout, stop
tracks, disconnect the WebSocket, clear capture/playback buffers, and close the
AudioContext. Warn at 14:30 and end at 15:00 with a reopen affordance. Show a
non-blocking disclosure that audio is sent to an AI service and final
transcripts are saved to follow-up history. Update all five UI locales and the
English/Chinese privacy policies.

Add `learner_voice_follow_up_attempt`,
`learner_voice_follow_up_result`, and
`learner_voice_follow_up_session_end`. Common fields are `shifu_bid`,
`outline_bid`, `learning_mode`, and bounded `surface`; result adds bounded
`outcome` and `error_code`; session_end adds `duration_ms`, `had_exchange`, and
bounded `end_reason`. Include guest/member production learners, exclude teacher
preview and classroom, count each explicit first click/retry as one attempt,
and define result success only after connection. Extend
`creator_shifu_setting_save` with only
`follow_up_mode=text|live_voice`. Analytics failure is always fail-open.

### Product analytics contract (v1)

This section is the versioned producer contract for the Gemini Live learner
event family. It applies the canonical rules in
`docs/references/frontend-product-analytics.md`; changing an event name,
trigger, population, deduplication boundary, field, or enum requires a new
documented compatibility revision.

- Business question: among accepted production learner voice follow-up
  attempts, what share reaches a connected voice state, which bounded outcomes
  prevent connection, and how long and how often do connected sessions produce
  at least one committed exchange by course, learning mode, and entry surface?
- Metric definition: for each UTC day and rolling seven-day window, count raw
  `result` outcomes divided by raw `attempt` events, grouped by
  `learning_mode` and `surface`. Separately, compute session duration
  percentiles and the share of `session_end` rows with `had_exchange=true`.
  The primary count unit is an accepted attempt or connected session, not a
  distinct user. There is no attempt/session correlation ID, so these are
  aggregate ratios and must not be presented as row-level joins.
- Actor and surface: guest and logged-in learners in production reading and
  listen mode. Delivered `surface` is `read_content` or `listen_player`.
  Teacher preview uses the same controller but emits none of these learner
  events; `teacher_preview` is therefore not a delivered analytics value.
- Trigger: `attempt` fires after non-empty course, outline, and anchor IDs are
  accepted and immediately before microphone/session startup. Each explicit
  initial click or retry is a new attempt. `result` fires once: `success` on
  the first server `listening` or `speaking` state, `failed` on a terminal
  pre-connection failure, or `cancelled` on explicit end/close/replacement or
  learner navigation before connection. `session_end` fires once for a
  previously connected session when it reaches a terminal lifecycle reason.
- Population: production guest/member learners are included. Teacher preview,
  classroom mode, invalid/unloaded IDs, render-only updates, and attempts that
  never pass local guards are excluded. There is no separate client-side
  internal-employee flag; non-production/test traffic is isolated by the
  configured Umami site and test producers use a mocked/disabled transport.
- Count unit and deduplication: one accepted click/retry, one result per
  attempt, and one end event per connected session. In-memory attempt flags and
  generation guards suppress repeated server states and stale async callbacks.
  A later explicit retry deliberately starts a new count. No cross-page,
  cross-session, or persisted deduplication is performed.
- Correlation: `shifu_bid` groups by course and `outline_bid` groups by the
  selected lesson/chapter. Both are pseudonymous stable machine IDs. The shared
  tracker owns the distinct user identity; it is not duplicated in payloads.
  Without an attempt ID, attempt, result, and session-end rows correlate only
  in aggregate.
- Consumers: the Gemini Live adoption/reliability readout owned by product and
  engineering. No billing, authorization, audit, or provider-health decision
  may consume these best-effort events.
- Compatibility: these are new v1 event names with no predecessor, dual-write,
  or backfill. The additive `follow_up_mode` revision of
  `creator_shifu_setting_save` is canonical in
  `docs/product-specs/web-umami-contract-remediation.md`; historical missing
  values remain `legacy_unknown` for consumers.
- Verification: feature tests assert exact names, trigger timing, eligibility,
  retry/result/end deduplication, every bounded enum, exact payload allowlists,
  prohibited-field absence, and synchronous/asynchronous tracking failure
  isolation. Shared tracking tests cover the final flat-scalar delivered
  schema and transport fail-open behavior.

| Field           | Events      | Type and complete allowed values                                                                                                                                                                                                                                                 | Cardinality | Privacy class           | Why required                                                |
| --------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- | ----------------------- | ----------------------------------------------------------- |
| `shifu_bid`     | all         | stable non-empty course BID                                                                                                                                                                                                                                                      | high        | pseudonymous machine ID | group adoption by course                                    |
| `outline_bid`   | all         | stable non-empty outline BID                                                                                                                                                                                                                                                     | high        | pseudonymous machine ID | group adoption by learning unit                             |
| `learning_mode` | all         | string: `read`, `listen`                                                                                                                                                                                                                                                         | low         | non-personal enum       | compare supported learning modes                            |
| `surface`       | all         | string: `read_content`, `listen_player`                                                                                                                                                                                                                                          | low         | non-personal enum       | compare eligible entry surfaces                             |
| `outcome`       | result      | string: `success`, `failed`, `cancelled`                                                                                                                                                                                                                                         | low         | non-personal enum       | measure one terminal attempt result                         |
| `error_code`    | result      | string: `none`, `microphone_denied`, `microphone_unavailable`, `microphone_busy`, `audio_unavailable`, `session_create_failed`, `session_expired`, `capacity_exceeded`, `origin_rejected`, `configuration_error`, `network_error`, `websocket_failed`, `server_error`, `unknown` | low         | non-personal enum       | diagnose bounded pre-connection failures without raw errors |
| `duration_ms`   | session end | finite integer greater than or equal to zero                                                                                                                                                                                                                                     | numeric     | non-personal duration   | measure connected-session duration                          |
| `had_exchange`  | session end | boolean                                                                                                                                                                                                                                                                          | low         | non-personal boolean    | distinguish connected sessions with a committed turn        |
| `end_reason`    | session end | string: `user_end`, `user_close`, `timeout`, `page_hidden`, `lesson_changed`, `connection_closed`, `connection_error`, `server_end`, `server_timeout`, `replaced`                                                                                                                | low         | non-personal enum       | compare bounded connected-session terminal states           |

The complete application payloads are: common four fields for `attempt`;
common fields plus `outcome` and `error_code` for `result`; and common fields
plus `duration_ms`, `had_exchange`, and `end_reason` for `session_end`. Model
names, voice IDs, audio, transcripts, prompts, anchor IDs, Live session IDs,
WebSocket paths/URLs, tickets, tokens, API keys, raw errors, and provider
responses are prohibited. `error_code=none` is used for success and explicit
cancellation; a failed result uses one reviewed failure code. Analytics calls
are never awaited by, and never determine, the voice or settings workflow.

## Concrete Steps

1. Add the three pinned server WebSocket dependencies and gthread defaults.
2. Update Dockerfile, Compose variants, Cursor launcher, manual instructions,
   and both Nginx configurations; verify external ingress separately.
3. Add feature/capacity configuration with false/off rollout defaults and
   regenerate `docker/.env.example.full` after concurrent config work settles.
4. Implement the session ticket store, capacity lease manager, HTTP session
   factory, Sock route, bounded protocol schemas, cleanup, and focused tests.
5. Add the follow-up model catalog and Gemini Live capability/voice validation,
   then thread resolved `follow_up_mode` into lesson DTOs.
6. Extract shared follow-up context, implement the upstream provider and turn
   accumulator, then add idempotent transcript, trace, and non-billable usage
   persistence with focused failure/interruption tests.
7. Implement the shared frontend controller, AudioWorklets, dialog, exclusive
   course-audio lifecycle, timeout, and retry-only failure paths.
8. Add analytics contract, producers, privacy-negative tests, five locales,
   disclosure copy, and English/Chinese privacy updates.
9. Run focused backend/frontend suites first, then type/lint/i18n, architecture,
   repository harness, WebSocket integration, fake-microphone E2E, and complete
   pre-commit gates.
10. Deploy with `GEMINI_LIVE_ENABLED=false`; verify capacity and ordinary HTTP,
    audit the external ingress, then enable for all teachers. Roll back by
    setting the switch false without changing text follow-up.

## Validation and Acceptance

- Catalog tests prove that primary models stay text-only, `generateContent`
  and `bidiGenerateContent` are distinguished, the Live allowlist and kill
  switch are enforced, and Cook Web routes only by `follow_up_mode`.
- Configuration tests cover all official voice IDs, default Kore, rejected
  unknown voices, rejected main-model use, and rejected Dify/Coze/knowledge
  provider combinations at both save and session start.
- Ticket tests cover 256-bit generation, hash-only Redis state, exact cookie
  attributes/path, 30-second expiry, atomic one-time use, replay, Origin and
  binding mismatch, Redis outage fail-closed, and unaffected text/HTTP paths.
- Capacity tests cover six per worker, 24 globally, one per user, renewal every
  15 seconds, 45-second stale expiry, acquisition/release races, worker loss,
  and available ordinary HTTP threads.
- Protocol tests cover 40 ms PCM input, over-8-KiB rejection, 24 kHz output,
  bounded queues/control payloads/errors, heartbeat, disconnects, GoAway
  resumption, multi-part events, and browser disconnect without cross-worker
  resume.
- Accumulator/persistence tests cover out-of-order/final transcripts, the 500
  ms window, interruption, empty ANSWER, absent final ASK, deterministic retry
  idempotence, transaction rollback, full modality usage, `billable=0`, and no
  settlement. Langfuse tests prove audio, tickets, keys, handles, and raw errors
  are absent.
- Frontend tests cover activation-stack startup, normal text-model routing,
  microphone denial and retry-only UI, PCM resampling, queue clearing on
  interruption, mute, 14:30 warning/15:00 end, course/background/unmount
  cleanup, listen pause/intent restore, preview inclusion, and classroom
  exclusion.
- Analytics tests assert exact names, payload allowlists, exclusions,
  deduplication, every terminal state, and fail-open operation, and explicitly
  reject model, voice, audio, transcript, prompt, URL, token, and raw error.
- Run focused pytest/Jest, backend static checks, frontend type/lint, five-locale
  i18n generation/usage checks, `python scripts/check_architecture_boundaries.py`,
  `python scripts/check_repo_harness.py`, real gthread/Nginx 101 integration,
  Playwright fake-microphone E2E, and `lefthook run pre-commit --all-files`.
- Manual acceptance on desktop Chrome, Safari/iOS, and mobile Chrome proves
  several continuous turns, VAD, interruption, both transcripts, selected
  voice, session timeout/reopen, microphone release, and no course-audio
  overlap. Prior or adjacent audio tests are not acceptance evidence.
- Rollout acceptance starts disabled and proves readiness, 101 Upgrade,
  heartbeat through the external ingress, 24 concurrent sessions, rejection
  above capacity, and normal HTTP health before enabling all teachers.

## Idempotence and Recovery

Session creation is retryable because every attempt issues a new random ticket;
only a consumed ticket can open one WebSocket. Redis GETDEL and deterministic
turn BIDs make ticket and provider-event replay harmless. Capacity leases
expire after missed renewal and are released best-effort on normal termination.
Transcript writes use one transaction per turn, so a partial ASK/ANSWER pair is
rolled back and the same deterministic turn can be retried.

If Gemini signals GoAway, reconnect only the upstream socket with its newest
private resumption handle while the browser connection remains alive. If the
browser socket closes, end the session and ask the learner to explicitly retry.
If Redis is unavailable, reject new Live sessions while keeping text follow-up
and all normal HTTP paths operational.

Deploy infrastructure with the feature flag false. If provider, capacity,
browser, privacy, or production proxy behavior fails acceptance, restore safe
behavior by setting `GEMINI_LIVE_ENABLED=false`; existing text-model courses
continue on their unchanged SSE path. Re-running generators or focused tests is
safe, but inspect concurrent working-tree changes before accepting generated
output.

## Interfaces and Dependencies

The follow-up model catalog returns these stable fields for every option:
`interaction_mode`, `allowed_roles`, and `billing_mode`. A Live option also
returns `voices: [{voice_id, style}]`. Course settings store
`ask_provider_config.config.live_voice`; lesson nodes return resolved
`follow_up_mode: text | live_voice`.

`POST /api/learn/shifu/{shifu_bid}/live-follow-up/{outline_bid}/session`
returns a stable `session_bid`, same-origin WebSocket path, and expiry while
setting the one-time HttpOnly ticket cookie.
`WS /api/learn/live-follow-up/ws/{session_bid}` receives PCM16 binary frames
and bounded JSON client controls. Server JSON is one of:

- `state` with `connecting | listening | speaking | reconnecting | ended`;
- `transcript` with `role`, `turn_index`, `text`, and `final`;
- `interrupted`;
- `turn_committed`;
- `error` with bounded `code` and `retryable`; or
- `session_end` with bounded `reason`.

The upstream provider is `GeminiLiveProvider`, built with the existing
`websocket-client` and not LiteLLM or TTS. The inbound server uses
`Flask-Sock==0.7.0`, `simple-websocket==1.1.0`, and `wsproto==1.3.2` on
Gunicorn gthread. Redis is mandatory only for Live tickets/capacity. Existing
SQLAlchemy generated-history, BillUsageRecord, Langfuse, translation,
exclusive-audio, and shared analytics infrastructure remain authoritative.

# Gemini Live Voice Follow-Up

## Purpose / Big Picture

Courses whose effective follow-up model is
`gemini-3.1-flash-live-preview` use the existing AskBlock layout in reading,
listening, and teacher preview. Opening the panel only reveals history and the
input; the first keyboard submission or explicit microphone click starts Live.
Keyboard and microphone input both receive native audio answers and transcripts.
Editing text stops microphone capture; only an explicit click starts it again.
Both input methods can interrupt an answer. Completed or interrupted turns
appear in the existing ASK/ANSWER history; original audio is never stored and
Live input never falls back to the ordinary text/SSE provider.

The long-lived Gemini API key remains on the backend. The backend mints a
one-use, short-lived [Gemini ephemeral token](https://ai.google.dev/gemini-api/docs/live-api/ephemeral-tokens)
whose Live constraints lock the model, follow-up system instruction, selected
voice, and session behavior. The browser uses that token to connect directly
to Gemini's constrained Live WebSocket. AI-Shifu continues to own admission,
capacity, session lifetime, transcript history, and non-billable usage through
ordinary authenticated HTTPS endpoints. Consequently, the feature does not
require a WebSocket Upgrade route or a different Gunicorn worker at the
AI-Shifu ingress.

Live does not load or concatenate the teacher-authored Course Prompt. A short
voice instruction supplies the default base context, including the existing
learner-profile formatting. Configured follow-up prompts are retained; their
`{shifu_system_message}` placeholder resolves to that voice context. Learner
language, current learning content, and recent follow-up history remain
available. Ordinary text follow-ups continue to inherit the Course Prompt.

The first release supports reading mode, listen mode, and teacher preview;
classroom remains excluded. It is available to every teacher only when
`GEMINI_LIVE_ENABLED=true`. The issued token's absolute 15-minute expiry is an
internal connection boundary, including provisioning and connection time, not
a user-facing countdown or error. Expiry retains the panel, history, and draft;
the next deliberate input establishes a new connection after bounded final
history persistence. Never replay an already-sent question or mint idle tokens.
Usage and transcripts reported after the media plane moves into the
browser are explicitly client-reported and untrusted. They are bounded,
persisted only with `billable=0`, and must never drive settlement, permissions,
auditing, or another correctness-sensitive decision.

## Progress

- [x] 2026-09-05: Resolved the merge with main `724ed0818`, preserving
  Live controls, RTL regression coverage, cached keepalive transport, and
  analytics fields while adopting the unified frontend source directories.
  Updated Live-only imports and test mocks that Git could not migrate
  automatically; regenerated repository knowledge indexes.
  Validation: all 228 frontend suites / 2,336 tests passed; focused Live,
  shared LLM, configuration and deployment-contract tests passed (365 passed,
  one skipped), including real Redis coverage. TypeScript, lint and the full
  all-files pre-commit gate passed. No deployment was performed.

- [x] 2026-09-05: Current-head review of `f1f259390` found two further edge
      cases. Reproduce three Redis failures where an undisclosed failed mint's
      retired head blocked retry despite released risk; rely on actual risk
      and rolling quotas instead of its obsolete expiry. All 260 focused
      backend tests pass, including 61 real Redis cases. Four final-input-first
      variants also reproduced (unrelated, repeated, shared-prefix, overlapping
      questions). Freeze already-final input at the terminal boundary; retain
      missing-final and pre-terminal fragment reconciliation. All 199 focused
      accumulator/controller tests and TypeScript pass. Keep both review
      threads open until these fixes are pushed and verified in the PR.
- [x] 2026-09-05: User authorized adjusting the one-valid-credential rule and
      designing controlled replacement. Record the proposed bounded contract
      in Phase 4 below; this is a design, not an implemented capacity change.
      Keep the existing global credential exposure unchanged and distinguish
      application ownership from still-valid Google credentials.
- [x] 2026-09-05: All applicable CI checks on `6f28f2916` reached terminal
      states; executed checks passed. Bugbot's quota skip and CodeRabbit's
      size skip are not review approvals. The admission review remains open:
      retiring an old anchor does not yet permit immediate token replacement.
- [x] 2026-09-05: Verify the audio-ownership review against the actual pinned
      `markdown-flow-ui@0.2.24` Slide/Player in Chrome, not a mocked player.
      Opening the original desktop/mobile Ask panel physically pauses native
      course audio before Live connects. End inside the still-open panel keeps
      it paused; closing resumes only prior playing intent, not manually paused
      narration. Resolve the disproven review without another playback owner.
      Gemini transport was mocked; temporary fixtures and services were removed.
- [x] 2026-09-05: Implement Phase 4 behind default-off
      `GEMINI_LIVE_ROTATION_ENABLED`. Verify End/new-anchor replacement,
      metadata-only lost-response recovery, one shared startup budget, history
      gating, generation guards, and exact analytics/consumer contracts.
      Frontend: 228 suites / 2,330 tests passed, including 156 controller cases.
      Backend: 255 focused tests passed, including 56 real Redis Lua cases.
      Independent review caught and corrected post-admission failure responses
      losing the successor identity; regressions cover recovery via that ID.
- [x] 2026-09-05: Full dev-tool check and repository-wide pre-commit passed,
      including pinned Ruff, five-locale parity/usage, architecture, and harness.
      TypeScript and full lint passed with existing warnings. Current-head CI
      and review synchronization are recorded in PR #2744 after each push.
- [ ] Deployment/enablement and physical Gemini/Safari/mobile acceptance remain
      separate, unperformed operations; do not infer them from local tests.
- [x] 2026-09-05: Merge current main in `db6b859fe` and regenerate the sole
      conflicting `docs/generated/harness-health.md`; dev-tool verification
      and full pre-commit passed. No deployment was performed.
- [x] 2026-09-05: Reproduce review `discussion_r3938739497`: the first output
      of a spoken next turn inside reconciliation could merge into a terminal
      predecessor before its input transcription arrived. Route new output to
      the active turn while retaining input/usage-only late reconciliation.
      Four ordering regressions and the existing accumulator/controller suite
      pass (165 tests); the three initial reproductions failed before the fix.
- [x] 2026-09-05: Codex review of `201e096f8` found a paused listen attempt
      retained after the rendered slide anchor changed. End mismatched retained
      attempts before the new panel becomes interactive; keep same-anchor
      collapse paused and leave credential admission unchanged. Four desktop/
      mobile, expanded/collapsed regressions pass (red before correction).
      The final full frontend run passed 227 suites / 2,271 tests, TypeScript,
      and full pre-commit; subsequent CI passed, while the separate admission
      contract review remains open as recorded above.
- [x] 2026-09-05: Codex review of `201e096f8` found resume telemetry without
      an originating connected pause when setup finished in the background.
      Track the connected-pause transition independently of event delivery;
      do not infer it from later connection readiness. The new regression
      failed before correction, and all 128 controller tests now pass.
- [x] 2026-09-05: Follow-up regression review found that a discarded answer
      could leave `speaking` state behind after pause. Reset only the audible
      speaking state, preserving connecting/reconnecting. Both microphone and
      keyboard reproductions failed before correction; all 127 controller
      tests now pass, including a non-interrupted next text-submit event.
- [x] 2026-09-05: User approved pause/continue for panel collapse and temporary
      backgrounding, with no visible 15-minute limit. Explicit End, different
      anchor/lesson/course, page unload, and expiry still retire the connection.
      Opening a panel alone does not resume media or microphone capture.
- [x] 2026-09-05: Integrate and verify pause/output suppression, click-safe
      resume, exact credential/admission deadline, retained background binding,
      silent natural expiry, finalization-gated next input, and pause/resume
      analytics. Local Chrome with real AudioContext/worklet and mocked
      transport verified collapse releases capture and suspends output;
      reopening alone remains muted, next text reuses one session/socket,
      and shortened natural expiry retains history without error or a clock.
      The next explicit Send creates exactly one replacement connection.
      Desktop/mobile screenshots confirm the microphone beside Send inside
      the original input. Temporary QA route/server/browser were removed.
- [x] 2026-09-05: Regression review fixed paused typed-handoff deadlock,
      premature history commit before the final playback watermark, and a
      failed binding-close request poisoning future input. Bound native audio
      close to one second. Keep retained-history recovery explicit and bounded;
      one click never chains two closing budgets. Backend Live suites:
      183 passed, one environment-dependent skip; no schema or deployment edits.
- [x] 2026-09-05: Final full frontend run passed all 227 suites / 2,264 tests;
      controller 125 and writer 33 focused cases passed. TypeScript, lint,
      architecture boundaries, and repository harness passed. Physical
      Safari/iOS/mobile Chrome, real Gemini, and real Redis integration remain
      unverified; browser fixture coverage is not presented as those gates.
- [x] 2026-09-05: Move the manual microphone action into the original input,
      beside Send, using the public textarea class hook and a local adornment.
      Preserve one textarea, existing keyboard behavior, and manual capture.
      Real Chrome with mocked Gemini verified desktop, 390px mobile, RTL,
      typed input without capture, click activation, and capture release on
      editing. The status and retry row remain below the input. The later
      user-approved lifecycle removes retry clocks entirely in all five locales.
- [x] 2026-09-05: Add one bounded recovery for unexpected resumable socket
      closes and one transient heartbeat retry; retain the same admission,
      token, history accumulator, expiry, and analytics session. Preserve
      the original failure during cooldown. Controller tests: 95 passed;
      full frontend suite: 227 suites / 2,207 tests passed.
- [x] 2026-09-05: Complete full `lefthook run pre-commit --all-files`, including
      five-locale parity/usage, pinned Ruff 0.16.5, architecture and repository
      harness. The first run sorted the new locale keys; the second passed.
- [x] 2026-09-05: Update PR #2744 and follow CI/review for the
      input/pause/reliability revision through `6f28f2916`. The newly authorized
      admission change is an outstanding implementation, not a resolved review.

- [x] 2026-09-04: Integrate Live into the existing AskBlock; separate playback,
      microphone, and connection activation; add keyboard interruption and
      shared-store reconciliation. All 227 frontend suites / 2,163 tests passed;
      TypeScript, lint, translation usage, and architecture checks passed.
      Full `lefthook run pre-commit --all-files` passed after staging the
      deleted dialog and the locale sort; required Ruff 0.16.5 ran in an
      isolated temporary tool environment. Latest focused rerun: 192 passed.
- [x] 2026-09-04: Local Chrome acceptance with the real AskBlock, controller,
      AudioContext, and AudioWorklet plus mocked HTTPS/Gemini frames and capture:
      opening created no audio/capture, Enter sent text without permission,
      playback and transcripts rendered in existing bubbles, denied permission
      retained keyboard use, editing ended capture tracks, and End closed the
      output context while preserving the draft/panel/history. Desktop and
      390px mobile layouts were visually checked. Temporary fixture removed.
- [x] 2026-09-04: Submitted embedded revision `ad3038d58` to PR #2744 and
      updated its title/body for voice plus keyboard in the original panel.
- [x] 2026-09-04: Addressed existing review `discussion_r3932264095`: normalize
      terminal `/v1beta` in native model discovery and continue past an empty
      OpenAI-format parse from a successful native proxy response. Preserve
      reverse-proxy prefixes, text-model discovery, and Bidi capability metadata.
      Added nine regressions; LLM/token tests: 119 passed, one environment skip.
- [x] 2026-09-04: Self-review tightened pending text admission: only audio or
      completion in the submitted question's own turn releases its send guard.
      Coalesced old interruption/completion and late old audio no longer allow a
      third question before the second starts. Both event combinations covered;
      controller suite: 72 passed; TypeScript and full pre-commit passed.
      Full frontend rerun: 227 suites / 2,165 tests passed.
- [x] 2026-09-04: Addressed Codex review `discussion_r3934843129`: ending
      waits at most five seconds for the normal turn queue before handing its
      retained, bounded outbox to the idempotent finalizer. Stop queued normal
      successors after takeover; late acknowledgements cannot duplicate history.
      Over-budget ordered retries have a ten-second per-request wait and never
      consume a binding with an incomplete outbox. Three regressions reproduced
      the unbounded wait before the fix. All 98 writer/controller/real-transport
      lifecycle tests and TypeScript passed, including a native fetch that never
      settles. Full frontend rerun: 227 suites / 2,174 tests passed. No HTTP
      schema, deployment, or analytics contract changes.
- [x] 2026-09-04: Addressed follow-up review `discussion_r3934973719`:
      finalization retries the same idempotent batch up to three times with a
      one-second delay after rejection. If all attempts fail, clear rejected
      takeover/finish state, resume normal writes, and requeue every retained
      successor, including those skipped during takeover. Pending-index guards
      prevent duplicate sends after late acknowledgements. Three regressions
      failed before the fix; all 102 focused controller/writer/real-transport
      lifecycle tests passed, including native HTTP 503 followed by success.
      Full frontend rerun: 227 suites / 2,178 tests passed.
      The existing backend route/finalization suite also passed all 62 tests
      with repository-pinned Flask/Werkzeug in an isolated temporary overlay.
- [x] 2026-09-04: Addressed review `discussion_r3935086763`: detach recovery
      from an original `/turn` fetch that never settles. Advance the queue
      generation, invalidate old queued successors, and start a new ordered
      chain for retained reports. A late active-request acknowledgement remains
      idempotent; stale failures cannot notify or restart the recovered queue.
      Three regressions failed before correction. All 106 focused tests and
      TypeScript passed, including real shared-transport recovery after three
      HTTP 503 finalizer rejections while the original native fetch stays pending.
      Full frontend rerun: 227 suites / 2,182 tests passed.
- [x] 2026-09-04: Addressed review `discussion_r3935201692`: keep `finish()`
      attached to the recovered drain instead of rejecting after enqueue.
      Retry only the earliest unacknowledged index; a rejected/stalled recovery
      request cannot advance its successors. One monotonic 25-second closing
      budget covers the normal drain, finalizer attempts, ordered recovery, and
      binding close. Pagehide can still hand off the retained outbox during
      recovery, without restarting media or duplicating session-end analytics.
      Four regressions failed before correction. All 113 focused tests and
      TypeScript passed, including controller teardown/pagehide, repeated
      failure, stuck requests, and a backward wall-clock jump. Full frontend:
      227 suites / 2,189 tests passed.
- [ ] 2026-09-04: Follow valid review threads and recheck current-head CI.
      Complete real-Gemini and physical
      Safari/iOS/mobile Chrome acceptance before claiming those environments:
      no Gemini credential is available in the local environment for this run.

### Embedded AskBlock interaction contract (2026-09-04)

This revision supersedes the standalone-dialog and automatic-microphone UI
described in the earlier delivery journal below. Keep one controller in the
read/listen parent. AskBlock remains the only message renderer and the existing
ask store remains its source of truth. Merge provisional messages by session,
turn, and role, then bind the existing turn-report acknowledgement element IDs.
No new HTTP endpoint, database migration, credential, or deployment setting is
required. Preserve the AUDIO-only setup, automatic VAD, native safety, free
preview accounting, and Course Prompt exclusion.

Use realtimeInput.text for keyboard questions. Stop queued playback immediately
on a typed interruption but reconcile the old turn at the upstream interruption
or completion boundary. Accept only one pending handoff, retain failed drafts,
and never replay a question automatically after an ambiguous disconnect.
As amended on 2026-09-05, collapsing the panel or a visibility change pauses
Live: release microphone and audio exclusivity, mute and clear playback, suppress
late output from the discarded turn, and retain its played-prefix history.
The next explicit input resumes the existing AudioContext and revalidates the
binding; it never enables the microphone without an explicit microphone click.
Actual pagehide/unload, scope/anchor change, End, and internal expiry retire the
connection. Ending Live itself leaves the panel/history visible.
The existing listen custom-action panel owns
course pause/resume; a still-open panel never resumes course audio.

Analytics extends the existing adoption/connection consumer with typed-use and
microphone-operation counts per reporting window. Production read/listen guests
and members are included; teacher preview, classroom, disabled/invalid actions,
and duplicate re-entry are excluded. All producers are fail-open. Shared payload
fields are shifu_bid, outline_bid, learning_mode, and surface, using the existing
bounded types. No content, model, voice, credential, or raw error is collected.

- learner_voice_follow_up_attempt starts at an accepted connection operation,
  not panel open. Existing result/end payloads and once-per-attempt/session
  guards remain; success means setup plus playback readiness, independently of
  optional microphone permission. Existing aggregate consumers must segment the
  pre/post-release periods; historical automatic-microphone attempts are not
  an exact denominator for the new manually activated microphone operations.
- learner_voice_follow_up_text_submit fires once per accepted explicit text
  submission before connection/send. Additional fields: submission_method
  (keyboard|button) and interrupted (boolean). The pending handoff guard dedupes
  rapid re-entry; this is accepted use, not delivery or answer success.
- learner_voice_follow_up_microphone_result fires once when an explicit on/off
  operation settles. Additional fields: enabled (requested boolean), outcome
  (success|failed|cancelled), and the existing bounded error_code. Cancellation
  on navigation or editing settles the original operation exactly once;
  implicit capture cleanup does not create another operation. A generation
  guard prevents late permissions from enabling capture or double reporting.

These two new event series are additive, without backfill or dual writes to
learner_follow_up_submit, whose ordinary-text contract remains unchanged.
Product adoption queries group their counts by surface/method/outcome and use
the existing connection result/end series for session reliability. Tests assert
exact payloads, exclusions, deduplication, all terminal outcomes, and fail-open.

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
- [x] 2026-09-04: Added stable business code `4018` for user/worker/global
      capacity rejection. The client maps only that numeric code to
      `capacity_exceeded`, stops audio, and waits 30 seconds before another
      explicit attempt. This is backoff, not a promise that another tab's
      credential has expired; locally known credential expiry still wins.
      Focused verification passes with 104 backend tests, 94 frontend tests,
      and TypeScript checking, including no analytics or microphone activity
      from clicks during capacity backoff.
- [x] 2026-09-04: Interrupted outputs no longer receive a drain-complete
      command after clearing playback; the accumulator also ignores stale
      completion callbacks for interrupted turns, retaining only heard text.
- [x] 2026-09-04: Keep the Live voice draft separate from text-provider state.
      Live derives its required built-in provider and submits only its voice;
      switching back restores the unchanged external provider, scalar fields,
      and unsaved object inputs. Repeated switches retain the chosen voice.
      The expanded frontend regression suite passes 106 tests, including
      settings round trips and late playback completion, plus TypeScript.
- [x] 2026-09-04: Allow blank generated follow-up prompts in drafts/new
      publications: both transports fall back to the effective course prompt.
      If no prompt exists, token provisioning omits empty content while keeping
      `systemInstruction` locked in the field mask. Credentials/model/voice
      remain required. The later Live-only Course Prompt exclusion below
      supersedes this fallback for voice sessions, not text sessions.
- [x] 2026-09-04: Bound HTTP session provisioning at 20 seconds, stop audio on
      timeout, and apply a 30-second retry backoff. Late credentials are retired
      without opening a socket and still update the known admission deadline.
- [x] 2026-09-04: Retain and queue completed turns before signalling transcript
      backpressure. A backlog larger than one unload batch stops recording but
      drains through ordinary ordered requests instead of dropping the newest
      turn. It never sends an oversized/truncated finalization batch.
      Verification passes with 124 focused backend tests, 112 frontend tests,
      TypeScript, and the full pre-commit gate.
- [x] 2026-09-04: Followed a frontend CI failure to the reconciliation timer's
      early-fire boundary. Reproduced a callback at deadline-minus-one with a
      deterministic clock test, then re-arm the remaining delay instead of
      leaving the terminal turn uncommitted until another event arrives.
- [x] 2026-09-04: Attribute speech coalesced with Gemini interruption to the
      new learner turn while preserving the cancelled answer and original
      question. Cover an answer already marked complete and split/coalesced
      interruption completion frames.
- [x] 2026-09-04: Do not publish usage-only acknowledgements into local history
      without a final user transcript, matching backend persistence. A final
      question with an empty interrupted answer still produces its pair.
      All 119 focused frontend tests and TypeScript checking pass.
- [x] 2026-09-04: Reconciled `main` commit `4a693d8fe` (learner input
      shortcuts) with the Live branch. Retained desktop/mobile text submission
      analytics and shortcut tests alongside mobile readonly voice history;
      adopted the upstream release pin `markdown-flow-ui@0.2.24`.
- [x] 2026-09-04: Keep the saved text model selectable when billable debug is
      unavailable, so trying Live does not trap teachers in an unintended
      selection. Other billable models and text debug controls remain gated;
      tests cover denied/unavailable billing permission and text save analytics.
- [x] 2026-09-04: Reconciled `main` commit `75a105e5d` (credit notification
      email delivery). Regenerated shared documentation indexes and i18n keys
      from both features' source files; no voice runtime behavior changed.
- [x] 2026-09-04: Recover orphaned Redis turn claims only after acquiring the
      session's connection-scoped MySQL write lock. The lock covers reservation,
      history/usage persistence, acknowledgement, and session consumption, with
      a five-second acquisition bound and a fresh DB read context. A terminated
      worker releases ownership; a slow live writer cannot be displaced by a
      timer. No schema or ordinary follow-up behavior changes are required.
- [x] 2026-09-04: Acknowledge already-durable `/turn` retries from persisted
      state without reserving or writing again. Usage-only turns remain without
      history. Cover a lost acknowledgement followed by an over-budget backlog;
      all retained turns drain once. The focused backend suites pass 142 tests
      with one SQLite-only skip; an isolated MySQL run passes all 143 focused
      backend tests, including physical writer disconnect and lock takeover.
      The full frontend suite passes 2,086 tests, plus TypeScript and the full
      repository pre-commit gate.
- [x] 2026-09-04: Preserve the saved empty-value Default model as a selectable
      return target after trying Live without billing debug permission. Match
      ModelList's explicit-default/first-entry resolution, retain all other
      text restrictions, and cover the saved empty value and exact save event.
      All 22 focused model/settings tests pass.
- [x] 2026-09-04: Clear failed-session UI, transcripts, mute state, retry
      timers, and the old anchor on every course/lesson/mode/preview scope
      change, even after transport teardown. Preserve credential admission
      deadlines and existing analytics terminal deduplication; an explicit
      new-scope click supplies the new retry target. All 53 controller tests,
      2,098 frontend tests, TypeScript, and the full pre-commit gate pass.
- [x] 2026-09-04: Pause listen-mode course audio only from an accepted Live
      controller state, not before dispatching a click that admission may
      reject. Preserve synchronous desktop/mobile activation and verify both
      rejected clicks and accepted pause/restore behavior. All 45 listen-mode
      renderer tests pass.
- [x] 2026-09-04: Keep the connection timeout armed until both Gemini setup
      and browser audio activation complete, including resumed connections.
      Abort pending audio setup on teardown, releasing acquired or late-arriving
      microphone streams and closing AudioContext even when another setup
      promise never settles. Synchronous audio API failures also release owned
      resources. All 62 controller/audio tests and TypeScript checking pass.
- [x] 2026-09-04: Preserve the public `lesson_changed` terminal reason when
      clearing scope-local UI, so the listen player cannot restore audio from
      the previous lesson. Verified active course/mode/preview/classroom changes
      together with terminal analytics; all 107 audio/controller/renderer tests
      and the full 2,108-test frontend suite pass, along with TypeScript and the
      full pre-commit gate.
- [x] 2026-09-04: Route a new question's final input and response to the active
      turn when its interim speech has already arrived, even during the prior
      turn's 500 ms reconciliation window. Interim-only speech remains excluded
      from durable history. All 14 accumulator tests pass, covering final-first,
      response-first, and coalesced interim/response ordering.
- [x] 2026-09-04: Start native keepalive fetch synchronously from the shared
      request transport, using the runtime API URL already resolved before
      session admission. Read current auth/language/trace headers at send time;
      preserve shared response handling and ordinary HTTP/SSE preparation.
      Lifecycle regressions use the real transport and configuration cache for
      same-origin and split-domain pagehide, plus end, auth recovery, and cold
      configuration rejection. All 33 focused tests, 2,121 frontend tests, and
      TypeScript checking pass.
- [x] 2026-09-04: Keep the normal validated settings save/close path available
      while the optional follow-up catalog is pending. Preserve existing Live
      configuration and the empty Default model's provider settings without
      metadata; save edited course fields and ignore late catalog responses
      after close. All 27 settings/model tests pass, including exact save-event
      timing/payload, no event on failure, and analytics fail-open behavior.
- [x] 2026-09-04: Preserve confirmed input transcription when ending an active
      turn before Gemini sends `turnComplete`. Keep interim speech excluded and
      retain only acknowledged answer playback. All 76 accumulator/controller
      tests pass, covering explicit end, final playback flush, pagehide, a
      question with no answer yet, and correct exchange analytics.
- [x] 2026-09-04: Preserve an accepted finalization batch across slow writes and
      the request-admission deadline. Reload and compare its immutable binding
      under the DB lock using server admission time, then renew a 300-second
      Redis retention lease before each write. Heartbeats cannot shorten that
      lease; new requests still fail after the existing expiry/grace cutoff.
      Clock regressions cover both expiry boundaries and binding replacement;
      205 focused backend tests pass with two expected environment-dependent
      skips. Full frontend verification passes 2,131 tests and TypeScript.
- [x] 2026-09-04: Cover Redis Lua's 14-digit numeric round trip when a finalizer
      waits for an earlier write. Binding comparison tolerates only 100
      microseconds of expiry rounding, with exact comparison of every other
      field; an actual expiry change is still rejected. Both predecessor cases
      reproduced the rejection before the fix, while all 13 changed-binding
      cases remain rejected. The admission deadline itself is not extended.
      All 215 focused backend tests pass with the same two environment skips;
      76 accumulator/controller regressions and the full pre-commit gate pass.
- [x] 2026-09-04: Ran two additional task-local checks against an isolated
      Redis 7.4.0 Lua engine. Actual reserve/commit/touch/consume scripts retain
      the finalization lease across heartbeat and numeric round trips; the
      HTTP finalizer follows a predecessor and consumes the completed binding.
      DB persistence was stubbed for these checks, and the private Unix-socket
      Redis process was shut down afterward.
- [x] 2026-09-04: Emit only a consecutive ready prefix of terminal turns.
      Later ready turns remain queued while an earlier turn awaits playback or
      reconciliation; normal playback and forced ending both drain in order
      with acknowledged answer text. Five regressions reproduced out-of-order
      reports before the fix, including a strict server-cursor controller test;
      all 91 accumulator/controller/writer tests and TypeScript checking pass.
      The complete frontend suite passes 2,136 tests across 226 suites, and the
      full pre-commit gate passes with no new architecture-boundary violations.
- [x] 2026-09-04: Deployed the reviewed browser-direct tree through PR #2758
      as dev commit `396b3aceb` (Drone #4726). Both API/web images, public HTTP
      health, the public direct-transport bundle, and Redis PING were verified.
      The existing Live flag remained enabled; no ingress/env changes were made.
- [x] 2026-09-04: Reuse the server's existing `GEMINI_API_URL` for token
      provisioning, preserving proxy prefixes and the fixed browser endpoint.
      Reject unsafe URLs and disable redirects/fallback hosts. Seventeen
      targeted cases reproduced the missing configuration before the fix;
      all 97 focused token/route/deployment tests pass afterward.
- [x] 2026-09-04: Remove client-owned `sessionResumption` from token setup
      constraints as well as their FieldMask. Three regressions reproduced
      the mismatch before the fix; all 97 focused tests pass afterward.
      Candidate code using the dev container's existing proxy/key now mints
      a real token (HTTP 200). A client-side direct Google WebSocket using that
      token completes `setupComplete`; neither probe records audio or secrets.
- [x] 2026-09-04: Address the release review's versioned-base compatibility
      case. Reuse an existing terminal `/v1beta` without changing proxy
      prefixes or matching the hostname. Three cases reproduced duplicate
      version segments before the fix; the wider Live selection passes
      160 tests with one environment-dependent MySQL skip afterward.
- [x] 2026-09-04: Deployed the connection fixes through PR #2759 as dev
      commit `3bea8f2f6` (Drone #4729). Verified API/web images, HTTP health,
      token minting, and a synthetic direct Google `setupComplete` handshake.
- [x] 2026-09-04: Fix browser handling of Gemini binary WebSocket messages.
      A new no-audio probe received `setupComplete` in opcode 2, while the
      browser controller discarded every non-string message and timed out.
      Initial and resumed sockets now deliver ArrayBuffer messages for strict,
      synchronous UTF-8 parsing. All 132 tests across nine Live frontend suites
      and TypeScript checking pass, covering binary setup, UTF-8 transcripts/
      audio, malformed input, interruption order, resumption, and exactly-once
      success analytics. The full frontend suite passes 2,139 tests across
      226 suites; the full pre-commit gate, five-locale checks, architecture
      boundaries, and repository harness pass. Deploy the fix to dev before
      microphone acceptance.
- [x] 2026-09-04: Exclude Course Prompt lookup and inheritance from Live at the
      user's request. Preserve configured follow-up prompts, learner language,
      profile formatting, current anchor, and the latest ten turns through the
      shared context builder. Blank prompts and the system-message placeholder
      use a versioned voice default instead. All 22 focused context regressions
      pass across reading/listening and learner/preview sessions; text retains
      its original Course Prompt precedence. Saved course data is unchanged.
- [x] 2026-09-04: The wider Live/text/profile/backend selection passes 201 tests
      with one isolated-MySQL skip, using the repository-pinned Flask/Werkzeug
      from an isolated dependency overlay. Ruff, architecture boundaries,
      repository harness, all five locales, and the full pre-commit gate pass.
      No shared virtualenv or environment configuration was changed.
- [ ] Deploy the Live-only prompt change and validate audible responses on dev.
- [ ] Exercise a real ephemeral token and direct Gemini WebSocket on the dev
      deployment with a valid credential and microphone.
- [x] 2026-09-03: Repository harness and the full
      `lefthook run pre-commit --all-files` gate pass after staging the
      proxy-file deletions.
- [ ] Complete Chrome, Safari/iOS, and mobile Chrome audio acceptance, including
      multi-turn speech, interruption, transcript accuracy, selected voice,
      15-minute ending, microphone release, and listen-audio restoration.

## Surprises & Discoveries

- 2026-09-05: Same-anchor pause resolves the reported collapse incident but
  does not remove the one-valid-credential admission block after a real End or
  anchor change. Google token expiry and application session retirement are
  separate facts. The public [Live AuthToken contract](https://ai.google.dev/api/live#AuthToken)
  describes immutable expiry/setup and creation; it does not expose a revoke
  operation. A claimed browser close is not proof of upstream revocation.
- 2026-09-05: A token response cannot be replayed after response loss without
  retaining the credential. Phase 4 deliberately keeps the no-token-storage
  rule: request idempotence prevents a second mint, but status recovery returns
  metadata only. A separate explicit replacement may consume another bounded
  risk slot. Do not describe these two operations as transparent token replay.
- 2026-09-05: The reported dev incident is not a 15-minute expiry. Sanitized
  API timings show a session created at 06:17:25 UTC, followed by turn/end
  requests around 06:17:35, before the first heartbeat. The displayed retry
  time matches the separately reserved token lifetime plus expiry grace.
  API logs intentionally omit sensitive request bodies and do not establish
  the original browser teardown reason. A cooldown click previously replaced
  that reason with `capacity_exceeded`; do not infer capacity or timeout from
  that UI. No Live persistence exception was logged for the observed turn.
  The learner subsequently confirmed collapsing the panel before the error,
  which explains the current `user_close` teardown and reservation conflict.
  The user approved changing collapse to pause and hiding the internal lifetime.
  Preserve that decision in the amended lifecycle contract above.

- The provider can complete with output transcription but no PCM audio even
  when server and browser setup both request only `AUDIO`. Authorized temporary
  probes with the affected Course Prompt reproduced this; adding one voice
  sentence produced audio in two of three trials, not a reliable guarantee.
  Prompt variants do not establish a single offending phrase or model-internal
  cause. No private course prompt or audio from those probes is stored here.
- Gemini returns JSON in binary WebSocket frames (observed opcode 2), not
  only text frames. Browser WebSockets default to Blob delivery, while the
  controller previously ignored non-string messages. A successful Python
  handshake therefore did not verify that the browser consumed setup. Later
  retries returned AI-Shifu code 4018 because the issued credential's capacity
  reservation outlived the failed attempt; that is separate from its cause.
- The dev API container cannot reach Google's HTTPS endpoint directly. Its
  existing Gemini reverse proxy is reachable, but the original token issuer
  ignored `GEMINI_API_URL`. A healthy deployment and direct browser media path
  therefore did not prove token provisioning worked.
- A real request through the configured proxy reached Gemini but returned
  HTTP 400: setup contains fields absent from its FieldMask. The token setup
  still supplied empty `sessionResumption` despite intentionally leaving that
  field unlocked. Client-settable fields must also be absent from the token's
  constrained setup, not merely absent from the mask.
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
- Calling an async request wrapper during pagehide is not enough: even an
  already-resolved configuration promise suspends before native fetch. The
  shared keepalive path reads the existing runtime cache synchronously (with
  `undefined` distinct from a ready empty/same-origin base) and starts fetch
  before returning to the lifecycle caller. Session admission warms that cache;
  an unexpected cold relative keepalive fails without starting another lookup.
- The Gemini `auth_tokens` resource exposes token creation but no revocation.
  After a credential reaches the browser, closing the AI-Shifu control-plane
  binding cannot prove that the Google socket closed. Capacity therefore has
  to remain reserved until `expireTime`; otherwise one client can overlap an
  old socket and a newly minted credential.

## Decision Log

- Decision (2026-09-05): once a terminal spoken turn already has final input,
  subsequent final-only input starts its successor, including identical or
  text-overlapping questions. Only a missing final input can reconcile into
  that terminal turn; do not infer ownership from text similarity.
  - Why: Gemini input transcription is unordered and carries no turn ID or
    completion marker. The bounded reconciliation window cannot resolve every
    ambiguity when the old input is entirely missing. Preserve explicit known
    boundaries without pretending arbitrary ASR order is fully attributable.
- Decision (2026-09-05): a retired ownership head is not a credential quota.
  Even with rotation disabled, positively undisclosed failures can retry when
  the actual risk ledger is empty; retained uncertain/disclosed credentials and
  rolling mint limits continue to block admission normally.
- Decision (2026-09-05, implemented behind a default-off policy): separate
  one application owner per user from a non-releasable ledger of issued or
  disclosure-uncertain credentials. Initial bounds are three such
  credentials per user, 24 globally, and six per issuing worker; validated mint
  attempts are limited to four per user and 24 globally per rolling minute.
  - Why: normal End/context replacement can use a second credential without
    pretending to revoke the first. Preserve the existing total risk ceiling
    rather than silently doubling provider exposure. This permits an initial
    credential plus two early replacements, not unlimited instant reconnects.
    At saturation, keep the draft and return bounded busy without expiry copy.
    These are code defaults, not a claim of deployed enablement.
- Decision (2026-09-05): keep replacement explicit, with a versioned
  owner comparison, bounded request idempotence, retained retirement receipts,
  and no credential response cache. Pause/resume keeps the same token. Natural
  expiry remains silent and lazy; no continuous-microphone rollover is added.
  - Why: a late End or mint response must never change a newer owner. Avoid
    introducing stored bearer credentials or replaying ambiguously sent input.
    The existing single-credential limit remains authoritative while the
    rotation policy is off; the risk ledger and recovery gate apply either way.
- Decision: a single close operation owns persistence through recovery, with
  a 25-second elapsed-time budget rather than fire-and-forget successor writes.
  - Why: teardown intentionally stops media and heartbeats immediately. A
    healthy 15-second heartbeat against the 45-second binding TTL, plus the
    existing 30-second absolute expiry grace, leaves only a bounded admission
    window. Finalizer/turn/end waits share that deadline; no new request starts
    after it. Retry the earliest pending index before any successor. Exhausted
    connectivity is still a failed save, never a fabricated acknowledgement or
    an end request that consumes an incomplete outbox. The monotonic clock
    prevents local clock changes from extending recovery.
- Decision: omit the Course Prompt from Live only, rather than heuristically
  editing its formatting or teaching rules. Use `prompts/live_follow_up.md`
  as the shared builder's explicit fallback while passing no course prompt.
  - Why: the user explicitly chose not to concatenate the Course Prompt after
    the transcript-only response diagnosis. Preserve the teacher's separate
    follow-up prompt, including its existing standalone override behavior;
    placeholder/blank prompts receive the voice/profile default. Ordinary text
    prompt composition, saved course settings, audio configuration, and native
    safety remain unchanged. This changes no analytics invocation, outcome,
    eligibility, deduplication, payload, or downstream consumer contract.
- Decision: set every Gemini socket's `binaryType` to `arraybuffer` and decode
  binary JSON synchronously in the existing protocol parser, retaining text
  message compatibility.
  - Why: the real provider sends binary JSON. Unlike asynchronous Blob reads,
    synchronous decoding preserves the arrival order of setup, audio, and
    interruption without introducing stale callbacks across resumed sockets.
    Invalid UTF-8 or JSON remains a discarded protocol message, never logged.
- Decision: reuse `GEMINI_API_URL` only for backend token provisioning, with
  the base-plus-`/v1beta` path contract used by Gemini model discovery, also
  accepting an already-versioned `/v1beta` base without duplicating it.
  - Why: existing environments already configure their trusted Gemini proxy.
    Preserve proxy prefixes, require HTTPS without URL credentials/query/
    fragment, and disable redirects to avoid forwarding the API-key header.
    Do not add another environment variable or change the browser's fixed
    official constrained WebSocket endpoint.
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
- Decision (superseded for deadlines and binding retention on 2026-09-05):
  reserve per-worker, global, and per-user Redis capacity for the
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
- Decision (superseded for user-visible clocks and the extra margin on
  2026-09-05): after a credential is issued, disable retry until its expiry plus
  the capacity safety margin and display the eligible retry time in all five
  locales. Re-entry shares that guard; no microphone, API request, or analytics
  attempt starts while the credential reservation is known to remain active.
  - Why: an immediate retry cannot succeed under the deliberately retained
    one-credential-per-user admission limit.
- Decision (2026-09-05, user approved): collapse and temporary hiding pause the
  existing connection, while explicit End/navigation/unload really end it.
  Hide the internal 15-minute lifetime and all expiry clocks. A natural expiry
  preserves the original panel, history, and draft; the next deliberate input
  obtains a fresh credential after bounded history finalization. Use one UTC
  issuance timestamp for capacity and token expiry, with only millisecond
  rounding, and retain authenticated binding through its fixed finalization
  deadline without heartbeat renewal.
  - Why: a normal collapse must not strand the learner behind an unrevocable
    credential reservation. Internal renewal should not become a user task,
    and throttled background timers must not delete valid session identity.
    Keep all existing access checks, single-credential limits, and manual mic
    consent; never silently replay input or create idle replacement sessions.
- Decision: treat credential expiry plus 30 seconds as an admission cutoff for
  new finalization requests, not as cancellation of an already accepted bounded
  batch. Under the existing connection-owned DB lock, compare the binding and
  reload the committed cursor once at the server-captured admission time. Renew
  Redis retention to 300 seconds before each write; ordinary heartbeats may
  extend but never shorten this bounded in-flight retention.
  - Why: teardown has stopped browser heartbeats, and slow persistence must not
    discard the remainder of a valid batch. This does not extend the Gemini
    token, media lifetime, capacity reservation, or authorization for any new
    request. Failed/abandoned writes retain only this bounded lease and still
    obey the existing DB-lock/claim recovery rules.
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
  handoff budget, after retaining and queueing the turns that crossed it. Drain
  an over-budget backlog through normal ordered requests while the document is
  alive; do not send a truncated finalization batch that closes the binding.
  Actual document destruction cannot guarantee delivery of more than the
  browser's keepalive budget. Explicit end/close waits for the bounded final playback ACK
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

The 2026-09-05 pause/input implementation and its verified review corrections
are pushed through `6f28f2916`; its executed CI checks passed. Actual pinned
player acceptance confirms original-panel ownership of narration pause/resume.
Controlled early credential replacement is implemented and locally verified
behind a default-off policy. Main's generated-report conflict is resolved in
`db6b859fe`. Current-head PR checks and review synchronization remain pending;
no deployment or policy enablement occurred. Local regression evidence must not
be reported as physical Gemini/Safari/mobile acceptance or a deployed fix.

The implementation is now aligned with the deployment the user actually has:
the AI-Shifu ingress handles only ordinary HTTPS for Live, while the browser
opens Gemini's own WebSocket. The long-lived provider secret and private follow-up
instruction are not returned to the browser; the returned credential is
short-lived, one-use, and constrained. The old Flask-Sock dependencies,
server-side Gemini WebSocket wrapper, cookie ticket, backend turn accumulator,
Nginx Live location, and gthread startup changes have been removed.

Automated evidence after the pivot currently covers token constraints,
Redis fail-closed behavior, admission and Origin binding, direct-session
lifecycle, report bounds, deterministic/non-billable persistence, protocol
parsing, transcript reconciliation, audio backpressure, interruption,
resumption, retry-only failures, analytics, and TypeScript. Candidate code has
also passed real ephemeral-token issuance through the dev server's existing
Gemini proxy and direct client-side Google WebSocket `setupComplete`. This
synthetic, no-audio check does not establish browser microphone, multi-turn,
or resumption acceptance; those checks remain outstanding. The later binary
frame diagnosis demonstrates why successful network setup alone was not
sufficient: the browser also has to consume that setup response. The protocol
and controller regressions now cover its real binary representation, including
ordered interruption and resumption, but do not replace microphone acceptance.

Live now intentionally differs from text in its base instruction: it never
resolves the Course Prompt and uses a concise voice default instead. Shared
profile, language, anchor, and history handling remain in place. Context
regressions prove the exclusion and unchanged text behavior; they do not prove
that every provider response contains audio or replace post-deployment testing.

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

`src/api/prompts/live_follow_up.md` owns the default Live voice instruction;
`follow_up_context.py` composes it with the same profile and history handling
used by text, without resolving the Course Prompt on the Live path.

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
capacity through the credential lifetime. Build the follow-up instruction and
latest ten turns through the shared context builder, with the Live voice
default instead of the Course Prompt. Mint a Gemini token with `uses=1`, a
30-second new-session window, 15-minute expiry, and a locked effective Bidi
setup. Keep the authenticated Redis binding until the same credential deadline
plus the existing 30-second finalization grace; do not require background
JavaScript timers to renew it. Return only the
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

Every 15 seconds the browser validates control-plane health and authorization
over authenticated HTTPS without extending the binding or credential lifetime.
The independent capacity reservation expires with the disclosed credential,
using the same UTC issuance instant and rounded-up millisecond deadline.
A completed/interrupted turn waits 500 ms for
late transcription and waits for the playback watermark before POSTing. The
backend validates/bounds the report, filters usage to allowed numeric token and
modality fields, writes history idempotently, and forces `billable=0`. On close,
timeout, navigation, or error, stop capture immediately. When the document
remains active, flush playback before creating the final report and POST end
after pending writes. Wait no longer than five seconds for that normal queue;
if it stalls, stop its successors and hand the retained outbox to the existing
idempotent finalizer. Late normal acknowledgements do not duplicate history.
Retry a rejected finalizer up to three attempts with one-second backoff. If
takeover still fails, clear its rejected state and resume/requeue unacknowledged
normal writes on a fresh queue generation, detached from the old unresolved
request. Old queued successors cannot join that recovered chain; a late active
request may acknowledge only once. Never treat rejection as successful
ownership transfer. `finish()` owns and awaits recovery: retry the earliest
unacknowledged turn after a temporary failure or bounded wait, before issuing
any successor. A single monotonic 25-second budget spans all closing requests,
including finalization and binding close, and cannot be extended by a retry.
Pagehide may initiate keepalive during that owned recovery operation.
On unload, synchronously initiate one bounded keepalive
finalization batch instead when the backlog fits. An over-budget backlog stays
in an ordered queue and drains only while the document remains alive, with a
ten-second wait per retry. A failed or stalled retry does not consume the
binding or discard the remaining turns. An offline/over-budget backlog cannot
be guaranteed to survive document unload; it is never silently truncated or
sent in a request the browser will reject. Capacity is not released early.

### Phase 3: embedded experience, privacy, and verification

The shared read/listen parent owns one controller, without a separate dialog.
The existing AskBlock owns history, keyboard input, responsive panels, and its
fullscreen option. Opening it does not activate audio, microphone, or transport.
The first text submission activates playback in the user event stack without
requesting capture. An explicit microphone click also requests capture in that
stack; permission denial leaves keyboard input available. Editing stops capture
without disconnecting. Only explicit microphone activation can restart it.

Compact controls show connection/microphone state, end, and retry. The
microphone sits inside the existing input beside Send, including RTL layouts.
No countdown, lifetime warning, or credential-expiry clock is user-facing.
All failures remain in AskBlock; no Live input enters the ordinary SSE path.
Ending Live leaves the panel open. The original listen custom-action panel owns
pause/resume intent, so ending a session inside the panel never resumes the
course. Panel collapse, temporary document hiding, and audio-ownership handoff
pause capture and output immediately, retaining the same session. Resume only
on deliberate text or microphone input, after playback and authorization are
ready. Discard late output from paused turns and await the worklet watermark
before committing heard history. Actual pagehide, lesson/course/anchor change,
unmount, explicit End, and internal expiry close all media and transport
resources. Natural expiry retains panel/history/draft without an error; the
next explicit input starts a fresh session after bounded finalization of the
previous history. Do not replay already-sent input or auto-enable capture.
No deployment settings or production environment change in this phase.

Maintain disclosure, five locales, privacy copy, and the existing event family:
`learner_voice_follow_up_attempt`, `learner_voice_follow_up_result`, and
`learner_voice_follow_up_session_end`. Include production guest/member learners
in read/listen; exclude teacher preview and classroom. Keep analytics best
effort and independent from the user-visible operation.

### Phase 4: bounded credential rotation (implemented; disabled by default)

This amendment is authorized by the user's 2026-09-05 response permitting a
capacity-contract adjustment. It supersedes the single-valid-credential rule
only when implemented and enabled. Keep the direct Gemini media plane, locked
token setup, fixed internal expiry, original AskBlock, explicit microphone
consent, Course Prompt exclusion, and non-billable persistence. Do not change
deployment configuration or enable the policy as part of this revision.

#### Ownership and risk bounds

An application owner is the one session our authenticated control plane accepts
as current for a user. A credential reservation represents a Google token that
may still be usable, even after that owner is retired. They are not the same
resource. The backend cannot prove that a modified direct browser closed its
old Gemini socket. Guarantee one logical owner, not one physical Google socket.

| Resource | Initial default | Release rule |
| --- | --- | --- |
| Application owner | One per user | Authenticated End or compare-and-swap replacement of that exact owner; hard expiry also retires it |
| Outstanding credential reservations | Three per user, 24 globally, six per issuing worker | Fixed credential expiry; only positively undisclosed failures may roll back early |
| Validated mint attempts | Four per user and 24 globally per rolling 60 seconds | Rolling server-time window; provider failures count, exact idempotent duplicates do not |
| In-flight issuance | One per user | Bounded operation deadline or terminal completion, guarded by owner revision |

Existing global/worker limits remain total credential bounds, not additional
limits on top of 24 active users. Each owner must have a reservation, so logical
global/worker counts cannot exceed those bounds. The worker dimension describes
issuance bookkeeping, not server-side media sockets or threads. Replacements
consume headroom: at 24 outstanding credentials there is no rotation slot, and
one user's third early replacement is refused while their first three tokens
remain valid. This finite tradeoff is intentional; do not promise unlimited
instant renewal. Increasing to 48 globally and 12 per worker would double the
previous credential exposure and requires a separate measured decision.

#### Atomic admission, retirement, and request idempotence

Extend the existing authenticated session POST instead of adding another media
path. Add `operation=create|status` (default `create`), `request_bid`, optional
`replace_session_bid`, and optional
`expected_admission_revision`. Return `admission_revision` with the current
successful response. Use a server-generated opaque ownership revision and
compare the pair of predecessor session BID and revision; a recreated Redis
key cannot make a stale request current again. Bind every operation to user,
normalized Origin, exact course/outline/anchor, preview, learning mode, and its
predecessor. Revalidate permissions and effective Live configuration for every
create. Status authenticates the original user, Origin, and stored target, but
does not require still-valid access to a retired course or a surviving anchor:
it returns only the caller's own operation metadata, never course content.

Use time-bearing UUIDv7 request IDs with a server-validated acceptance window:
at most 120 seconds old and at most 30 seconds ahead of server UTC. Keep terminal
operation tombstones for 20 minutes. An expired ID is rejected before provider
access, including after its tombstone is removed; the same ID cannot become a
new mint later. A bounded stale-ID response may include server UTC for client
clock correction. Correcting an ID is safe only after this pre-mint rejection;
never turn an ambiguous timeout into an automatic new ID. Request IDs and
ownership revisions are control-plane metadata, never analytics dimensions.
Use Redis server time consistently for admission, rolling windows, expiry
pruning, and the accepted issuance instant returned to the token issuer;
different worker clocks must not release risk or extend request validity.

After permission/context preparation, one Redis Lua transaction must prune
expired reservations, validate the operation's immutable binding, check exact
owner or retirement receipt, enforce risk/rate bounds, reserve risk, and claim
one pending successor. All rejections occur before contacting Gemini. A
duplicate ID with a different binding is rejected; an exact duplicate returns
the same bounded operation status without another provider call or rate charge.
`operation_status=rejected` is reserved for a definite pre-admission refusal.
After reservation, provider/binding failures return that operation's current
`failed`, `cancelled`, `pending`, or `issued` metadata. If Redis cannot establish
the status, return a generic failure, preserving the caller's new request ID.
Never label an advanced/uncertain owner as rejected and restore its predecessor:
that would strand the next retry on an obsolete head.
The explicit `status` operation only reads an existing operation record; it
never runs mint admission, creates a missing record, consumes capacity/rate
budget, or returns a credential. Put the original immutable fields inside a
nested `target` object on status requests; omit root `anchor_element_bid`.
This is deliberately invalid as a legacy create so an older worker cannot
ignore `operation=status` and accidentally mint after a lost response.
Authenticate user/Origin and exact target
before lookup. Unlike `create`, status remains valid throughout the 20-minute
tombstone retention even after the request ID's mint window has elapsed.
Existing risk keys stay non-releasable; new versioned user-risk/owner/operation
keys do not replace the existing per-user STRING in place.

Mint outside Lua with a provider wait capped at ten seconds and a total server
operation deadline of 15 seconds, shorter than the browser's existing 20-second
startup budget. Same-ID status retries share that original browser deadline,
leaving time for delivery/setup instead of resetting the clock. Use one server
issuance time for token and risk expiry as today. Commit the
binding and ready ownership only if the operation and revision are still
current and within deadline, before exposing the token. A late provider result
cannot resurrect a cancelled or superseded operation. Reserve before the call:
process crashes, uncertain completion, and uncertain disclosure retain the
reservation conservatively. Confirmed pre-disclosure failure may release only
its own reservation, never a predecessor's, and never refund a provider attempt
from the rolling rate limit. Do not revive a retired predecessor after failure.

Keep the token only in the original successful response; Redis, SQL, traces,
and logs retain no raw or encrypted credential response. Repeating the POST
with the same ID can return `pending`, `issued`, `failed`, or `cancelled` status
plus non-secret session/revision metadata, but cannot replay a lost token.
Bound same-operation status retries within the original frontend startup
budget. An `issued` response without the original token ends that attempt as a
bounded failure, preserving unsent input. A later deliberate retry creates a
new ID and may replace that orphan through the same reservation/CAS rules.
Aborting fetch is never treated as proof the provider did not issue a token.
If the original response and all status responses are lost, preserve the old
request ID even though no session BID/revision was received. The next explicit
retry first performs a bounded, non-minting status lookup with that ID; the
expired startup budget does not prohibit a new user-requested lookup. It may
recover only that operation's session/revision and whether it still matches the
current ownership head. Do not return an unrelated successor as an implicit
takeover target. Only a matching current/retired head allows a fresh-ID CAS
replacement; a stale operation preserves the draft and reports an ownership
conflict. Pending operations must settle or hit their original server deadline
before a successor is admitted. A new retry shares one 20-second startup budget
across status recovery and any subsequent issuance/setup; it never chains new
budgets automatically. If the tombstone no longer exists, do not recreate it or
remint its ID: all credentials it could have issued have expired, and a fresh
initial operation still has to pass current ownership and quota checks.

Authenticated End/finalize may retire only their own owner revision. Keep a
separate retirement receipt until at least the original expiry plus 300 seconds,
even when successful finalization consumes the history binding. It identifies
the predecessor, owner revision, target, and committed-history cursor but
contains no transcript or credential. It cannot authorize another user's or
Origin's replacement, and it is not sufficient by itself: retain the user's
latest ownership head/revision even after its owner is retired. A receipt must
match that current head and may advance it only once. An old predecessor cannot
be reused after its successor has also ended. Keep head/tombstone retention
beyond the request-validity window and any corresponding receipt deadline.
Preserve the existing history-admission cutoff and
bounded accepted-write lease; the receipt is not extended history permission.
Old reports may finish within their original window, but a retired session
cannot regain current heartbeat/media ownership. Late End, finalization, or
stale browser callbacks must not clear a successor. Two tabs attempting the
same predecessor have one CAS winner; the other keeps its draft. A new tab
without a matching predecessor must not silently seize another tab's owner.
An initial create without a predecessor may proceed after the current head is
retired (there is no active owner), subject to all risk/rate limits. Advancing
that head invalidates previous receipts; a stale explicit CAS still fails.

Return a bounded machine reason and server-calculated `retry_after_ms` for
actual risk/rate saturation. Compute when every blocking quota could admit the
request; do not copy the last browser credential expiry or promise admission
at that moment. Ownership conflicts need an explicit ownership action, not a
fabricated retry deadline. Redis unavailable remains Live fail-closed, with
ordinary HTTP and text follow-ups unaffected.

#### Frontend operation and playback contract

Keep same-anchor collapse/background pause and explicit resume unchanged:
neither creates a credential, asks for capture, or starts connection analytics
just because the panel opens. For a real End or context change, synchronously
isolate old callbacks, stop microphone/output, capture the played watermark,
and close the old socket. Retain the predecessor receipt independently of the
destroyed media attempt. End alone never starts another connection.

On the next valid explicit text/microphone action, activate native playback in
the real click stack, retain only this unsent question, await existing bounded
history finalization, then submit a replacement operation. Do not mint before
a potential 25-second history wait consumes the initial connection window.
Same-context replacement must rebuild server history only after prior pending
turns are durable. Reuse the writer's single per-click closing budget; failure
preserves the draft for another deliberate action. Already-sent input is never
replayed, and old unplayed answers never become new context.

Replace the local token-expiry admission guard with authoritative admission
responses and a single pending operation. All callbacks check controller
generation, target, request ID, and owner revision. A stale response can retire
only its own returned session, never attach capture or playback to a new one.
Only the current explicit microphone action can grant capture; text still
works without microphone permission. Keep original listen-panel audio intent:
an open Ask panel keeps course audio paused, including during replacement.

No lifetime warning, countdown, or token-expiry retry clock returns to the UI.
Show only compact connection progress or a genuine bounded error/retry state.
Natural expiry still cleans up silently; the next explicit input can acquire a
fresh session. There is no idle pre-minting or automatic continuous-microphone
rollover in this first cut. Finite capacity, network, and persistence failures
may still require a retry; do not hide them by discarding drafts or claiming a
successful connection. Busy retry availability is internal state, not a clock.

#### Analytics and compatibility gates

Extend the existing connection-reliability consumer rather than inventing a
second funnel. Its decision remains accepted-connection success and bounded
failure counts in UTC daily/seven-day windows. A replacement passing local
guards and starting connection work is one new attempt, one result, and (only
if connected) one eventual session end. Acceptance is local, not server quota
approval: quota/CAS rejection still produces one failed result. An
internal same-ID HTTP/status retry adds none. A failed old session's late
callback cannot emit for the successor. Existing text-submit and microphone
operation counts still correspond to explicit accepted user actions, not
issuance calls. Same-token pause/resume remains a separate paired transition.

Keep the current exact event names, payload allowlists, guest/member read/listen
population, preview/classroom exclusions, deduplication, and fail-open behavior.
Map quota/rate rejection to existing `capacity_exceeded`; map ambiguous token
response and owner conflict to an existing bounded creation/network outcome,
never raw server text. Request IDs, revisions, credential counts, tokens,
content, model, and voice do not enter product events. At implementation time,
update the canonical analytics spec, producers, and consumer fixture together.
Segment reliability reports at the actual rotation-enable timestamp per
environment: formerly locally blocked attempts can now reach admission, so
historical attempt denominators are not interchangeable. No backfill or dual
write; server-owned capacity telemetry, not Umami, controls quotas.

`GEMINI_LIVE_ROTATION_ENABLED` defaults off. Deploying/enabling it is a
separate authorized operation. The smallest safe rollout is all compatible
backend workers first, temporarily pause new admission with the existing Live
flag, drain legacy issued credentials through their expiry/finalization grace,
then enable the new policy and restore admission. Existing global/worker risk
ZSETs remain shared throughout. If a no-drain mixed-version rollout is required,
implement explicit dual-read/write legacy guards first; do not let old workers
mint around V2 limits or treat an empty V2 namespace as empty risk. Old frontends
without operation metadata retain the non-replacement contract and cannot
bypass V2 ownership/risk checks. Turning rotation off denies new early
replacement but keeps V2 risk accounting and existing-session finalization.
Never roll back by erasing reservations or selecting an empty old namespace.
Rolling back to an old binary that cannot enforce V2 risk is also prohibited
until all V2 credentials drain. If Redis recovers with missing accounting
state, absence is not proof of zero outstanding credentials: keep new issuance
closed for at least the maximum remaining credential lifetime, using a shared
recovery epoch established before reopening. Bootstrap the accounting marker
while admission is disabled; a missing marker after restart/reset triggers this
conservative recovery rather than an empty-ledger bypass. Normal text/HTTP and
already-issued Google credentials do not depend on this new admission gate.
A surviving marker is not sufficient after restoring an older snapshot. Verify
the shared Redis instance/recovery generation on admission; restart, failover,
or restore invalidates it and triggers the same conservative window even when
the marker survives. Risk/owner/operation keys must not be individually evicted:
verify non-evicting storage on admission. The new binary always applies this
generation/noeviction gate, even while rotation is off; otherwise accounting
loss could hide still-valid V2 credentials during rollback. First bootstrap or
a missing/changed Redis run ID starts a shared 15-minute quarantine. Redis
generation and eviction policy are checked inside the admission Lua operation.
A same-process privileged DEBUG RELOAD/RESTORE or selective administrative key
deletion cannot be detected reliably from run ID; prohibit those operations
while admission is enabled. Operators must disable admission and establish a
fresh recovery epoch/quarantine before such restoration. This implementation
does not claim arbitrary privileged partial-restore detection. If these
properties cannot be established, keep Live admission disabled and report the
operational gate; do not silently change Redis deployment settings here.
Non-eviction must hold continuously while credentials are valid, not just at
the instant of a check; a temporary privileged policy change also requires
disabled admission and a complete drain/recovery window before reopening.

Implementation uses `live_follow_up_admission.py` alongside the existing
`live_follow_up_capacity.py`,
`live_follow_up_session_store.py`, `live_follow_up_routes.py`, existing direct
request DTOs/controller/writer integration, their neighboring tests, and the
canonical analytics specification. Redis metadata suffices; no SQL migration,
provider key exposure, token response cache, or media proxy is proposed.

Acceptance must include real Redis Lua concurrent workers/tabs, exact expiry,
three-per-user/global/worker exhaustion, rolling-rate edges, identical/mutated/
expired request IDs, worker clock skew, provider timeout/crash/late success,
response loss (including loss of every status response followed by recovery
after the UUID mint window), stale End/finalize, retirement after consumed binding, replay of
an old predecessor after its successor ends, V1/V2 rollout and rollback, and
Redis fail-closed/accounting loss, including restored markers with missing
newer reservations. Frontend tests must reproduce End/new-anchor immediate
replacement under available budget, paused same-anchor reuse, one pending send,
clock skew, dropped/stale responses, draft/history preservation, no sent-input
replay, manual capture and click activation, output isolation, and exact
analytics payloads/terminal counts/fail-open. Real browser/Gemini and physical
Safari/mobile acceptance remain required for microphone/voice claims. Keep the
admission review open until implemented behavior, not this design, proves it.

## Product Analytics Contract (v2: embedded input)

The [canonical embedded analytics contract](../../product-specs/gemini-live-follow-up-analytics.md)
owns the new input-method consumers, complete payloads, and the deployment-time
break between automatic-microphone v1 and lazy-connection v2. The connection
details below continue to apply except that opening the panel is no attempt:
accepted text submission, explicit microphone activation, or retry starts one.

The existing `creator_shifu_setting_save` remains a successful-save event,
including manual close/autosave while the optional follow-up catalog is still
loading. Settings retain the saved follow-up configuration and mode when its
model is absent from that catalog. Emit once after each successful save, never
on catalog completion, failed validation, or failed persistence. The teacher
population, `save_type`, payload allowlist, aggregate settings-adoption consumer,
and fail-open behavior are unchanged; this restores the existing save path and
needs no new event or consumer migration.

The business question is the share of accepted production learner voice
attempts that connect, their bounded failure outcomes, and whether connected
sessions produce an exchange. An attempt fires after local ID validation and
before playback/session startup. Each accepted connection start or retry is one
attempt. The local retry guard runs before that point: a disabled
retry or re-entry starts no microphone, request, or analytics attempt. For
legacy sessions it retains the old credential-expiry guard; rotation-enabled
sessions rely on server admission. The aggregate attempt/result consumer
and payload allowlist remain unchanged; no retry deadline is shown in the UI.
An API capacity rejection uses business code `4018`, emits the existing bounded
`capacity_exceeded` result, and applies a 30-second explicit-retry backoff when
the occupying credential's expiry is unknown. A stalled session POST is a
`failed` result with the existing `network_error` code after one 20-second
status/issuance/setup budget; the next deliberate retry can recover its stored
operation identity without minting blindly. Late responses never emit another result.
This does not change the capacity error payload. It never infers capacity from
localized or raw error text, retries automatically, or sends another attempt
event while that backoff is active. Older servers without the new code retain
the generic failure path until the server update is deployed.
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
keys; consumers must nevertheless split v1/v2 activation cohorts as documented.

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
8. For the embedded revision, validate locally, update the feature PR, and
   follow current-head CI and review feedback. Do not change deployments.
9. Implement Phase 4 only against the documented two-ledger contract, retaining
   the current single-credential behavior until its compatibility gate is met.
   Resolve the outstanding admission review with regression evidence; a design
   approval or hidden expiry copy alone does not fix it.

## Validation and Acceptance

- Catalog/configuration tests prove text-model isolation, Bidi capability,
  allowlist/flag behavior, provider restrictions, all voice IDs, default Kore,
  preservation across model switching, and resolved lesson mode.
- Token tests assert one use, 30-second connection window, 15-minute expiry,
  exact constrained model/config, private system instruction placement, prompt-
  free browser setup, and bounded provider failure handling.
- Context tests forbid Live Course Prompt lookup in reading/listening and
  learner/preview sessions. Cover blank, whitespace-only, placeholder, and
  standalone follow-up prompts, preserving profile formatting, language,
  anchor, and ten-turn history. Text regressions retain Course Prompt
  composition and precedence over an optional fallback.
- Session tests cover permission and Origin binding, Redis fail-closed,
  capacity acquisition/pre-disclosure rollback/token-lifetime expiry, hashed
  Redis keys, fixed binding retention and heartbeat authorization, consume-once end without early
  capacity release, and no internal AI-Shifu WebSocket route.
- Protocol/controller tests cover setup-before-history, exact Google endpoint
  validation, PCM encoding, over-8-KiB and buffered-frame drops, multi-part
  audio, transcripts, interruption, mute, resumption, session errors, explicit
  retry, cleanup, and analytics exclusions.
- Embedded tests cover panel-open inactivity, text without microphone permission,
  explicit capture success/denial/cancellation, editing release, typed and voice
  interruption, delayed old-turn boundaries, resume-queued input, stable history
  IDs and deduplication, draft preservation, no second TTS, and original layouts.
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
maximum token lifetime. Missed background heartbeats do not invalidate an
otherwise unexpired binding; all requests still enforce its hard access
deadline. End consumes that binding atomically; repeated end is harmless from
the browser's perspective and cannot revoke or release the Gemini credential.

Turn BIDs derive deterministically from Live session and turn index. The
existing persistence transaction makes a repeated report idempotent and rolls
back partial ASK/ANSWER work. A commit failure ends the current controller and
offers voice retry; it does not silently continue with unsaved history.

If the browser socket closes without a usable resumption path, stop the session
and require an explicit retry. An established session may recover one unexpected
close with a current resumable handle, an unexpired token, and no pending typed
handoff. Policy/normal closes, failed setup, non-resumable updates, and a second
unexpected close remain terminal. Never replay typed input automatically.
Heartbeat requests have a five-second bound and one transient retry after one
second. Paused sessions tolerate transient health-check failure; deliberate
resume validates authorization again. Business/auth failures end immediately.
Pause/resume and transport recovery create no
new analytics attempt or session; terminal teardown still emits end once.
If Redis is unavailable, reject Live while text
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

`POST /api/learn/live-follow-up/session/{session_bid}/heartbeat` validates the
trusted control-plane binding without extending its lifetime. `POST .../turn` accepts bounded
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

# Gemini Live follow-up implementation contract

Reviewed against the merged implementation on 2026-09-26. This describes the
supported contract; it does not certify a deployment or physical audio device.

## Input, history and lifetime

Live is embedded in AskBlock, with one controller in the reading/listening
parent and `useAskStateStore` as the message owner. Merge provisional messages
by session, turn and role, then bind the turn-report acknowledgement IDs.
Keyboard input uses `realtimeInput.text`; microphone capture requires explicit
activation. Never replay a question automatically after an ambiguous disconnect.
Use AUDIO-only setup, automatic VAD, native safety and the supported Live model.
Course Prompt remains excluded from Live context; use committed server history.

Collapse or visibility pause releases microphone/audio exclusivity, clears
playback and suppresses late output from the discarded turn while retaining
its played-prefix history. Explicit input revalidates the binding before
resuming. Page exit, scope/anchor change, ending and internal expiry retire the
connection. The listen custom-action panel owns lesson pause/resume; an open
panel must not resume lesson narration. Ending Live does not erase ask history.

## Admission and replacement

Authenticated same-Origin ownership uses revision-checked replacement; concurrent
contenders have one winner, and stale callers never reclaim automatically.
Logical owners and outstanding credentials are separate ledgers. Replacement
retains disclosed or uncertain credential risk until expiry. Rotation disabled
denies early takeover but continues accounting. Never clear ledgers for capacity.

The central configuration registry owns limits: defaults are 96 global
credentials, 8 per user, 24 active owners, 4 user mints/minute and 24 global
mints/minute. Use the five `GEMINI_LIVE_*_LIMIT` definitions in
`src/api/flaskr/common/config.py` and admission boundary tests as the source
when changing them. Older worker quotas in the journal are superseded.
The separate capacity plan owns proposed US overrides and rollout acceptance.

## Verification and analytics

Read the [analytics contract](../product-specs/gemini-live-follow-up-analytics.md)
for exact eligibility, events, payloads and consumers. Analytics must remain
independent from admission, billing and user operations.

Run adjacent Live admission/session and frontend controller/AskBlock tests when
changing behavior. Real-provider, Redis/MySQL and physical browser acceptance
are tracked in `docs/exec-plans/active/gemini-live-voice-follow-up.md`.
The [dated journal](../history/gemini-live-voice-follow-up-through-2026-09-26.md)
retains past decisions and test evidence; it is not an alternate current contract.

# Submit AI answers without waiting for a question

## Purpose / Big Picture

Remove the requirement to wait for a generated question before processing AI
answers. The learner can copy the frozen public prompt, paste an answer and
click Process once. If an ordinary request is already running, the frontend
holds that explicit submission and starts the import at its confirmed cursor,
before automatically generating another block. Pasting alone never submits.

## Progress

- [x] 2026-08-26 UTC: Inspect the existing hook, views, controller, runtime locks
  and replay contract on branch sunner/profile-onboarding-ai-import at b24345f2a.
  The server already imports at any valid unfinished cursor; no new endpoint
  or backend change is needed for the handoff.
- [x] 2026-08-26 UTC: Add the pending explicit submission, attempt-guarded
  handoff and replay/lifecycle regressions. The first test run reproduced seven
  readiness/handoff failures. All 56 conversation/assistant-view tests now pass,
  including early-return and final-summary cursor regressions.
- [x] 2026-08-26 UTC: Remove the question-readiness hint and obsolete locale key
  from all five languages, and regenerate i18n types.
- [x] 2026-08-26 UTC: Verify all 177 frontend suites / 1,528 tests, TypeScript,
  ESLint (existing warnings only), translations and architecture boundaries
  (133 baseline entries, no new violations).
- [x] 2026-08-26 UTC: Verify the official renderer and assistant/save views in
  the real browser at 1280x720 using a temporary local fixture. Early submit,
  content-only handoff, confirmation and disconnected-run replay pass; the
  import uses the same session, original body and next confirmed cursor. No
  extra ordinary block is generated. No live backend, config save or deployment
  was used in this browser check. Remove the fixture after checking.
- [x] 2026-08-26 UTC: Finish repository harness, dev-tool checks and every
  lefthook pre-commit gate. Remove the temporary route/types, regenerate route
  types and re-run TypeScript successfully. Keep the local port 3000 server.
- [x] 2026-08-26 UTC: Prepare verified follow-up publication to ready PR #2669;
  the PR description is the live record for commit, CI and natural-review status.

## Surprises & Discoveries

The frontend currently accepts imports only in awaiting_input/retryable_error,
although the backend validates only the session cursor, prompt, ownership and
unfinished state. Automatically following content-only blocks creates another
race: a scheduled ordinary continuation must not overtake a clicked import.
The final summary is not a collection step; a session already finalizing must
not accept an import that its completed backend session could no longer apply.
An early import can also fail before any question exists. Returning must resume
the same cursor, rather than mark an empty conversation as awaiting input. When
an interaction already existed, preserve it and its unsent input as before.

## Decision Log

- Keep one session and the existing owner/session locks, request fingerprints,
  official final-summary execution and confirmation/save contract unchanged.
- Freeze the accepted raw text and request identifier when the learner clicks.
  Attach the authoritative cursor only after the current ordinary request has
  settled. Do not close an unconfirmed request to bypass server serialization.
- A disconnected ordinary request must replay with its original operation,
  cursor, body and identifier before the held import can start. Keep the held
  text locked on an uncertain result; retain the existing explicit retry action.
- Intercept the first confirmed nonterminal boundary, including a content-only
  welcome block; do not wait for an interaction and do not generate more
  intermediate questions after an import has been accepted.
- Preserve existing behavior after collection has reached its final summary;
  do not offer a new import while the ordinary final summary is already running.
- Remove the readiness text rather than replace it with another waiting hint.
  Processing state begins on the explicit click. Keep errors and retry visible.
- Apply the hook-contract-refactor-safety skill to synchronize the hook, its
  shared conversation consumer and tests. The editor-controlled-sync skill is
  not applicable because this is the renderer/session path, not the editor.

## Outcomes & Retrospective

The learner can submit once during an ordinary run. Its first confirmed
nonterminal cursor hands off to the held import, without waiting for a question.
The old readiness message is gone in all five locales. A disconnected run still
requires explicit retry and preserves both the original request and the held
import. Returning from a rejected early import continues the same conversation.
The prior progress-message removal and public-prompt/admin changes remain intact.
Publishing this follow-up does not authorize a dev/main push or live config write.
Implementation and local validation are complete. CI and natural-review follow-up
remain publication checks; their head-specific outcomes are recorded in PR #2669
instead of claiming that local checks establish deployment or mergeability.

## Context and Orientation

useProfileOnboardingSession owns live requests, their cursor and replay state.
ProfileOnboardingConversation preserves the mounted official renderer and
connects the assistant view. ProfileAssistantAnswersView owns the controlled
paste draft and explicit button. profileOnboardingConversationModel defines
existing session states; the controller owns the final reviewed profile.
profile_research/runtime.py already serializes run and delegate operations.

## Plan of Work

Extend existing tests before changing behavior. Introduce a small held-request
record in the hook rather than another API, session, queue service or summary
pipeline. Guard scheduled continuations with the active attempt and mounted
state. Remove obsolete view props and the readiness key in all five locales,
regenerate i18n types and keep the current no-auto-paste behavior.

## Concrete Steps

Run focused conversation/assistant/dialog/admin Jest, then the full frontend
suite, TypeScript and ESLint. Use the existing local frontend with a temporary
fixture and the official renderer to control in-flight requests without live
LLM or configuration mutations. Run translation checks, architecture, repository
harness, dev tools and lefthook. Keep temporary files out of the commit.

## Validation and Acceptance

An early Process click is accepted once and shows processing immediately.
No import reaches the server before the current run is confirmed. The first
content-only completion hands off using the new cursor without another run or
another user click. Duplicate clicks and later draft changes cannot replace the
accepted body. Disconnect/retry retains the original ordinary request and then
hands off once. Import failures preserve existing correction and replay rules.
Unmount, fatal/expired sessions and final-summary states cannot launch stale
held imports. Ordinary Q&A and no-prompt/admin-preview sessions still work.

## Idempotence and Recovery

No migration or dependency upgrade. Never invent intermediate answers or
reinitialize a session to obtain a cursor. Keep unresolved operations on the
existing retry path. Clear held work on session reset or unmount. Keep the
user's local server running, and remove the temporary route and generated types
after browser checks. Record final publication/CI/review status in PR #2669.

## Interfaces and Dependencies

Only the internal hook/view contract changes. The POST assistant-answers route,
its raw-text/cursor/request-id payload, SSE events and final complete endpoint
remain unchanged. Existing dialogs and admin previews use the same conversation.

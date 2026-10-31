# Keep editor previews in the selected language

> Superseded in part on 2026-10-30: only `sys_user_language` selects preview
> language. The former `language` alias is an independent course variable; see
> [variable scopes](../../references/course-variable-scopes.md).

## Purpose / Big Picture

Teachers must be able to preview a multilingual draft, change language, continue,
and restart without silently returning to Chinese. Preserve learner answers,
course settings, and the existing element protocol.

## Progress

- [x] 2026-10-19 CST: Reproduced missing editor request language and conflicting
  language aliases with a private course snapshot and the real model.
- [x] 2026-10-19 CST: Found that restart also restores the original language.
- [x] Fix request capture, explicit preview language precedence, and restart.
- [x] Simulate user actions locally and verify real Chinese, English and French
  generations, continuation, restart, and the reported audio loading behavior.
- [x] Run developer-tool verification, frontend type checking and repository-wide
  pre-commit checks.
- [x] Open ready-for-review [PR #3146](https://github.com/ai-shifu/ai-shifu/pull/3146)
  after final browser acceptance. Deployment remains outside this change.

## Surprises & Discoveries

The deployed API and web already contain PR #3145. Editor SSE does not use the
shared current-language header helper. Debug variables prioritize the legacy
`language` alias over the visible `sys_user_language` field. Restart restores all
initial variables, including a language that the teacher has since changed.
Production logs available during diagnosis did not contain the reported run.
The editor ignored structured audio errors and premature closure. In addition,
AudioPlayer captured a session ID immediately before playback incremented it,
causing successful and failed synthesis callbacks to be discarded as stale.

## Decision Log

- Keep explicit editor teaching language ahead of interface language; synchronize
  aliases, including when the override is cleared. Use the same policy for both
  editor runtimes and capture it before request-local language is cleared.
- Retain current language settings on restart while dropping subsequent answers.
- Settle audio errors and premature closure, clear every track's streaming state,
  and bind player callbacks to the session created by starting playback. Keep the
  existing playback controls and failure presentation.
- Keep language input bounded to known locales/names, including common names in
  the existing free-text field; never promote arbitrary text into instructions.
- Reuse current preview analytics without adding events: this restores existing
  language and restart behavior, with no new interaction or analytics payload.
- Use isolated local course copies and model calls; production remains read-only.

## Outcomes & Retrospective

Implemented and exercised against an isolated local copy of the reported course.
Chinese, English and French editor previews start, continue after an answer, and
restart in the selected language. English interface fallback works with an empty
teaching-language field and a Chinese saved profile; an explicit French override
wins over the English interface. Course titles and teacher names may remain in
their authored spelling while explanations and interaction labels are translated.

Private real-model acceptance covered 11 generations, including conflicting
aliases and a free-text English language name. The learning suite passed 3,860
tests with one skip. Browser acceptance also found and reproduced a second audio
bug: the player captured its session before starting playback, so its own failed
request was discarded as stale. Capturing the started session lets the player
stop waiting and retry. The local provider-unconfigured error now returns the
button to its playable state on two consecutive clicks. Real audio synthesis was
not accepted because this isolated fixture has no configured TTS provider.

The complete draft classroom also passed English start, continuation and reset,
plus switching existing English history to French for the next answer and a
French reset, then switching French history back to Chinese and resetting in
Chinese. All three languages passed continuation and reset in the full draft
classroom. Editor request capture confirms that continuation retains its debug
session and restart uses a different session without losing the chosen language.
Frontend component regression passed 75 suites / 1,258 tests; the final focused
preview/player suite passed 37 tests after adding partial-stream failure coverage.
Type checking and the repository-wide pre-commit gate passed.

Production was inspected read-only; the reporter's exact request was unavailable,
so these are reproduced defects and local acceptance, not a claim that the exact
production incident or every provider failure has been reconstructed.

## Context and Orientation

`use-debug-session.tsx` owns editor streaming, variable edits and restart. The preview
route selects the legacy context or agent debug session. Agent output-language
policy is configured per request. The classroom uses the separate study transport.

## Plan of Work

Add behavioral regressions, reuse current-language headers, resolve preview aliases
once before streaming, and preserve explicit language edits through restart. Run
local browser and real-model acceptance with the reported course content.

## Concrete Steps

Use conda `ai-shifu` for backend checks, focused Jest tests for the preview hook,
the learning suite and frontend type/lint checks. Run developer-tool verification
and the full pre-commit gate before committing. Push only to GitHub origin.

## Validation and Acceptance

Verify interface language changes with a Chinese browser/profile, explicit teaching
language overriding the interface, conflicting aliases, clearing the override,
continuation preserving session identity, restart creating a new session while
retaining language, and unchanged authored submission values. Exercise Chinese,
English and French with real course content and inspect user-facing output.

## Idempotence and Recovery

No migrations or production writes. Private snapshots, generated outputs and
local runtime data stay outside version control. Stop only task-owned servers.

## Interfaces and Dependencies

No new dependency, protocol, variable key, analytics event or course setting.
The visible `sys_user_language` field is authoritative over legacy `language`.

## PR Review Follow-up (2026-10-19)

Accepted all five inline findings (four distinct issues):

- An explicitly blank canonical language now skips stale legacy language and
  falls back to the request. Legacy-only clients remain supported; resolver and
  both-runtime route regressions cover the clear operation.
- Failed or cancelled audio discards incomplete item and track caches. A test
  renders the real AudioPlayer with the preview hook, delivers a segment followed
  by an error, then clicks play and verifies a fresh synthesis request.
- Stopping, resetting or unmounting preview explicitly rejects in-flight audio
  with AbortError and clears streaming state. Cancellation does not depend on
  callbacks from an invalidated run. Old-source callbacks remain ignored after
  a replacement request starts for the same block.
- Variable edits update the request ref outside React state updaters. StrictMode
  coverage checks batched edits against both visible variables and continuation.

Added descriptive docstrings to the touched Python resolver, context helper and
regression functions. Follow-up validation: 3,865 backend learning tests passed,
one skipped and four subtests passed; 75 frontend component suites / 1,264 tests
passed (42 focused preview/player tests); type checking and lint passed. The
repository-wide pre-commit gate passed.
No new production or live-provider actions were performed for review follow-up.

# Hide extra interaction questions in reading mode

## Purpose / Big Picture

Reading must show interaction controls without appending their separate native
question to lesson prose. This change supplies the shared transport needed for
that rule. Moving listen/classroom questions into panel titles is a dependent,
separate PR. The durable contract is in
[`learner-listen-playback.md`](../../product-specs/learner-listen-playback.md).

## Progress

- [x] 2026-11-04 CST: Preserve the combined implementation and split from the
  latest main. Keep listen/classroom rendering and the global learner content
  normalization unchanged in this PR.
- [x] 2026-11-04 CST: Carry questions as interaction metadata and an inert wire
  fallback, preserving canonical controls, saved answers and older clients.
- [x] 2026-11-04 CST: Hide only the exact metadata-backed fallback at reading
  and Debug boundaries. Update draft classroom history expectations.
- [x] 2026-11-04 CST: Pass 314 frontend cases across reading, printing,
  history, Debug, mode changes and the unchanged main listen renderer; frontend
  type checking and lint also pass.
- [x] 2026-11-04 CST: Pass the full learning backend regression on the latest
  main: 3,601 passed and 90 skipped. All-file repository gates also pass.
- [x] 2026-11-04 CST: Require the shared runtime prompt to ask ordinary course
  and profile questions in visible content before calling `interact`, and
  coordinate profile presentation without duplicate questions. Verify the
  complete offline engine suite and affected hosts: 3,505 cases pass using the
  repository-pinned SDK and graph version 2.53.0 in an isolated test overlay.
- [x] 2026-11-04 CST: Complete original-head CI/review: 16,000 backend tests
  passed (20 skipped), with the compatibility thread verified and resolved.
- [x] 2026-11-04 CST: Rename the unreleased presentation contract to
  `interaction_question`, including producers, consumers, helpers and tests.
  The renamed reading/frontend coverage passes 314 tests, type checking and lint.
  Affected backend learning/Profile coverage passes 564 tests with the pinned SDK.
- [ ] 2026-11-04 CST: Confirm renamed-head CI/review and maintainer acceptance.
- [x] 2026-11-04 CST: The preceding head passed full remote CI with 16,008
  backend cases and 20 skips; both actionable review threads were resolved.
- [x] 2026-11-04 CST: Remove the Profile question fallback at the user's
  direction. Delete prose matching and emit controls only on every interaction
  path, with question wording supplied by the shared question-first instruction.
  All 203 Profile tests pass; the obsolete text-matching matrix is replaced by
  controls-only presentation coverage, retaining recovery and answer contracts.

## Surprises & Discoveries

Removing separate question CONTENT events also removes their independent audio
and marker elements. The transport change is shared: listening still receives
the question inside the interaction body, while authored narration and its
audio remain unchanged. Restoring mode-dependent CONTENT would pollute history
and reintroduce extra questions after a switch back to reading.

Older open bundles ignore new metadata. Their existing ContentRender supports
question text before controls, but raw concatenation can let unfinished HTML
or code consume those controls. Encoding every question code point as a decimal
HTML entity makes that compatibility prefix inert.

## Decision Log

- Keep the title UI, title cache and global learner normalization in the next
  PR. The current main listen renderer continues to see the safe question in
  its existing interaction body.
- Modify only serialized interaction content, leaving DTOs, database rows,
  checkpoints and answer matching canonical. Never infer or delete old prose.
- Reading and Debug remove exactly the prefix encoded from question metadata;
  missing or mismatching metadata does not authorize deleting content.
- The user explicitly requests the question-first instruction for both course
  and profile runtimes. A control title cannot substitute for a visible
  question. Preserve authored choices, navigation, correction stages and
  pending question identities while updating the shared prompt and consumer.
- Profile emits controls only, including ordinary turns, pending restoration,
  rejected answers and queued interactions. The user explicitly removed the
  question fallback; the shared system instruction owns asking the question in
  normal model content. No local prose matching or extra model call is needed.
- This is existing-content presentation and compatibility work, with no new
  user action or analytics meaning. Questions never enter analytics.

- Use `question` throughout the new presentation contract. Keep `prompt` for
  actual model instructions and the pre-existing engine tool/session field;
  the host maps between those layers. The new presentation field has not been
  released, so rename it atomically without a redundant compatibility alias.

## Outcomes & Retrospective

The original CI failure was an obsolete draft-history prose assertion. The
replacement covers title metadata, replay, distinct question IDs and answers.
Split-specific validation and remote checks are in progress. Maintainers own
merge and deployment; no automatic merge is authorized.

The question-first prompt and Profile composition also pass all offline engine
and Profile tests. The historical prompt fixture remains intact; its system
hash gate records this explicitly reviewed runtime change. A stale local SDK
was isolated and aligned with the existing repository pin without changing
shared development dependencies or weakening session compatibility checks.

## Context and Orientation

Course native events are translated by `agent/legacy_protocol.py`, ordered by
`agent/run_agent.py`, and serialized by `learn_dtos.py`. Formal and preview
sidecars persist metadata. Reading uses `ContentBlock`; Debug normalizes before
interaction parsing. Learner shared items deliberately retain wire content so
the unchanged listen/classroom renderer retains visible questions.
The shared engine's `prompts/system.md` supplies course and profile
instructions; `profile_research/engine_runtime.py` projects questionnaire
content and controls and must not echo a question already presented.
It projects every interaction as controls only; it never reconstructs question
wording from pending tool arguments.

## Plan of Work

Keep the shared backend and reading display fix together, independently verify
the unchanged listening surface, then deliver the title UI as a dependent PR.

## Concrete Steps

Run backend learning tests and focused frontend read/history/Debug/real-renderer
tests, type checking, lint and all-file repository gates. Rewrite the existing
PR to this focused branch with a lease after preserving its original history.
Create the separate listen/classroom branch from this commit.

## Validation and Acceptance

Reading on desktop, mobile and print shows controls without the extra question;
streaming, history and mode changes preserve metadata and answers. Debug
parses canonical controls. Older real renderers display inert questions and
submit all four control kinds correctly, including questions with unfinished
HTML/code, literal MDF syntax and emoji. Repeated serialization never changes
stored controls. Listen/classroom title behavior stays with the existing main
renderer in this PR.

## Idempotence and Recovery

No migration or dependency bump is required. The complete original branch is
preserved before splitting, and remote history updates use an exact lease.
Older records lacking metadata remain readable without guessed prose edits.

## Interfaces and Dependencies

Optional `interaction_question` metadata carries original question text. The wire
prefix is decimal HTML entities for every Unicode code point plus two actual
newlines. Python `ord` and JavaScript `Array.from`/`codePointAt` must agree.
The dependent PR consumes the same metadata for listen/classroom titles.

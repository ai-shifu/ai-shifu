# Restore authored text inputs in lesson previews

## Purpose / Big Picture

An authored text-only question can appear as a Submit button with no input when
its model-generated interaction puts the author's hint in `prompt` and omits
`placeholder`. Preserve the authored hint in newly generated and restored
pending interactions so the existing learner renderer displays the input.

## Progress

- [x] 2026-10-09T07:17:00Z: Confirm the failure in two read-only production
  preview cache records and the authored script. Eight new regression cases
  fail before the fix.
- [x] 2026-10-09T07:19:00Z: Restore missing hints using authored prompt matches
  for the same variable. Cover cached pending
  questions, unnamed answers, named memory, ambiguity and escaped hints.
- [x] 2026-10-09T07:20:00Z: All learning tests pass: 2,853 tests, one skip,
  four subtests. Repository developer-tool and all-file gates pass.
- [x] 2026-10-09T07:24:00Z: Open PR #3061. Initial sim verifies two replicas
  with 39 hashes each, 28 isolated regressions and both production examples on
  each replica. Actual pinned UI renders the repaired input and submits text.
- [x] 2026-10-09T07:26:00Z: Reproduce the AI review finding that a unique-hint
  fallback changes unrelated follow-ups; remove the fallback and retain exact
  authored prompt matching only.
- [x] 2026-10-09T07:27:00Z: Final learning suite passes 2,854 tests, one skip,
  four subtests, including the unrelated-follow-up regression that failed before
  removal of the fallback. Add focused test/helper docstrings for review coverage.
- [ ] Revalidate the final review fix in sim and reply to AI opinions.

## Surprises & Discoveries

The authored lesson contains several unnamed text-only questions. Choosing the
first authored question would silently assign the wrong hint. Both observed
preview records copy the correct hint into `prompt`, so an exact source match
can recover it without guessing. The frontend treats a missing placeholder as
a confirmation control; the question prompt alone cannot create a text input.

## Decision Log

- Restore only missing or empty placeholders on text-only interactions without
  choices. Preserve explicit placeholders, choice controls and variable identity.
- Require an exact raw/decoded authored hint match against the model prompt.
  A unique hint alone does not identify an unrelated follow-up, so it must not
  change the placeholder. Duplicate identical authored hints remain safe.
- Apply the existing normalizer to restored pending questions as well as new
  tool calls. No cache deletion, schema migration or course edit is required.
- Keep genuinely ambiguous or unauthored hints unchanged. General empty-hint
  library behavior is outside this source-backed repair.
- This repairs the existing input path and its existing analytics contract;
  it adds no new frontend action, event or payload.

## Outcomes & Retrospective

The initial 2,853 learning regressions and repository gates pass, as do sim
source-backed replay and browser input/submission checks. The review-identified
unrelated-question boundary passes the final 2,854 learning tests; final sim
revalidation is pending. Production evidence and course content remain private and read-only.

## Context and Orientation

`engine/tools.py` parses authored text hints and normalizes `InteractionSpec`.
`engine/engine.py` applies it again before answering a restored pending question.
`agent/legacy_protocol.py` renders the spec into the existing MarkdownFlow UI
notation. The renderer needs the authored hint in that notation to show an input.

## Plan of Work

Extend the existing source-backed normalizer, clarify the v1 syntax prompt, and
verify new and old pending interactions with the real engine/session/protocol.
Run the mandatory offline engine suite within all learning tests, then deploy
the reviewed source to sim and replay private production examples in isolation.

## Concrete Steps

From `src/api`, run `python -m pytest tests/service/learn/ -q`. At repository root,
run `python scripts/check_dev_tools.py` and
`lefthook run pre-commit --all-files`. Open a focused PR against main. Merge the
feature into sim, preserving unrelated approved sim work, and verify installed
runtime hashes and source-backed input recovery before requesting human merge.

## Validation and Acceptance

A missing hint must produce `?[...Your answer]`, retain the correct hint among
several unnamed questions and accept actual text after session reload. Empty
submission on an old cached question must re-emit the repaired input without
altering conversation history. Explicit custom hints, different variables,
choice questions, fenced examples and unmatched ambiguous hints must stay intact.

## Idempotence and Recovery

Normalization is idempotent: a repaired nonempty placeholder is preserved.
Rollback the code to undo the change; no persisted schema or production content
is modified. Sim diagnostics use isolated objects and new test learners only.

## Interfaces and Dependencies

No new dependency or protocol field. Reuse `InteractionSpec`, the authored
question parser, session serialization and the pinned MarkdownFlow parser/UI.

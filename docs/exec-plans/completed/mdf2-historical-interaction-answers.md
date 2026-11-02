# Restore historical MDF 2.0 interaction answers

## Purpose / Big Picture

Reopening a studied lesson must show the learner's submitted text and selected
options. MDF 2.0 already keeps those inputs in durable turn checkpoints, but the
history reader only projects answers from legacy interaction blocks. Its content
blocks correctly remain excluded: their generated text is teacher prose.

## Progress

- [x] 2026-10-12: Confirm missing historical defaults against a read-only production snapshot.
      Both reported text controls retain their original submissions. Keep private
      identities, classroom data and evidence outside the source repository.
- [x] 2026-10-12: Reproduce six failures with the original reader, covering text, single and
      multiple choices, mixed inputs and repeated use of the same variable.
- [x] 2026-10-12: Project the following turn's raw submitted values onto the preceding turn's
      exact controls within the same learner/course/lesson/progress attempt.
      Reject malformed checkpoints, unmatched controls, unusable submissions,
      confirmations and inactive/deleted or unrelated records. Preserve legacy
      answer reading and avoid taking answers from teacher prose or current memory.
- [x] 2026-10-12: Use existing structured renderer defaults to preserve commas in option values
      and newlines in text. The installed renderer restores all four control kinds
      across unmount/reopen without submitting an answer.
- [x] 2026-10-12: Focused validation: 88 related backend cases and 7 renderer cases pass;
      the private snapshot projects 24 controls, including both reported controls.
- [x] 2026-10-12: Broader validation passes 3311 learning cases, four subtests and
      one expected skip, frontend type checking, developer tooling and all-file gates.
- [x] 2026-10-12: Codex identifies block-level answer attribution for parallel
      controls and locale-dependent default hints. Three new database cases fail
      before the correction. Match ordered interaction elements to checkpoint tool
      identities, preserve each queued question across re-display, and take only an
      omitted default hint from its persisted control. Twenty-four focused cases cover these boundaries, including a reproduced
      provider tool-ID reuse regression. Preserve identities only while the original
      deferred queue remains unanswered; new questions cannot overwrite old answers.
- [x] 2026-10-12: Devin also reproduces blank-progress element compatibility.
      Resolve that attempt from its active owned generated block; a foreign-owner
      block cannot supply a scope. Expose the existing turn-record reader publicly,
      load only projection columns and roll back failed test sessions before cleanup,
      addressing the three CodeRabbit review-summary suggestions. All 3317 learning
      cases pass, with four subtests and one expected skip.
- [x] 2026-10-12: Corrected sim 68a2f77ad, build 586 / Drone 5375, is Ready
      on both APIs and the web replica; five relevant file fingerprints match on
      each API. The merged candidate passes 3409 learning cases, four subtests,
      one expected skip and all-file gates. A read-only internal learner comparison
      restores three submitted text controls, preserves the fourth pending control
      and every other history field, matches original checkpoint inputs, and is
      stable across repeated reads. No teaching request or database write occurs.
- [x] 2026-10-12: Complete final-head CI; runtime is still pending on functional
      commit e98e98ead while backend/frontend/static/security checks pass. Closed at archival on 2026-10-29: #3119 is merged into main and deployed with it, so this review, merge or rollout step no longer applies.
- [x] 2026-10-12: Open Ready for Review #3119 and reply to all four inline findings
      in their original threads, plus each of three CodeRabbit review-summary
      suggestions in the original PR conversation with a link to that review.
      Accepted replies cite pushed e98e98ead and the passing validation.
- [x] 2026-10-12: Maintainer merge and production rollout; no automatic merge. Closed at archival on 2026-10-29: #3119 is merged into main and deployed with it, so this review, merge or rollout step no longer applies.

## Decision Log

Use a read projection, requiring pending-control evidence and adjacent active
turns in the same classroom attempt. Bind each ordered interaction element to its
checkpoint tool identity so parallel identical controls retain separate answers.
For an omitted input hint, compare with the persisted original hint, preserving
all authored options, variables and explicit placeholders across locale changes. This repairs existing records without database
writes or migrations. Follow-up Ask/Answer blocks do not advance the lesson turn
chain. Missing or ambiguous evidence leaves a control empty rather than inventing
an answer. Existing history DTOs and renderer structured-default support carry the
answer; no new protocol, dependency version or learning action is introduced.

The change restores an existing history display contract. It adds no user action,
state transition or invocation path and changes no analytics trigger or payload;
no new event is necessary. Answers remain outside analytics.

## Validation and Acceptance

Run the database reader regressions, neighboring history/rewind tests, broader
learning tests, installed renderer tests, developer tool check and all-file hooks.
On sim, use isolated internal learners and read-only history requests. Confirm the
image and loaded code before claiming deployment validation. Existing failed hint
probes and incomplete natural-compression acceptance remain tracked separately in
`mdf2-broader-classroom-acceptance.md` and are not changed by this display fix.

## Surprises & Discoveries

The original reader fails six new recovery cases while twelve isolation/legacy cases
pass. Structured single-choice defaults additionally need `buttonText`; real renderer
coverage caught that omission before commit. A first test collection used the wrong
reader function name and was corrected. The first full gate rejected missing ExecPlan
sections; complete the required plan structure before rerunning.

## Outcomes & Retrospective

The local reader restores historical submissions without changing persisted data.
Technical checks and the private read-only projection support the fix. Review
findings have regressions and replies. Corrected sim history requests verify actual
text recovery, while installed renderer and database tests cover single/multiple
choices and mixed inputs. Final CI and maintainer-controlled production rollout
remain outstanding. The first deployment check rejected a rolling mixed-image
state; verification succeeded only after both APIs and web were ready.

## Context and Orientation

`learn/elements/history.py` enriches persisted interaction element payloads for both
reading and listening history. MDF 1.0 stores an answer in its interaction block.
MDF 2.0 stores teacher text in a content block and the request values plus pending
interaction in the following turn's `agent_turn` checkpoint, read by `agent/rewind.py`.
`ContentBlock.tsx` already passes payload-derived `user_input` to the renderer.

## Plan of Work

Add a narrowly scoped read projector in `agent/interaction_history.py`, call it from
the shared history enrichment loader, and preserve legacy behavior. Validate durable
reader results and actual installed renderer defaults, then deploy an independent PR
candidate to sim. Keep feedback-phase acceptance in its separate active plan.

## Concrete Steps

From `src/api`, activate conda `ai-shifu` and run `pytest tests/service/learn/ -q`.
From `src/web`, run `npm test -- --runInBand
src/__tests__/markdown-flow-mixed-interaction.test.tsx` and `npm run type-check`.
From the repository root, run `python scripts/check_dev_tools.py`, generate the
knowledge index after staging this plan, and run `lefthook run pre-commit --all-files`.
Push to GitHub origin, open Ready for Review, inspect all three AI comment surfaces,
and reply in each original thread. Merge only into sim for candidate verification.

## Idempotence and Recovery

History projection is read-only and repeated reads return the same defaults. No
migration or backfill is necessary. If evidence is absent or mismatched, omit the
answer rather than guessing. A deployment rollback changes only display behavior;
all original checkpoints and submitted inputs remain durable.

## Interfaces and Dependencies

Reuse `ElementPayloadDTO.user_input` and the installed renderer's existing structured
`selectedValues`, `inputText` and `buttonText` defaults. No DTO, dependency or schema
change is required. The projector reads typed specs and answer normalization from
the portable engine but does not modify engine behavior or make model requests.

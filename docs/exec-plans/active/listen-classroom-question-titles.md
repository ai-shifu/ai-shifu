# Show interaction titles in listen and classroom modes

## Purpose / Big Picture

Listen and classroom modes must display a native question prompt as its
interaction panel title. This dependent PR builds on the reading and shared
transport change in [PR #3336](https://github.com/ai-shifu/ai-shifu/pull/3336).
It contains no backend or storage changes. The canonical display contract is
[`learner-listen-playback.md`](../../product-specs/learner-listen-playback.md).

## Progress

- [x] 2026-11-04 CST: Split the title presentation from the reading PR and
  base this branch on its validated reading commit.
- [x] 2026-11-04 CST: Use each active interaction's metadata as its title,
  normalize the compatibility body prefix and invalidate cached titles.
- [x] 2026-11-04 CST: Include history, mode-switch, same-ID update and actual
  installed-player literal-title regressions.
- [x] 2026-11-04 CST: Pass 305 focused frontend cases across eight suites,
  type checking, lint and formatting; independent split-scope review passes.
- [x] 2026-11-04 CST: Pass all-file repository gates.
- [ ] 2026-11-04 CST: Open the dependent PR and verify its final-head CI/review.

## Surprises & Discoveries

The reading PR deliberately preserves the compatibility prefix in shared
learner items so its unchanged listen renderer can show questions in the body.
This PR normalizes those items at their common data entry and also normalizes
direct renderer props before any classification. Without both title wiring and
prefix removal, the question could be missing or shown twice.

## Decision Log

- Consume the existing prompt field and exact-prefix helper from the reading
  PR; do not introduce another protocol, backend change or dependency release.
- Reuse the existing player's `interactionTexts.title`. Display original
  prompt text literally, with no HTML execution or Markdown interpretation.
- Include the prompt in the rendered-element fingerprint so title-only
  updates at an unchanged interaction ID are not hidden by the cache.
- Preserve the localized generic title for missing/blank and system prompts.
- This relocates existing text without a new action or analytics meaning;
  tracking contracts remain unchanged and prompts remain outside analytics.

## Outcomes & Retrospective

The title change is isolated from the reading/shared backend PR. Local and
remote split-specific validation is in progress. Maintainers own merge and
deployment; neither PR is automatically merged.

## Context and Orientation

`ListenModeSlideRenderer.tsx` is shared by listen and classroom modes. Its
current marker supplies the corresponding question, and its element cache
must observe metadata changes. `use-lesson-conversation.helpers.ts` normalizes
streamed/history interaction content; reading and Debug retain their existing
defensive normalization from the base PR.

## Plan of Work

Apply only title presentation, cache and learner-normalization consumers on
top of PR #3336. Verify both modes and the inherited reading contract, then
publish with the reading branch as the PR base.

## Concrete Steps

Run focused renderer, history/hook, reading, Debug and installed-player tests,
frontend type checking and lint, and all-file repository gates. Push the task
branch, open a ready dependent PR, and track current-head CI and review for
both PRs without merging.

## Validation and Acceptance

The active question becomes the title in listen and classroom modes. Previous
questions, streamed title updates at the same ID and mode switches retain the
correct text and answer. The panel body has controls only, with no duplicate
compatibility question. Reading/printing still hide the extra prompt. Missing
and system questions retain generic titles. The real installed player renders
HTML/Markdown characters literally, while its controls remain visible.

## Idempotence and Recovery

Normalization removes only the exact metadata-backed prefix and is safe to
repeat. The reading PR remains independently usable if this PR is delayed or
reverted: questions remain visible in its listen/classroom interaction body.

## Interfaces and Dependencies

Depends on PR #3336's `StudyRecordPayload.interaction_prompt` and shared
`stripInteractionPromptPrefix`. Reuses the pinned `markdown-flow-ui` player
API; adds no backend, database, locale or dependency contract.

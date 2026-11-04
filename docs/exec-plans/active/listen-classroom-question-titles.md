# Show interaction titles in listen and classroom modes

## Purpose / Big Picture

Listen and classroom modes must display a native question as its
interaction panel title. This dependent PR builds on the reading and shared
transport change in [PR #3336](https://github.com/ai-shifu/ai-shifu/pull/3336).
It contains no backend or storage changes. The canonical display contract is
[`learner-listen-playback.md`](../../product-specs/learner-listen-playback.md).

## Progress

- [x] 2026-11-04 CST: Split the title presentation from the reading PR and
  base this branch on its validated reading commit.
- [x] 2026-11-04 CST: Use each active interaction's metadata as its title
  and invalidate cached titles when that question changes.
- [x] 2026-11-04 CST: Include history, mode-switch, same-ID update and actual
  installed-player literal-title regressions.
- [x] 2026-11-04 CST: Pass 305 focused frontend cases across eight suites,
  type checking, lint and formatting; independent split-scope review passes.
- [x] 2026-11-04 CST: Pass all-file repository gates.
- [x] 2026-11-04 CST: Open PR #3340; original-head applicable CI passed.
- [x] 2026-11-04 CST: Align all title consumers and tests with the base PR
  presentation-field name `interaction_question`; 305 frontend tests, type
  checking and lint pass again on the renamed base.
- [ ] 2026-11-04 CST: Verify renamed-head CI/review and maintainer acceptance.
- [x] 2026-11-04 CST: Remove the compatibility-prefix consumers after the
  shared producer is deleted; render the original controls directly.
  All 299 focused frontend cases, type checking, lint and repository gates pass.

## Surprises & Discoveries

The user removed the old-frontend compatibility layer. Shared interaction
content is now pure controls and the question exists only as metadata. The
title renderer consumes that metadata directly and does not parse question
text from the interaction body.

## Decision Log

- Consume the existing question field from the reading PR without a prefix
  helper, another protocol, backend change or dependency release.
- Reuse the existing player's `interactionTexts.title`. Display original
  question text literally, with no HTML execution or Markdown interpretation.
- Include the question in the rendered-element fingerprint so title-only
  updates at an unchanged interaction ID are not hidden by the cache.
- Preserve the localized generic title for missing/blank and system controls.
- This relocates existing text without a new action or analytics meaning;
  tracking contracts remain unchanged and questions remain outside analytics.

## Outcomes & Retrospective

The title change is isolated from the reading/shared backend PR. Local and
remote split-specific validation is in progress. Maintainers own merge and
deployment; neither PR is automatically merged.

## Context and Orientation

`ListenModeSlideRenderer.tsx` is shared by listen and classroom modes. Its
current marker supplies the corresponding question, and its element cache
must observe metadata changes. `use-lesson-conversation.helpers.ts` normalizes
streamed/history interaction content with their existing conversion rules;
question text is not injected into or removed from that content in any view.

## Plan of Work

Apply only title presentation and cache consumers on
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
correct text and answer. The panel body has controls only. Reading/printing
ignore the separate question metadata. Missing
and system questions retain generic titles. The real installed player renders
HTML/Markdown characters literally, while its controls remain visible.

## Idempotence and Recovery

Missing metadata retains the localized generic title. The reading PR remains
independently usable if this PR is delayed or reverted: controls and model
narration remain available, without injecting question text into control content.

## Interfaces and Dependencies

Depends on PR #3336's `StudyRecordPayload.interaction_question`.
Reuses the pinned `markdown-flow-ui` player
API; adds no backend, database, locale or dependency contract.

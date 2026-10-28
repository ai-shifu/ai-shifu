---
title: Preserve backslashes before reference-label line endings
status: completed
owner_surface: backend
last_reviewed: 2026-10-28
---

# Preserve backslashes before reference-label line endings

## Purpose / Big Picture

An explicit image-reference label can contain a literal backslash followed by
a physical line ending. Such an image must keep its alt text out of question
options and bare named-answer admission, so existing learner memory remains
available. Image destinations continue to reject physical line endings.

## Progress

- [x] 2026-10-28 14:25 UTC: Located the rejecting label guard and checked the
  CommonMark label grammar against the new PR #3221 review example.
- [x] 2026-10-28 14:34 UTC: Actual renderer passed 633 cases and the complete
  frontend suite passed 4,181 tests on Node 22.23.4. Direct remark AST checks
  verified line endings, container projections and raw-character bounds.
- [x] 2026-10-28 14:34 UTC: Corrected both Python label readers and added
  punctuation/nonpunctuation, matching and malformed reference regressions.
- [x] 2026-10-28 14:34 UTC: Published 0.4.11 and installed it through ordinary
  PyPI resolution. All 32 installed Python modules match release source
  `8fefe475dce9fdbb468bb695ec432c7f42558c08`.
- [x] 2026-10-28 14:37 UTC: With official 0.4.11 installed, all 15,789 engine
  tests and 17 Profile tests passed. All repository gates passed; the published
  component wheel passed 13,276 tests, type checking, lint and build checks.

## Surprises & Discoveries

Backslash-newline is invalid inside an image destination but can occur inside
its reference label. Treating both contexts alike loses a real image and
admits a question whose buttons are never rendered.

## Decision Log

- Preserve a label's backslash when the following character is not ASCII
  punctuation. Let normal physical-line projection process the newline.
- Verify use-site and definition labels, both marker styles, different line
  endings, container continuations and malformed/undefined controls.
- Preserve URL/title syntax, explicit-percent global declarations and existing
  memory/submission contracts. Keep this issue in its own commit.
- Never merge or push changes to main.
- Keep the separately discovered native escaped-pair length correction in a
  second commit. The component already counts both raw characters correctly;
  its existing bound behavior is unchanged by this newline fix.

## Outcomes & Retrospective

Both Python readers preserve literal backslashes before reference-label line
endings, and the installed renderer confirms that matching labels stay images
without question controls. Malformed and undefined labels retain their visible
interaction fallback. Complete consumer and package gates passed. The native
escaped-pair length correction is tracked in a separate focused commit; this
newline fix preserves its previous punctuation-pair counting behavior.

## Context and Orientation

The native `_image_reference_label` lives in
`src/api/markdownflow/engine/marker_context.py`; reference definition projection
lives in `document_blocks.py`. The production Python component contains the
corresponding reader. The installed `ContentRender` regression suite verifies
observable controls and callbacks through the application parser bridge.

## Plan of Work

Use the real remark/rendering pipeline to distinguish valid reference labels
from invalid destinations. Correct the small label-scanning branch in both
Python parsers, publish its compatible release and verify installed consumers.

## Concrete Steps

1. Reproduce the reviewed label and matching definition in both pipelines.
2. Preserve literal backslashes and project subsequent physical line endings.
3. Compare punctuation, ordinary characters, odd/even runs and container cases.
4. Publish the tested component and verify the official artifact's source.
5. Run focused, complete engine, frontend and repository checks; follow the
   resulting application head through CI and live review.

## Validation and Acceptance

Matching valid labels render images with no A/B controls; a following real
question still submits normally. Bare image markers preserve existing memory.
Malformed or undefined labels keep visible interactions, and invalid image
destinations retain their previous fallback. Component, complete native engine,
affected Profile, real-renderer and repository verification must pass.

## Idempotence and Recovery

There is no data migration. Consume an immutable published version only after
registry and source verification. Reverting this focused commit restores the
previous reader and dependency pin.

## Interfaces and Dependencies

Interaction DTOs, stored key identity, browser URL filtering, analytics and the
UI/remark release pins remain unchanged. Only label recognition and the Python
component pin change. The label grammar is defined by
[CommonMark 0.31.2](https://spec.commonmark.org/0.31.2/#link-label).
Component 0.4.11 was published by the
[feature-branch workflow](https://github.com/ai-shifu/markdown-flow-agent-py/actions/runs/40706963708).

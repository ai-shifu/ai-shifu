---
title: Preserve image labels when the renderer filters their URL
status: completed
owner_surface: backend
last_reviewed: 2026-10-28
---

# Preserve image labels when the renderer filters their URL

## Purpose / Big Picture

A syntactically valid image remains an image when the browser clears its URL.
Its label must not expose question options, and a bare marker in the label
must not declare a new answer or exclude an existing learner value from memory.
Both variable marker styles follow the actual renderer's image classification;
explicit percent declarations keep their existing declaration semantics.

## Progress

- [x] 2026-10-28 13:57 UTC: Confirmed review #3221's image URL mismatch against
  the installed renderer's AST and URL transformation paths.
- [x] 2026-10-28 14:03 UTC: Corrected native and production Python image
  classification; retained all destination and title grammar checks.
- [x] 2026-10-28 14:03 UTC: Installed renderer passed 103 cases, including 96 URL
  ownership cases. Native engine passed 14,217 tests plus 17 Profile tests;
  the Python component passed 10,630 tests and its build/type/lint gates.
- [x] 2026-10-28 14:06 UTC: Published 0.4.10 and installed it through the
  ordinary PyPI index. All 32 installed Python modules match the reviewed
  release. The official wheel passed all 10,630 component tests.
- [x] 2026-10-28 14:08 UTC: All repository pre-commit gates and 3,651 frontend
  tests passed. With the official 0.4.10 package installed, the complete engine
  suite passed 14,217 tests and the affected Profile host passed 17 tests.

## Surprises & Discoveries

MarkdownIt's URL allowlist rejects some destinations whose image nodes remain
present in the browser. Using that policy as a syntax test admits invisible
questions and excludes an existing answer that cannot be replaced.

## Decision Log

- Separate image syntax classification from URL filtering in both Python
  implementations, including their shared reference-resource readers.
- Preserve existing destination/title grammar, physical newline rejection and
  incomplete-image fallback. Browser URL sanitization remains unchanged.
- Use real installed-renderer regressions as the observable contract. Preserve
  existing memory for bare label markers and suppress options for image labels
  with either marker style.
- Keep this review fix in one independent commit and never merge into main.

## Outcomes & Retrospective

Both Python implementations classify image syntax before browser URL cleanup.
Valid image labels create no interaction options, and bare label markers keep
existing learner memory available. Actual renderer coverage verifies the same
result and a following real question still submits normally. Destination/title
grammar, malformed-image fallbacks and explicit percent declarations retain
their contracts. The published package and application regression gates passed.
PR #3221 tracks CI and review for the resulting commit; no main merge occurred.

## Context and Orientation

`src/api/markdownflow/engine/marker_context.py` classifies inline resources;
`document_blocks.py` reads reference resources. The production Python package
contains corresponding logic. `src/web/src/__tests__/markdown-flow-variable-bindings.test.tsx`
loads the actual renderer and parser bridge. The exact Python package pin is
in `src/api/requirements.txt`.

## Plan of Work

Correct the native and library implementations together, test memory admission
and options, and verify the browser's resulting image and lack of controls.
Publish from the dependency feature branch, verify its immutable artifact and
consume it without changing the UI release pin or its URL filtering.

## Concrete Steps

1. Reproduce a data-SVG image and representative filtered URL schemes.
2. Remove URL-policy checks from syntax classification and revise regression
   oracles to distinguish syntax acceptance from URL acceptance.
3. Verify named memory, visible controls and malformed grammar controls.
4. Publish the compatible library, verify source identity and update its pin.
5. Run gates and follow CI and live review threads for the resulting head.

## Validation and Acceptance

Valid inline and reference images with filtered URLs must expose no interaction
options. Bare label markers must preserve existing memory. Actual renderer tests
must show an image and no answer buttons or callbacks. Invalid physical
newlines remain visible interactions. Both marker styles pass the complete
offline engine suite, affected Profile tests and focused frontend checks.
Library gates, registry/source verification and repository checks must pass.
The complete frontend suite passed 3,651 tests on Node 22.23.4; its actual
renderer coverage includes 96 URL ownership cases plus submission, replay,
direct-import and malformed-destination controls.

## Idempotence and Recovery

There is no data migration. The exact package version is immutable. Revert the
focused commit to restore the previous classifiers and dependency pin.

## Interfaces and Dependencies

The renderer's URL transformation, interaction DTOs, persisted answer identity
and analytics contracts stay unchanged. Consume the next verified Python
release 0.4.10; keep the released UI and remark parser pins. Its
[feature-branch publication](https://github.com/ai-shifu/markdown-flow-agent-py/actions/runs/40702165187)
completed at release source `adc16606286f13d247f9697cb0ff292117cda8e9`.

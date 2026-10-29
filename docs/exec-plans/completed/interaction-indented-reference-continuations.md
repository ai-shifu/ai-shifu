---
title: Preserve indented consecutive image definitions
status: completed
owner_surface: backend
last_reviewed: 2026-10-28
---

# Preserve indented consecutive image definitions

## Purpose / Big Picture

Keep image-label questions inactive when the installed renderer accepts an
indented definition immediately after another definition. Preserve ordinary
code and paragraph boundaries while supporting both variable marker spellings.

## Progress

- [x] 2026-10-28 18:52 UTC: Live ContentRender confirmed four spaces and Tab
  across both markers and all three line endings: 12 images, no answer controls
  or callbacks, including read-only replay. Native and installed component
  0.4.14 incorrectly expose the questions.
- [x] 2026-10-28 19:03 UTC: Captured 2,180 adjacent renderer cases and
  independent sibling-item controls. The first physical-container predicate
  was too broad for new sibling items and too narrow for logical continuations.
- [x] 2026-10-28 19:08 UTC: Native candidate uses logical reference ownership
  and excludes newly started paragraphs. Independent comparison matched all
  2,180 observed cases plus six sibling/same-item controls, including the eight
  bare-memory regressions. The production mirror independently matched the
  same corpus across full blocks, replacement and answer updates. Complete
  consumer gates remain.
- [x] 2026-10-28 19:15 UTC: Saved 556 representative renderer cases. Focused
  native checks passed 5,753 tests; the frontend binding file passed all 3,299
  tests including 12 new cases, plus type checking and lint. Source is frozen
  before repository hooks and complete consumer gates.
- [x] 2026-10-28 19:22 UTC: Full engine passed 14,887 tests and Profile passed
  17; all ten frozen hashes and the committed tree stayed unchanged. Frontend
  passed all 6,847 tests in 279 suites. Production component passed 13,762,
  source/build/type/repository gates and independent source/fixture review.
- [x] 2026-10-28 19:27 UTC: Published and consumed markdown-flow 0.4.15.
  Official wheel passed all 13,762 tests with strict installed-module guards;
  normal PyPI installation and all 33 source-file bytes matched. Installed
  application acceptance passed 108 cases, and Profile passed 17 again.

## Surprises & Discoveries

The follow-up review on head 3097d58e0 reports that a four-space or Tab-indented
definition can continue a preceding definition. Treat the installed renderer,
rather than a generic whole-document Markdown parser, as the behavior oracle.

Eight lazy-list/blank-line cases already had phantom options at the PR base.
They remain in scope because the new bare binding also admits the answer name
and removes saved memory, despite the UI showing an image with no question.
The base bare syntax did not grant that permission. Preserve explicit-percent
declaration compatibility while correcting the new bare-memory regression.

## Decision Log

- Limit the change to renderer-admitted definition continuation indentation.
- Capture both marker spellings and line endings; retain nearby code, invalid
  definition and paragraph behavior.
- Keep the new fix independent from the completed 0.4.14 corrections.
- Use actual logical reference ownership rather than equal indentation widths
  or the previous physical line alone. Exclude newly started sibling items.
- Keep hooks, dependency installation and full tests in separate phases with
  frozen source hashes. Never merge or push changes to main.

## Outcomes & Retrospective

Renderer-admitted indented definitions now retain the validated logical
reference owner across consecutive and lazy continuations. New list items
remain separate, and generic code-block admission stays unchanged. Both
variable spellings keep their contracts; bare memory remains available when
the rendered page has no question to collect a replacement.

Native, frontend, production component, official-wheel and installed-application
gates passed with independent review. Local implementation acceptance is
complete; exact-head CI and live feedback continue on
[PR #3221](https://github.com/ai-shifu/ai-shifu/pull/3221), without a main merge.

## Context and Orientation

`src/api/markdownflow/engine/document_blocks.py` owns block admission and
reference-definition prefixes. `marker_context.py` uses those definitions to
classify image labels. The production Python component has corresponding
readers. Frontend tests exercise the installed ContentRender bundle.

## Plan of Work

Observe the exact example and a finite matrix of preceding definitions,
indentation, blank lines and containers. Correct only the admitted continuation
path, mirror it in the Python component and verify named-answer behavior.

## Concrete Steps

1. Capture the actual renderer's images, buttons and source fixtures.
2. Implement the bounded context correction with regression tests.
3. Run focused tests, independent review and full consumer gates.
4. Publish and verify the official wheel before consuming its exact pin.
5. Follow the new PR head's CI and live feedback without merging main.

## Validation and Acceptance

Accepted reference images expose no label controls or bare answer permission.
Visible fallback questions retain their binding and collect a fresh answer.
Explicit-percent declarations and ordinary reads keep their existing semantics.
Require the complete offline engine suite, affected Profile checks, frontend
regressions, component suite, repository gates, official-package verification
and independent review before pushing the coordinated update.

## Idempotence and Recovery

There is no migration. Keep captured source fixtures and independent commits.
Verify published artifacts before pinning them; do not rewrite prior releases.

## Interfaces and Dependencies

The named-answer DTO and UI sandbox policy stay unchanged. Only reference
admission and the verified Python component release change. Exact-head CI and
review convergence remain on PR #3221 after local implementation acceptance.

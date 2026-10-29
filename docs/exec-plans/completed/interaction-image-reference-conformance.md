---
title: Match rendered reference-label budgets and triage HTML ownership
status: completed
owner_surface: backend
last_reviewed: 2026-10-28
---

# Match rendered reference-label budgets and triage HTML ownership

## Purpose / Big Picture

Image labels must not create invisible questions or remove an existing bare
answer from learner memory. Verify reference-label budgets and reference
definitions after HTML container exits against the actual installed renderer.

## Progress

- [x] 2026-10-28 14:49 UTC: Independently reproduced a regression from counting
  label line endings. Real ContentRender renders an image for both markers and
  LF/CRLF/CR while the native scanner exposes answer buttons.
- [x] 2026-10-28 15:14 UTC: Verified 1,224 actual-renderer budget observations,
  covering use and definition boundaries, continuations, tabs and Unicode.
- [x] 2026-10-28 15:14 UTC: Both Python readers match all observed budget
  cases. The frontend passed 1,847 real-renderer cases plus type/lint/format.
- [x] 2026-10-28 15:35 UTC: Both Python readers matched all 4,320 additional
  actual-renderer Tab projection observations. Both label projections preserve
  residual virtual padding; the durable native corpus retains 156
  representative cases in addition to the baseline 1,224 observations.
- [x] 2026-10-28 15:11 UTC: Declined generic HTML-container admission. The
  exact reviewed div example renders A/B through the actual UI, matching both
  Python pipelines. A generic closure fix would regress that behavior.
- [x] 2026-10-28 15:18 UTC: Published budget-only 0.4.12. Ordinary PyPI
  installation and all 32 source modules match release
  `0736366c423759a76d9749f5355dd917cacdaa03`; official wheel passed 14,483 tests.
- [x] 2026-10-28 16:00 UTC: Published 0.4.13 after independent review and the
  clean full source gate passed. Its official wheel passed 14,645 tests;
  ordinary PyPI installation and all 32 Python source modules match release
  `9c448d6a4ea50bf1359c42f7cce66c2f457266e5`.
- [x] 2026-10-28 16:00 UTC: Complete frontend suite passed 5,947 tests and its
  actual-renderer suite passed 2,399. Clean-snapshot engine gate passed 17,255;
  the installed 0.4.13 Profile host passed 17 tests. Independent review and all
  repository pre-commit gates passed; helper hashes stayed unchanged.

## Surprises & Discoveries

The installed micromark label factory consumes line endings without increasing
its label budget. Earlier boundary tests incorrectly inferred a cost of one
from normalized raw length. A casefold-equivalent definition exposes the
wrong expectation. Browser-generated observations must determine the oracle.

The new review also identifies ordinary HTML blocks whose container exits
without the closing-line evidence used by reference-definition admission.

## Decision Log

- Use the installed remark and ContentRender pipelines as the observable
  oracle; retain fixtures for use and definition boundaries.
- Count preserved escaped characters while excluding physical line endings
  from the renderer's label budget. Verify whitespace and container projection.
- Account for UTF-16 units, original-column tab stops and definition
  continuation padding. Cache sparse tab widths once per document, with
  deterministic work regressions.
- Reuse container projection's residual virtual padding when a Tab is only
  partially consumed by a container prefix. Validate that padding separately
  from physical characters and wait for independent review before publishing
  the corrected component release.
- Keep the label-budget correction in an independent commit and publish its
  verified component change. Do not apply the proposed generic HTML correction:
  the UI segments sandbox roots, so full-document Markdown AST classification
  is not the observable product contract there.
- The broader HTML ownership discrepancy also affects the legacy percent
  spelling and needs a separate contract change. Keep its evidence and review
  explanation without changing HTML behavior in this syntax-alias follow-up.
- Preserve destination/title grammar, explicit-percent declarations, normal
  substitution, answer identity, browser URL filtering and analytics contracts.
- Never merge or push changes to main.

## Outcomes & Retrospective

Both Python label readers now follow the browser's observed tokenizer budget,
including residual virtual container padding. The initial newline-budget
regression and the later Tab projection counterexample remain covered by
observed fixtures, including the exact image-before-definition source. Valid
image labels preserve existing bare answers; visible questions still collect
fresh answers. The official package, native engine, frontend and repository
gates passed. HTML ownership is unchanged; the reviewed div example stays a
visible named question and its explanatory review thread remains open.

Validation must serialize hooks and test imports. A full run during
partially-staged hook activity had 44 fixture failures. After fully staging an
immutable snapshot, a fresh-cache run passed all 17,255 engine tests and 17
Profile tests, with identical helper hashes before and after. Do not run hooks
that handle partial staging concurrently with these test gates.

## Context and Orientation

`src/api/markdownflow/engine/marker_context.py` reads use labels;
`document_blocks.py` projects definition labels and HTML boundaries. The
production Python component contains corresponding readers. Real renderer
tests live in `src/web/src/__tests__/markdown-flow-variable-bindings.test.tsx`.
The installed `micromark-factory-label` separates line-ending consumption from
its counted string chunks.

## Plan of Work

Capture browser outcomes around label budgets and HTML container transitions.
Correct native and component label readers with those outcomes as regressions,
explain why the generic HTML advice is not adopted, publish one verified
component build and validate the installed application.

## Concrete Steps

1. Record the newline-budget image and neighboring visible-control cases.
2. Compare use/definition labels, physical endings and container prefixes.
3. Independently verify ordinary HTML container-exit reference definitions.
4. Fix and commit each issue separately in native and component sources.
5. Verify the official release artifact, run gates and follow the final PR head.

## Validation and Acceptance

The observed label-budget corpus must match both Python parsers. Valid images
expose no A/B controls and keep bare existing memory available; a real
following question submits normally. Undefined/malformed controls remain
visible. Complete engine, affected Profile, frontend, component, build/type/lint
and repository gates must pass. Official registry resolution and source-byte
identity must be verified before consuming the new component pin.
HTML behavior is preserved. The exact div review example remains a visible
question in the actual UI; the generic AST-based admission advice is declined.

## Idempotence and Recovery

No database migration or stored-data rewrite is required. Each focused commit
is independently reversible. Package versions are immutable and verified before
application consumption.

## Interfaces and Dependencies

The component pin changes after verified publication. UI/remark versions,
interaction DTOs and stored answer identities remain unchanged. PR #3221 tracks
CI and live review after the local implementation gates pass.
The final verified component was published by its
[feature-branch workflow](https://github.com/ai-shifu/markdown-flow-agent-py/actions/runs/40720910703).

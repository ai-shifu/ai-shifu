---
title: Match image questions to rendered titles and reference runs
status: completed
owner_surface: backend
last_reviewed: 2026-10-28
---

# Match image questions to rendered titles and reference runs

## Purpose / Big Picture

Both variable marker spellings must collect an answer only when the rendered
interaction is visible. Use actual ContentRender observations to correct image
title parsing, paragraph state after reference definitions and the ownership
of reference lookups across rendered runs.

## Progress

- [x] 2026-10-28 16:16 UTC: Actual renderer confirmed all three new review
  examples for both spellings: parenthesized image title, definition followed
  by a numbered continuation, and a code fence separating use from definition.
- [x] 2026-10-28 16:29 UTC: Corrected the two title readers and protected
  question-like title text. All 2,466 observed title sources agree; focused
  native gate passed 4,387 tests and frontend passed 270 plus type/lint/format.
- [x] 2026-10-28 16:53 UTC: Corrected definition/paragraph lookahead, including
  no-title and unresolved-destination probes and concrete label/title
  continuation. Focused native gate passed 7,957; frontend passed 392 plus
  type/lint/format. Replaced the old 1,428-case MarkdownIt label oracle with
  actual renderer outcomes. Complete-fence compositions remain in the next fix.
- [x] 2026-10-28 18:16 UTC: Implemented rendered-run reference ownership and
  offset-mapped HTML normalization. Focused native checks passed 11,307 tests;
  4,144 segmentation, 328 HTML, 364 prior block and 216 indented-boundary
  observations agree with ContentRender. Frontend passed 226 scoped cases and
  all 6,835 tests, plus type checking and lint. Independent review cleared
  applied code, 3,081 cache semantic comparisons and eight pressure families.
- [x] 2026-10-28 18:34 UTC: Full engine passed 14,324 tests and Profile passed
  17 on a clean committed snapshot with eight unchanged source hashes. The
  remaining 70-case whole-document reference oracle now uses captured renderer
  outcomes. Frontend and independent implementation gates are green.
- [x] 2026-10-28 18:39 UTC: Published and consumed markdown-flow 0.4.14.
  Official wheel passed all 13,206 tests with strict installed-module guards;
  normal PyPI resolution and all 33 source-file bytes matched. Installed
  application acceptance passed 68 cases, and Profile passed 17 again.

## Surprises & Discoveries

MarkdownIt is not an oracle for these renderer behaviors. The installed UI
accepts an opening parenthesis inside a parenthesized title. It also retains
paragraph-continuation rules after a parsed definition. Rendered runs depend
on both split-content and subsequent rendering paths; ordinary extracted code
and richer native-HTML runs need actual observations rather than assumptions.

## Decision Log

- Ground expectations in the installed renderer and preserve source/outcome
  fixtures. Verify title contents as well as images, controls and callbacks.
- Keep the three fixes in independent commits with focused regression gates.
  Commit only fully staged coherent source; never run hook mutations alongside
  test imports.
- Run the full final source and independent review before approving component
  publication. Verify official artifact source, normal installation and host
  acceptance before consuming its exact release pin.
- Preserve the established character/virtual-padding budget, explicit-percent
  declaration semantics, UI rendering and sandbox policies.
- Never merge or push changes to main.

## Outcomes & Retrospective

Both marker spellings now preserve visible named questions across rendered-run
boundaries while genuine image labels and resource titles stay inactive.
Production consumes the same verified rules in markdown-flow 0.4.14. The
component also independently fixed its remaining cross-heading image-alt span
and classified-content replacement feedback; the native engine already bounded
that alt span correctly. Source, official package and installed consumer gates
passed without changing sandbox rendering or generic unfinished-HTML fallback.

Local implementation acceptance is complete. Exact-head CI and live review
follow-up continue on [PR #3221](https://github.com/ai-shifu/ai-shifu/pull/3221);
no main-branch merge is authorized.

## Context and Orientation

`src/api/markdownflow/engine/marker_context.py` classifies images and references.
`document_blocks.py` projects definitions and paragraph/container boundaries.
The production Python component has corresponding readers. The installed UI's
ContentRender selects Markdown rendering paths after splitting content, so its
actual output defines reference ownership. Frontend regressions use
`src/web/src/__tests__/markdown-flow-variable-bindings.test.tsx`.

The pinned renderer normalizes HTML indentation before parsing each Markdown
run. Child image analysis disables further segmentation and maps its image
ranges back to the original source, preserving marker and substitution offsets.
Pending sandbox suppression is limited to image-label controls; generic
unfinished-HTML fallback and explicit-percent declarations remain compatible.
Element bounds and sole-active-root suffix states are cached per document.
Validated structural-token summaries prove absent or unclosed roots without
treating raw-text or quoted strings as closing tags. Foreign closing tags
disable the root-prefix shortcut. Eight reported pressure families retain
deterministic work bounds alongside finite malformed-transfer comparisons.

## Plan of Work

Capture the three reported examples and adjacent positive/negative cases.
Correct titles first, then paragraph state, then rendered-run lookup. Keep
later patches unapplied until earlier focused changes are committed, avoiding
partially staged source snapshots. Validate the complete final patch before a
single coordinated component release and application push batch.

## Concrete Steps

1. Observe inline/reference title delimiters and literal vs active controls.
2. Observe definitions followed by numbered, nested, indented and blank-line
   continuations before changing paragraph state.
3. Inspect the UI's actual plain and rich rendering paths; observe same-run
   and cross-run references around code and sandbox content.
4. Commit each verified correction independently with its regressions.
5. Run complete gates, verify the published build and follow the new PR head.

## Validation and Acceptance

Valid rendered images retain existing bare memory and expose no image-label
controls. Visible questions preserve their binding and collect fresh answers.
Literal title examples remain literal while a following real question submits.
Reference definitions bind only in the owning rendered run. Both marker styles,
physical endings and container controls must match observed outcomes. Focused,
complete engine, affected Profile, frontend, component, build/type/lint and
repository gates must pass; source hashes must stay stable during full tests.

## Idempotence and Recovery

There is no migration. Each focused commit is independently reversible. Keep
observed fixtures when replacing or removing compatibility handling. Published
versions are immutable and verified before the application pin changes.

## Interfaces and Dependencies

Stored answer keys, interaction DTOs, analytics, UI/remark release pins and UI
sandbox behavior remain unchanged. The Python component release and image
classification helpers change together within this task. CI and live review
follow-up are tracked on PR #3221 after local implementation acceptance.

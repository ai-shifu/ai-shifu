---
title: Define and align MarkdownFlow text variable names
status: active
owner_surface: learner
last_reviewed: 2026-10-23
canonical: false
---

# Define and align MarkdownFlow text variable names

## Purpose / Big Picture

Use complete authored questions as memory keys across the MarkdownFlow
specification, frontend parser/editor/renderer, both Python runtimes and
application definition/submission boundaries. Names are opaque Unicode text
with their edges trimmed, rather than programming-language identifiers.

## Progress

- [x] 2026-10-23 11:31 UTC: Reproduced the original question-mark mismatch and
  mapped editor, rendering, submission and backend memory paths.
- [x] 2026-10-23 12:16 UTC: Prepared the narrower engine-compatible repair in
  [application PR #3160](https://github.com/ai-shifu/ai-shifu/pull/3160),
  [parser PR #41](https://github.com/ai-shifu/remark-flow/pull/41) and
  [component PR #258](https://github.com/ai-shifu/markdown-flow-ui/pull/258).
- [x] 2026-10-23 12:18 UTC: The user explicitly expanded scope to redefine the
  standard with broad text names, retaining trim of both edges.
- [x] 2026-10-23 12:25 UTC: Defined a shared corpus with 123 normalization,
  15 extraction, six interaction, 11 boundary and 11 document-context cases,
  including every trim character.
- [x] 2026-10-23 13:07 UTC: Published the reviewable bilingual specification
  change in [specification PR #11](https://github.com/ai-shifu/markdown-flow/pull/11)
  and prepared [Python library PR #80](https://github.com/ai-shifu/markdown-flow-agent-py/pull/80).
- [x] 2026-10-23 13:23 UTC: Finish the coordinated specification, parser,
  component library, Python library and application changes.
- [x] 2026-10-23 14:20 UTC: Validate initial inline-code and HTML-tag literal
  boundaries across extraction, substitution and streamed controls.
- [x] 2026-10-23 14:28 UTC: Push the core application contract and official
  Python dependency in commit `b39af30641b92629d70f801e263809b9a732b372`.
- [x] 2026-10-23 15:01 UTC: Repair exact-key memory listing/deletion and blank
  optional interaction fields; focused database and protocol regressions pass.
- [x] 2026-10-23 15:49 UTC: Validate indented-code, HTML, math, link-resource,
  heading, container and physical-line boundaries, with bounded incremental
  streaming context; the complete engine/stream/runner gate passes 1,894 tests.
- [ ] 2026-10-23 15:49 UTC: Finish the confirmed quote/list delimiter-boundary
  alignment and reduce the document helper's delimiter/line index allocations.
- [ ] 2026-10-23 12:28 UTC: Validate actual built packages and all affected
  runtime, editor, streaming, definition and persistence paths.
- [ ] 2026-10-23 12:28 UTC: Update PRs and dependency pins with publication
  prerequisites, and complete current-head CI/review verification.
- [ ] 2026-10-23 12:28 UTC: Replace the application development component pin
  with its verified formal release before merging.

## Surprises & Discoveries

- The public specification previously limited names to Unicode letters,
  numbers and underscores. Both Python implementations were more permissive
  and did not agree with the frontend. The current task intentionally replaces
  that old definition rather than describing it as already broad.
- The component library bundles its own parser; overriding only the app's
  top-level dependency does not repair its rendered controls.
- A name can contain interaction operators and Markdown syntax. Tokenization,
  streaming filters and renderer segmentation must treat the entire marker as
  data before interpreting those operators.
- Introducing backslash or quoted-key decoding would reinterpret historical
  keys. Keep both literal. Padding before a closing delimiter represents a
  key ending in a single closing brace without adding escapes.
- Button translation must not replace text inside an assignment key. JSON
  validation templates must serialize keys containing quotes or backslashes.
- Real Markdown parsing must retain container handling, distinguish literal
  replacement characters from NUL input, and make progress through multiline
  markers. An unclosed interaction cannot claim the remaining document merely
  because an earlier marker was closed.
- Database collations can merge distinct text keys even when Python strings
  differ. Definition reuse/hiding now filters exact keys, and memory readers
  group and exclude binary keys before applying existing live-value caps.
- Literal syntax examples such as a code span containing only `{{` must not
  hide a later variable. Document scanning retains complete variable declarations
  inside inline code/HTML as before, while bounding incomplete examples to their
  literal contexts. Native Markdown paragraph, heading and code behavior stays
  in charge outside an actual marker.
- Earlier backends also collected Markdown-escaped openers. Document-stage
  handling now preserves them as literal text, matching Markdown rendering;
  the specification records this deliberate alignment difference. Raw marker
  readers retain their context-free first-closing-pair contract.
- Native Markdown literal regions must stay bounded before an unfinished
  example can claim an outer marker tail. Cross-runtime checks exposed the
  same gap in indented code, raw HTML closing lines, formulas and link titles.
  Complete examples retain the host's existing collection/substitution scope.
- Exact definition admission also requires exact memory settings queries:
  listing and deletion now use the same binary key identity as runtime reads.
  Empty optional tool arguments remain unnamed questions rather than retries.

## Decision Log

- Read each marker from `{{` to the first literal `}}`, without recursively
  reading markers in its body. `}}` remains a reserved sequence.
- Trim the same explicit whitespace set as Python `str.strip()`. Preserve
  FEFF, internal spaces, repeated spaces, case, punctuation and Unicode.
- After trimming, require a nonempty name without C0/C1 controls or U+2028/
  U+2029. Treat dot/bracket/quote/backslash text as literal keys, not code.
- Parse a leading assignment marker atomically before interaction boundaries,
  options, display/value separators or input hints. Its internal closing
  bracket does not terminate the interaction.
- Generate padded markers (`{{ key }}` / `%{{ key }}`) for exact round trips,
  including names ending in a single closing brace.
- Normalize explicit variable-definition create/save inputs using the same
  contract. Do not migrate or silently rewrite existing stored memory keys.
- Preserve exact identity in definition hiding and live memory reads, including
  databases with case/accent-folding collations. Keep the database-side collapse
  before the row cap so repeated answers cannot displace another live key.
- Extend the existing `creator_lesson_preview_click` event with the boolean
  `has_text_variable_keys` to measure accepted preview intent for the wider
  grammar. Keep the existing eligibility, trigger and best-effort behavior;
  never collect authored keys, questions, source text or values. The canonical
  analytics contract defines the denominator and historical missing values.
- Keep the vendored engine independent of the old Python library. Raw name
  helpers remain standard-library-only; document-stage context handling reuses
  the application's existing pinned Markdown grammar. Shared conformance data
  locks equivalent behavior across languages and consumers.
- Never merge into `main`. The component library's release policy requires a
  maintainer merge and explicit confirmation of its exact main commit before
  formal publication. Development builds remain branch-only dependencies.

## Outcomes & Retrospective

The coordinated implementation passes all 166 shared conformance cases.
The core application backend passed 13,090 tests with 112 intentional skips in an
isolated environment using the official PyPI `markdown-flow==0.4.0` package,
including the complete offline engine and exact-key database regressions.
Subsequent application compatibility fixes pass 1,894 engine, streaming and
runner tests, plus 90 focused memory/protocol regressions. The component library
passed 1,992 unit tests and 137 built-package tests against the current parser
candidate. The parser passed 520 Jest tests plus 45 real Markdown AST cases in
each production and development mode. The Python 0.4.1 candidate passed 391
source tests. Final installed-wheel checks and a confirmed delimiter-boundary
and index-allocation follow-up remain in progress. Bilingual documentation builds
and repository-wide core application hooks passed.

Python publication is verified at
https://pypi.org/project/markdown-flow/0.4.0/. The actual wheel's 33 runtime files
match the tested local build byte-for-byte, and its isolated installed suite
also passes all 269 tests. JavaScript publication and final application
integration are still in progress. Python 0.4.1 adds the verified document-stage
compatibility fixes; streaming continuation and final registry-artifact
application checks remain to be completed.
The earlier `remark-flow@1.3.5` / `markdown-flow-ui@0.2.36-dev.1` pins only
implement the original narrow repair and must be replaced with verified
artifacts. The component library's formal-release prerequisite remains a
maintainer merge and human confirmation; no release gate is bypassed.

## Context and Orientation

- The specification source is `ai-shifu/markdown-flow`, bilingual variable and
  interaction pages plus a shared JSON conformance corpus.
- `remark-flow` owns common name/marker helpers and raw Markdown tokenization.
- `markdown-flow-ui` owns editor validation, placeholders, highlighting,
  segmentation and built interactive rendering.
- `markdown-flow-agent-py` owns legacy extraction, replacement, interaction
  parsing, document splitting, translation and validation templates.
- `src/api/flaskr/service/learn/agent/engine/` owns current collection,
  substitution and memory tools; adjacent legacy and streaming adapters emit
  and filter controls before the browser sees them.
- `src/api/flaskr/service/profile/profile_manage.py` persists definitions.
  App editors and preview/onboarding submissions consume frontend helpers.

## Plan of Work

Implement the same contract across every producer and consumer, run the shared
corpus and meaningful end-to-end submission/persistence regressions, build and
publish reviewable packages, then validate the actual registry artifacts in
application integration. Keep release gates intact.

## Concrete Steps

1. Reuse isolated feature worktrees and current application PR branches.
2. Update the bilingual standard and commit the common conformance examples.
3. Implement raw marker readers, exact normalization, atomic interaction
   boundaries and safe serialization in both languages.
4. Coordinate renderer/editor, translation/JSON templates, engine tools,
   streaming filters and profile definition boundaries.
5. Run relevant full offline suites, package checks, type/lint checks and the
   repository harness; validate downloaded package integrity and behavior.
6. Keep PR titles/descriptions synchronized with the broader final scope.

## Validation and Acceptance

The original question renders exactly three buttons and submits its complete
key. Questions with spaces, brackets and option-like punctuation remain one
key, and leading/trailing whitespace is removed exactly once. Internal spaces
and all remaining characters survive definition creation, submission, session
serialization and memory reads. Empty/control-containing keys are rejected.

Every consumer passes the same corpus. Exercise real Markdown AST parsing,
built renderer clicks, editor validation/extraction, every streaming prefix,
legacy translation and engine FunctionModel/session round trips. Existing
identifier, option display/value, selection and code-fence behavior must pass
its established regressions.

## Idempotence and Recovery

No memory migration is required. Generate every lockfile change with
`npm install`; never hand-edit one. Keep local packages, caches and temporary
validation environments under `/private/tmp/`. Do not overwrite existing local
environments or library checkouts. Restore clean library release versions
after development publication, and retain exact registry integrity in app pins.

## Interfaces and Dependencies

Marker readers distinguish an absent marker from a complete invalid marker,
so invalid bodies are skipped atomically and cannot expose nested variables.
Formatters produce padded markers. The wire remains `?[%{{ key }} ...]` and
`{[key]: values}`; no DTO or memory storage schema changes are required.

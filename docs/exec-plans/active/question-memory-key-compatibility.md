---
title: Define and align MarkdownFlow text variable names
status: active
owner_surface: learner
last_reviewed: 2026-10-24
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
- [x] 2026-10-23 16:14 UTC: Finish the confirmed quote/list delimiter-boundary
      alignment and reduce the document helper's delimiter/line index allocations.
- [x] 2026-10-23 16:19 UTC: Verify the published Python 0.4.1 artifact and
      complete all 13,408 application backend tests, with 112 intentional skips.
- [x] 2026-10-23 17:57 UTC: Complete native container, physical-line and
      angle-autolink boundaries; all 2,862 engine, streaming and runner tests pass.
- [x] 2026-10-23 17:55 UTC: Verify the actual `remark-flow@1.4.0-dev.1`
      registry artifact, API/types and 53 AST cases in both production and
      development mode. Current parser-head CI and review checks are complete.
- [x] 2026-10-23 18:10 UTC: Validate actual `markdown-flow-ui@0.3.0-dev.1`
      and `markdown-flow==0.4.2.dev1` registry artifacts. The component passes
      424 installed-package tests, and the SDK passes 982 installed-wheel tests
      plus the original Chinese question answer round trip.
- [x] 2026-10-23 18:10 UTC: Install the exact npm artifacts from the generated
      application lockfile; all 3,337 frontend tests, type checking and lint pass.
- [x] 2026-10-23 18:16 UTC: Pass the full application backend checkpoint:
      14,310 tests with 112 intentional skips using the actual Python dev1 wheel.
- [x] 2026-10-23 18:23 UTC: Cache verified native container bounds without
      changing source scope. All 2,910 engine/stream/runner tests pass, including
      48 new work-count, query-order, partial-line and physical-newline cases.
- [x] 2026-10-23 18:25 UTC: Verify the actual `markdown-flow==0.4.2.dev2`
      wheel with the cache fix: all 1,030 installed-package tests, Chinese answer
      round trip and runtime module/prompt comparisons pass. Pin it in the app.
- [x] 2026-10-23 18:25 UTC: Update ready PRs and feature-branch dependency
      pins with publication evidence and formal-release prerequisites.
- [x] 2026-10-23 18:33 UTC: Pass all 14,358 application backend tests
      with 112 intentional skips using the actual Python dev2 wheel.
- [x] 2026-10-23 18:40 UTC: Restore native link state for disqualified
      question candidates and stream the confirmed resource opener together.
      All 2,946 engine/stream/runner tests pass, including 36 new link-resource
      regressions across all chunk cuts and three physical newline forms.
- [x] 2026-10-23 18:42 UTC: Verify the actual Python dev3 wheel with the
      native-link fallback fix: all 1,066 installed-package tests and the Chinese
      answer round trip pass; pin the verified artifact in the application.
- [x] 2026-10-23 18:53 UTC: Pass all 14,394 application backend tests
      with 112 intentional skips using the actual Python dev3 wheel.
- [x] 2026-10-23 18:57 UTC: Protect complete variable markers before all
      three legacy preserved-output consumers interpret output operators.
      The actual Python dev4 wheel passes 1,131 installed-package tests and
      eight preserved-output process calls using the correct variables keyword.
- [x] 2026-10-23 19:01 UTC: Preserve a real held character when confirming
      inline closure at a stream boundary. All 3,019 engine/stream/runner tests
      pass with the actual Python dev4 wheel, including 73 new arbitrary-cut,
      character-by-character, HTML block-state and bounded-work regressions.
- [x] 2026-10-23 19:09 UTC: Pass all 14,467 application backend tests
      with 112 intentional skips using the actual Python dev4 wheel.
- [x] 2026-10-23 19:17 UTC: Preserve native HTML categories while their
      physical line or tag name is incomplete. All 1,007 focused tests pass,
      including 168 new native-tag, arbitrary-cut and bounded-state cases.
      A generated 1,386-source sweep makes 6,378 comparisons without a mismatch.
- [x] 2026-10-23 19:18 UTC: Pass all 3,187 engine/stream/runner tests with
      the final HTML category correction and the actual Python dev4 wheel.
- [x] 2026-10-23 22:22 UTC: Keep English README labels, documentation and
      examples free of Chinese text and punctuation across all five repositories.
      All 84 English documents and compatibility entries pass the expanded scan;
      dedicated Chinese translations, terminology and multilingual fixtures remain.
- [x] 2026-10-23 22:33 UTC: Preserve original opaque keys during authored input-hint
      preprocessing in `e68aac9f84450b66d8a3a2a0b73ce638a28f7a04`. All 3,247
      engine/stream/runner tests and 128 focused hint tests pass, including exact-key
      input restoration, typed answers, unfinished markers and CR/LF/CRLF behavior.
- [x] 2026-10-23 22:55 UTC: Defer ambiguous streaming questions until their
      native literal settles or reaches EOF, preserving nested HTML and resource
      witnesses. All 3,291 engine/stream/runner tests pass, including 44 new cases;
      third-party validation passes 9,713 streams and long-payload state/work bounds.
- [x] 2026-10-23 23:01 UTC: Complete the full-backend checkpoint on `583da075`:
      14,739 tests pass with 112 intentional skips. All 1,338 tracked API source,
      fixture and configuration hashes remain unchanged throughout the isolated
      run with temporary SQLite and mocked model providers. Remote runtime and
      backend tests also pass on that head; its development-pin gate stays red.
- [x] 2026-10-23 23:19 UTC: Preserve provisional reference-definition ownership
      in `dae598bf58f1524801590fd7ea9d16992387feb1`. All 3,337 engine, stream,
      reference and runner tests pass, including 46 new reference regressions.
      Independent review passes 4,377 streams across 167 generated sources,
      nine long-prefix checks and 20 escaped or overlapping opener cases.
- [x] 2026-10-23 23:25 UTC: Stream irrevocably owned unfinished raw markers
      without retaining their body. All 34 focused tests pass, covering split
      closing pairs, native delimiter runs, opaque body text, restoration of
      later fences and inline code, reuse and bounded parser work and storage.
      Independent measurements across 100 to 16,384 body characters keep held
      source at one character and the raw witness at two; inspected work is linear.
      The 765-test stream, reference and performance gate passes after retaining
      earlier pending native block and container HTML ownership; this restores
      all 12 container dedent cases exposed by the initial broader run.
- [x] 2026-10-23 23:30 UTC: Preserve EOF reuse behavior after emitting an
      unfinished raw marker. Snapshot escape and line-boundary state after
      preceding prose, restore it only for an unfinished marker at flush, and
      retain ordinary state after a real closing pair. All 767 stream, reference
      and performance tests pass, including 36 focused raw-marker cases;
      independent review matches the previous filter across 30 reuse checks.
- [x] 2026-10-23 23:34 UTC: Preserve source order between an earlier native
      fence and a later pending reference marker. All 3,376 engine, streaming,
      reference, performance, fence and runner tests pass, including three new
      physical-newline cases. Final independent review passes 6,145 streams over
      225 sources, 128 fence and 700 container HTML streams, 30 reuse checks,
      and 4,144 long-payload cut checks, with no remaining substantive finding.
- [x] 2026-10-23 23:32 UTC: Start the final full-backend run on the frozen
      reference, performance, EOF and fence corrections. Capture hashes for all
      1,390 API files, including all 1,341 source, configuration and fixture files
      and the new tests. The earlier 23:21 run was interrupted when the fence
      regression was confirmed and does not establish final acceptance.
- [x] 2026-10-24 00:04 UTC: Complete acceptance on `fd60c15b1`: the local full
      backend passes 14,824 tests with 112 skips and unchanged hashes for all
      1,390 API files. Backend CI passes 14,921 tests with 15 skips; both collect
      14,936 tests with different environment-dependent skip eligibility. All
      checks reach a terminal state, with only the known development-pin gate
      failing. Fresh review has no new unclassified feedback.
- [x] 2026-10-24 02:45 UTC: Incorporate main through `dda7becb5` into the
      feature branch to resolve the generated document-inventory conflict.
      Regenerate the inventory from both branches' source documents rather than
      selecting one side. Independent integration review passes 61 capacity,
      observability, Gunicorn, worker-aggregation and learning-stream cleanup
      tests; the metrics wrapper preserves chunks and forwards stream closure.
- [x] 2026-10-24: Verify the earlier `89d2d4d3` integration checkpoint in CI:
      14,938 backend tests pass with 15 skips. Its only failing check is the
      development-version gate; these results predate the next main integration.
- [x] 2026-10-24: Publish and verify `remark-flow@1.4.1` and
      `markdown-flow-ui@0.3.0` through their official workflows. The component
      release comes from human-merged main `6ff0542349bf254a0395afbfaf299b0d3c90d92d`.
- [x] 2026-10-24: Integrate main through `7a23e7c57`, moving the text-name
      implementation and its tests into the independent `markdownflow` package.
      Retain the thin course adapter and Profile's native interaction identity,
      stale-control guards and session transitions. Replace frontend development
      dependencies with the verified formal releases and regenerate the lockfile.
- [ ] Complete the new integration's shared-engine, course, Profile, frontend and
      repository gates, then synchronize current-head CI and review feedback in
      application PR #3160. Never merge the feature branch into main automatically.
- [x] 2026-10-24: Publish Python `markdown-flow==0.4.2` after explicit user
      authorization, using official run `40071222859` from SDK PR #80 at
      `aa4f337517e8b935d42b65d9e69fee36f7767b6f`. Verify the actual PyPI wheel,
      all 34 runtime/resource members, 1,131 installed-package tests and the
      question-key answer round trip, then select the formal application pin.
- [x] 2026-10-24: Fix Profile evidence's raw-versus-canonical binding mismatch
      in independent commit `9c5f6b763`. Padded nickname keys stay excluded;
      punctuation and internal-space keys survive accepted answers and cache
      serialization. Cross-host coverage passes 1,016 tests, including Profile,
      course streaming and exact-key memory boundaries; 41 focused Profile
      binding/runtime tests pass. The shared-engine gate passes 2,643 tests.
- [x] 2026-10-24: Verify the integrated frontend against stable npm packages:
      all 3,364 tests in 273 suites pass, along with type checking and lint.
      Toolchain validation and all-file repository hooks pass.


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
- Preserved-only legacy output has its own admission and extraction path.
  Both must protect variable markers before output directives are interpreted;
  extraction and the ordinary content-message path alone do not prove the
  public process call preserves a key containing directive-like punctuation.
- A real held character can confirm an inline closing run at a stream cut.
  Replay it only for a matching unfinished inline run, preserving physical-line
  block state and limiting replay masks to already emitted source offsets.
- An EOF-admitted generic HTML block is provisional until its physical line
  ends. Preserve that native admission state instead of turning its witness
  into an irrevocable block. The finite HTML lexer also retains native block
  tag prefixes, so partial closing tags and extended names keep their category.

- Authored hint preprocessing previously deleted comment-like key content and
  interpreted code-like padding. Compute exclusion ranges using protected native
  markers and apply them to the original source, preserving exact key identity.
- A provisional literal can later fail and turn its marker into an opaque raw key.
  Defer an ambiguous interaction until native ownership settles. Its necessary
  raw payload may be buffered in chunks; continuation witnesses remain bounded
  and each newly arrived character must incur only incremental parser work.
- Native reference definitions accepted at EOF can still fail when their line
  continues. Preserve the raw opener and escape parity in the existing bounded
  reference witness, and defer questions until that native ownership settles.
- A genuinely unfinished raw marker previously retained and rescanned its whole
  body on every stream arrival. Once ownership is irreversible, its raw text can
  be emitted while retaining only the closing-pair continuation state.
- A source prefix can end inside a later marker while an earlier reference has
  already ended before a native code fence. That later incomplete marker must
  not make the fence provisional. Independent whole/chunk comparison reproduces
  a regression against the unchanged main-branch filter.
- Later main commits added API capacity metrics and rollout documentation.
  Only the generated inventory conflicts with this feature; regenerate from
  the combined canonical documents and validate the shared SSE close chain.

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
- Retain a pending question's necessary raw payload as chunks, but keep only a
  bounded native continuation witness for incremental arrivals. Preserve outer
  HTML/resource state around an inner URI witness. Replay held source once when
  all relevant literal ownership settles, and use final native lexing at EOF.
  An unfinished angle/resource may become an opaque raw marker at EOF rather
  than exposing a question inside its key.
- Include viable reference definitions in the same pending-literal contract.
  Reuse native reference and resource admission; preserve first-opener ownership
  and escaped-opener parity without introducing a separate Markdown grammar.
- Once raw-marker ownership cannot be displaced by an earlier unfinished native
  literal or inline delimiter, emit its body incrementally and remember only a
  possible final single closing brace. Ambiguous literal candidates retain the
  existing deferred classification, and flush clears the incremental raw state.
  An unfinished raw marker restores the previous filter's pre-marker escape and
  indentation state at EOF, preserving behavior when the filter is reused.
- Compare pending reference waits and native code fences by source offset.
  A later unfinished marker cannot retroactively suppress an earlier fence;
  an earlier unresolved marker still blocks a later fence until ownership settles.
- Keep the vendored engine independent of the old Python library. Raw name
  helpers remain standard-library-only; document-stage context handling reuses
  the application's existing pinned Markdown grammar. Shared conformance data
  locks equivalent behavior across languages and consumers.
- Use one document walk to identify inline delimiters rejected at native block
  boundaries, then seed the native parser before it consumes container prefixes.
  A per-processor parser accessor preserves plugin order, parser reassignment
  and copied processors; a synchronous seed stack is restored on exceptions.
  Normalize a document-leading BOM only for native offsets, retaining it in raw
  helper offsets and in variable names. Keep line and delimiter indexes compact.
- Publish development builds for feature-branch integration. Automatic
  approval review rejected formal parser publication because an irreversible
  release was not explicitly authorized; no formal-publication retry or
  alternative route is used. Actual development artifacts are verified before
  pinning them. Release-version gates remain intact for eventual merge.
- Never merge into `main`. The component library's release policy requires a
  maintainer merge and explicit confirmation of its exact main commit before
  formal publication. Development builds remain branch-only dependencies.

## Outcomes & Retrospective

All five repositories pass the same 166-case semantic conformance corpus.
The final corrections pass 3,376 engine, streaming, reference, performance, fence
and runner tests,
including arbitrary chunk cuts, bounded continuation state, 48 container-cache
regressions, 36 native-link fallback regressions and 73 held-lookahead
regressions, plus 168 HTML-category, 60 input-hint, 44 pending-literal, 46
reference, 36 raw-marker and three fence-order cases. The complete application
backend checkpoint on `583da075`
passed 14,739 tests with 112 intentional skips using Python dev4 after the
input-hint and initial pending-literal repairs. Exact-key database and optional
unnamed-question coverage is included. The frozen `fd60c15b1` full-backend run
passes 14,824 tests locally and 14,921 in CI, with the same 14,936 collected total
and different skip eligibility. Integration with subsequent main commits passes
61 focused metrics, worker and stream-cleanup tests. New-head CI and review
readback belongs in the linked PR; prior-head results are not relabeled as new
integration results.
Required toolchain checks, architecture boundaries and all-file hooks pass.
The latest full-backend and remote-CI acceptance are tracked in the remaining
progress item; earlier checkpoints do not establish that final gate.

The actual `remark-flow@1.4.0-dev.1` registry artifact matches the tested runtime
payload, with a version-only package metadata difference. Its API, public types
and 53 production plus 53 development AST cases pass. Component source passes
3,433 unit, 424 built-package and 160 browser tests using that exact parser.
The actual `markdown-flow-ui@0.3.0-dev.1` npm artifact passes all 424 package
tests. Both npm and pinned-pnpm lockfiles select the same parser version;
subsequent component changes are test assertions and lockfile alignment, with
the published production runtime unchanged.

The actual `markdown-flow==0.4.2.dev4` PyPI wheel passes 1,131 isolated installed
package tests, the Chinese question answer round trip and byte-exact runtime
module/prompt verification. Eight preserved-output process calls also preserve
directive-like key punctuation. Its cache reduces the confirmed flat-quote scan
work at 100/200/400 lines from 5,150/20,300/80,600 calls to 200/400/800 calls,
with the same literal and variable boundaries. The application lockfile records
real registry URLs and SHA-512 integrity for both npm artifacts; a clean
installation passes 3,337 frontend tests, type checking and lint.

Published development artifacts are traceable to the official workflows:
[parser run](https://github.com/ai-shifu/remark-flow/actions/runs/39997419199),
[component run](https://github.com/ai-shifu/markdown-flow-ui/actions/runs/39999398841),
and [Python run](https://github.com/ai-shifu/markdown-flow-agent-py/actions/runs/40007255303).
The Python wheel SHA-256 is
`65165f1a140a684916e3cb9be80214dd21861bc8437bf64852acbed480ac60a3`.
The application pins these actual development artifacts only on its feature
branch; the original narrow-repair pins have been replaced.

The formal parser and component releases are now published and verified.
`remark-flow@1.4.1` includes the native tokenizer-state compatibility repair;
`markdown-flow-ui@0.3.0` uses that exact parser. The regenerated application
lockfile selects both stable versions. The Python stable release is also published through official run
`40071222859`. Its actual wheel SHA-256 is
`3c852cad2b1ca3284b4c4c1f7b0e51b9f83c0b38c88abd8f4cef7bca9e1d62b0`;
all 34 runtime/resource files match the formal candidate and 1,131 installed
package tests pass without provider/network calls. The application now selects
`markdown-flow==0.4.2`, preserving the existing release gate. No automatic main merge
or release-gate bypass is part of this task.

## Context and Orientation

- The specification source is `ai-shifu/markdown-flow`, bilingual variable and
  interaction pages plus a shared JSON conformance corpus.
- `remark-flow` owns common name/marker helpers and raw Markdown tokenization.
- `markdown-flow-ui` owns editor validation, placeholders, highlighting,
  segmentation and built interactive rendering.
- `markdown-flow-agent-py` owns legacy extraction, replacement, interaction
  parsing, document splitting, translation and validation templates.
- `src/api/markdownflow/engine/` owns current collection, substitution and
  memory tools. `src/api/markdownflow/interaction_rendering.py` accepts explicit
  host labels, while course and Profile hosts share `flaskr.api.markdownflow`.
  Course legacy and streaming adapters emit and filter controls before the
  browser sees them.
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

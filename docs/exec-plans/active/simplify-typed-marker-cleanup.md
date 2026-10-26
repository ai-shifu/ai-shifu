# Simplify typed MarkdownFlow marker cleanup

## Purpose / Big Picture

Keep interactive lesson HTML executable by applying MDF preserve-marker removal only to
formatter-classified Markdown prose. HTML, SVG, code and other visual elements retain their
source bytes. Reuse the pinned MarkdownFlow classifier instead of maintaining a second HTML
parser. Deliver this change through PR #3150 and follow its latest-head CI and review without
merging.

## Progress

- [x] 2026-10-21 22:01 UTC: Pulled the PR branch and inspected classification, delivery,
  feedback persistence, engine display checks and existing regression coverage.
- [x] 2026-10-21 22:15 UTC: Replaced duplicate HTML parsing with typed marker cleanup
  and coordinated live narration, saved feedback and interaction extraction.
- [x] 2026-10-21 22:18 UTC: Verified streaming, opaque source preservation, persistence
  and learning-mode regressions: 3,984 learn tests passed, 93 environment-dependent skips.
  Architecture, harness and development-tool checks passed.
- [x] 2026-10-21 22:21 UTC: Pushed `dd4c5cb85` and rewrote the PR description.
- [x] 2026-10-21 22:32 UTC: All checks for `dd4c5cb85` reached terminal states:
  14 success, one skipped publication check and one neutral Cursor review.
- [x] 2026-10-21 22:36 UTC: Addressed the review finding that complete links held the
  remaining stream. Native analysis now distinguishes completed inline syntax, unresolved
  references and incomplete paragraphs; empty checkboxes cannot become references.
- [ ] 2026-10-21 22:36 UTC: Verify and push the separate review-fix commit, then follow
  its latest-head CI and review. Do not merge.

- [x] 2026-10-21 23:28 UTC: Rebased the independent invalid-fence follow-up (#3151)
  onto parent head `f1c9a431c5e5`, retaining the typed implementation and migrating regressions.
- [ ] 2026-10-21 23:28 UTC: Finish follow-up validation, push with an explicit lease,
  and converge its current-head CI and review without merging.

## Surprises & Discoveries

The pinned StreamFormatter classifies elements but normalizes blank lines and drops trailing
blank lines. Cleanup must retain the original physical source while reusing its types and
numbers. Prepared feedback must still be saved successfully before any filtered bytes become
visible. The formatter owns HTML boundaries, including its existing limitations; this task
must not introduce a competing HTML grammar to correct those limitations.

The first full learn run passed 3,954 tests with 93 environment-dependent skips.
Independent checks then found two compatibility edges: native reference definitions
wrapped with inline MDF prefixes must keep their metadata bytes, and the engine's
repeat-prefix comparison must not treat the UI formatter's buffered partial line as
an empty displayed candidate. The latter reproduced a new 584-character teaching
continuation being dropped before `finish`, while the old filter delivered it.
Both are part of coordinating existing callers of the replaced cleaner.

Latest-head review of `dd4c5cb85` found that treating every `[` as a possible forward
reference stalled completed links and all subsequent visuals. Native inline rule results
now distinguish actual unresolved candidates from complete links, code or escaped brackets.
Committed reference environments survive across pieces, while speculative parsing uses a
copy so a later native definition title remains intact. Empty normalized reference keys are
rejected by the native definition grammar and must not hold checklists.

## Decision Log

- 2026-10-21: The user explicitly approved treating whole HTML elements as opaque, including
  visible `===` text. Extend the same rule to existing non-prose element types.
- 2026-10-21: Keep LessonPager's legacy default for existing direct callers. The agent turn
  opts into typed cleanup. Markdown inline code and link metadata use native Markdown rules.
- 2026-10-21: Keep small MDF-envelope handling around the existing classifier; remove HTML
  raw-text, namespace, tag and attribute parsing from the marker cleaner.

- 2026-10-21: The user explicitly requested rebasing #3151 and #3152 after the parent
  rewrite. For #3151, discard the obsolete fence/replay parser changes. Reuse native
  `parse_code_fence_start` and reject only backtick info containing another backtick before
  the typed classifier opens code state. Native CRLF closing already works. Keep the legacy
  pager unchanged and retain native TEXT classification for quoted fence-looking prose.

## Outcomes & Retrospective

The custom HTML parser has been replaced by a small native-classifier adapter. HTML, SVG,
code and other visuals are opaque; native Markdown protects prose metadata without rendering
or rewriting source. Prepared feedback and narration use the same typed pipeline. Full engine
validation passed 1,054 tests, and the focused host/marker/pagination suite passed 389 tests.
The initial learn validation passed 3,984 tests with 93 environment-dependent skips. The
independent review fix passed the full learn suite with 4,015 tests and the same 93 skips;
its 154 focused Markdown/marker/pagination tests also passed. Latest-head external
acceptance remains tracked by PR #3150. Existing follow-up PRs #3151 and #3152
remain open; evaluate their applicability after the simplified base is tested.

## Context and Orientation

`src/api/markdownflow/pagination.py` owns the existing StreamFormatter integration.
`preserve_markers.py` ran a second parser before classification at the start of this task;
it now adapts the existing formatter and delegates only prose syntax to `markdown_text.py`.
`run_agent.py` delivers typed SSE, persists derived narration and enforces the prepared-feedback
commit barrier. `engine/engine.py` uses the marker projection for display/repetition checks.
Tests live under `src/api/tests/service/learn/agent/`.

## Plan of Work

Use the existing formatter's classifications and numbering to gate marker cleanup. Retain
source physical lines to avoid serializer changes. Remove MDF envelopes outside opaque
contexts. Clean classified prose with the native Markdown inline parser. Pass typed pieces
through delivery once, extracting narrated interaction syntax only from prose. Use the same
projection for fully prepared feedback and engine display comparisons. Replace obsolete
HTML-parser tests with the approved whole-element contract and retain host durability tests.

## Concrete Steps

Run focused marker/pagination/run-agent tests, the complete vendored engine suite, then learn
service tests. Run `python scripts/check_dev_tools.py`, architecture and harness checks, and
`lefthook run pre-commit --all-files` before committing. Push to the existing PR branch, wait
five minutes before feedback polling, then inspect CI and live review threads on the new head.

## Validation and Acceptance

For whole chunks, every two-part split and character streaming: HTML/SVG/code payload bytes,
strict comparison operators and literal markers survive; prose MDF markers disappear; wrappers
around visuals disappear; type/number order stays stable. Reading/listening and persisted
history agree. Prepared feedback is committed before visible output, and failures expose no
unsaved correction. Tool events do not terminate an opaque element. Interaction/turn/error
boundaries flush in order. Applicable latest-head checks must finish and new review findings
must be classified and addressed before completion.

## Idempotence and Recovery

Repeated flushes emit no duplicate content. Preserve the existing untracked `logs/` directory.
The user explicitly authorized rebasing the two follow-ups. Back up their original tips and
update rewritten branches only with an explicit force-with-lease against those tips. Do not
merge or enable auto-merge. Keep distinct verified review fixes in independent commits and
retain this plan until external acceptance is complete.

## Interfaces and Dependencies

Use pinned markdown-flow 0.3.4 and its StreamFormatter/Classifier; do not change dependency pins.
`LessonPager(clean_markers=True)` is the typed projection. `PreserveMarkerFilter.feed/flush`
remain a string projection for engine callers. No new frontend or persistence schema contract
is introduced.

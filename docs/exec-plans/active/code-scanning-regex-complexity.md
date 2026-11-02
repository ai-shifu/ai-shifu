# Bound malformed-text processing cost

## Purpose / Big Picture

Address CodeQL alerts #150, #105 and #26 without changing accepted course or
translation syntax. Long whitespace runs in MarkdownFlow separators, unmatched
angle brackets in TTS and incomplete translation calls must not repeatedly scan
the same suffix. The translation updater is a developer CLI; the course and TTS
parsers are service/library surfaces.

## Progress

- [x] 2026-11-01 10:28 UTC: Reproduced the reported expensive patterns and
  established their delimiter and whitespace compatibility contracts.
- [x] 2026-11-01 10:28 UTC: Implemented linear scanners and adversarial-input
  regressions while retaining normal and malformed-input behavior.
- [x] 2026-11-01 10:28 UTC: Independent review identified repeated unfinished
  translation calls as a second expensive form; fixed it and added coverage.
- [x] 2026-11-01 10:28 UTC: Passed all 2,966 offline engine tests, 942 TTS tests,
  five script tests, translation checks and the combined 15,249-test backend run.
- [ ] 2026-11-01 10:32 UTC: Human PR acceptance, merge and default-branch alert
  closure remain external gates. Do not merge automatically.

## Surprises & Discoveries

- Replacing separator whitespace with horizontal whitespace would change the
  established syntax. The scanner retains the former greedy match spans.
- Restricting tag contents to exclude nested opening brackets would change
  malformed-tag stripping. The scanner removes the first opening bracket through
  its next closing bracket, leaving an unmatched tail untouched.
- Removing nested dotted-key repetition alone left quadratic searches for a
  missing closing parenthesis. Translation extraction now advances a cursor
  through each completed call and stops once no closing parenthesis remains.

## Decision Log

- 2026-11-01: Preserve actual legacy spans and non-overlap rather than introduce
  input limits, truncate text or change valid narration/course syntax.
- 2026-11-01: Keep the engine independent of Flask. Keep each scanner in its
  owning module and add no dependency or public service contract.
- 2026-11-01: Use subprocess deadlines for malicious inputs, with broad deadlines
  that detect nontermination without fragile microbenchmark thresholds.

## Outcomes & Retrospective

Local validation passes, including original and alternate malicious inputs and
legitimate controls. Default-branch alerts require a human merge and a subsequent
CodeQL scan; this work does not deploy or merge changes.

## Context and Orientation

`src/api/markdownflow/syntax/document.py` splits authoring documents while
respecting protected spans. `src/api/flaskr/service/tts/__init__.py` removes tags
before synthesizing speech. `scripts/update_i18n.py` collects dotted translation
keys. Follow root/backend, engine, TTS and scripts `AGENTS.md` rules for their
respective paths. No authentication, authorization or analytics contract changes.

## Plan of Work

Replace expensive matching at the three reported boundaries, retain existing
callers and behavior, then compare against legacy semantics. Verify original
attack forms, alternate malformed inputs, protected course blocks and narration.
Submit one focused parser-complexity PR independently of other scan remediations.

## Concrete Steps

1. Replace separator matching with a cursor-based span iterator.
2. Replace generic angle-tag substitution with a cursor-based stripping helper.
3. Extract translation-key prefixes and skip directly to the next closing call.
4. Add scoped regression files, run package gates and translation checks, and
   review the final diff before creating a ready PR.

## Validation and Acceptance

From `src/api`, run `python -m pytest tests/markdownflow/ -q` (2,966 passed),
`python -m pytest tests/service/tts/ -q` (942 passed), and the new complexity
tests. From root, run `python -m unittest discover -s scripts -p
test_update_i18n_patterns.py -q` (five passed), translation parity/usage checks,
locale generation, Ruff and `lefthook run pre-commit --all-files`.

Randomized and exhaustive comparisons retain separator and tag behavior;
translation extraction matches the previous behavior across all 875 tracked
frontend source files. A clean `requirements-ci.txt` environment passed 15,249
backend tests and 41 subtests, with 109 existing skips, including the independent
HTTP, notification and export candidates submitted in separate PRs.

## Idempotence and Recovery

Tests and checkers are repeatable and make no business-state changes. Revert this
focused commit with its regression tests to recover prior parser behavior. No
database migration or configuration change is needed.

## Interfaces and Dependencies

The engine document API and TTS preprocessing API remain unchanged. The internal
translation collector replaces its pattern list with a key-scanning helper and
updates its direct consumer and tests together. Standard-library operations
suffice; no package or lockfile changes are required.

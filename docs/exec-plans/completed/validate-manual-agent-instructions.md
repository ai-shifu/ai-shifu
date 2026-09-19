# Validate Manual Agent Instructions

## Purpose / Big Picture

Validate directly maintained instruction files after PR #2861 retires their
generator. Keep these checks, tests, and toolchain changes in a separate PR so
the documentation cleanup can be reviewed independently.

## Progress

- [x] 2026-09-19 07:20 UTC: Isolated documentation cleanup and its minimal
      generator-retirement wiring in PR #2861.
- [x] 2026-09-19 07:28 UTC: Restored the independently reviewed validator,
      regression tests, CI integration, and dependency setup on a dependent branch.
- [x] 2026-09-19 07:33 UTC: Independent review verified the split; all 21 tests
      passed on Python 3.11 and 3.14, and all 20 repository pre-commit checks passed.

## Surprises & Discoveries

- Removing the generator requires a small checker/CI adjustment in the parent
  PR; otherwise existing checks would import or execute a deleted file.
- Markdown links can use titles, references, escaping, and nested parentheses.
  A CommonMark parser avoids a partial regular-expression implementation.
- Instruction files themselves, as well as their link targets, can be symlinks.
  Resolve both inside the repository before reading or accepting them.

## Decision Log

- 2026-09-19: Base this validation PR on the documentation PR and merge the
  documentation PR first. Do not rewrite earlier review-fix history.
- 2026-09-19: Reject tracked `CLAUDE.md` and `CLAUDE.local.md` overrides while
  allowing ignored or untracked personal configuration.
- 2026-09-19: Pin `markdown-it-py==4.0.0` in CI and developer installation
  guidance, and have the tool doctor verify that version before local gates.

## Outcomes & Retrospective

All validation files match the reviewed snapshot. The focused tests, tool
doctor, repository harness, and full pre-commit gate passed. Independent review
confirmed the parent retains only documentation cleanup and required generator
retirement wiring. No application runtime code changes were required.

## Context and Orientation

`scripts/check_repo_harness.py` owns instruction and knowledge validation.
`scripts/test_repo_instructions.py` exercises manual ownership, tracked-file
policy, Markdown navigation, and filesystem boundaries. `repo-harness.yml`
runs these checks in CI; `lefthook.yml` runs the local gates. The compatibility
design and installation guides describe the resulting contract and tools.

## Plan of Work

Extend the existing harness without restoring generated instruction ownership.
Cover malformed or retired files, standard local links, tracked overrides, and
symlink boundaries. Wire the parser and focused tests into both developer
setup and CI. Remove the obsolete checker alias and stale backend path filter.

## Concrete Steps

1. Restore validation changes and their regression tests on the dependent branch.
2. Run the tests with Python 3.11 and the local Python version.
3. Run the tool doctor, repository harness, architecture checks, and full hooks.
4. Verify parent/child diffs and compare validation files with the reviewed snapshot.
5. Complete this plan, regenerate knowledge indexes, and publish the separate PR.

## Validation and Acceptance

All 21 focused tests must pass. Valid CommonMark links and internal symlinks
must be accepted; missing targets, repository escapes, symlink loops, and
tracked override files must fail with actionable errors. Ignored and untracked
personal overrides must remain allowed. The tool doctor and all repository
pre-commit checks must pass with the pinned parser and Ruff versions.

## Idempotence and Recovery

Checks are read-only. Test fixtures use temporary directories and isolated Git
indexes. Regenerating knowledge indexes must be deterministic. Revert this
dependent change to recover the documentation PR's existing validation model.

## Interfaces and Dependencies

Use Python 3.11 or newer, Git for tracked-file enumeration, and
`markdown-it-py==4.0.0` for CommonMark links. The application dependency pins
and runtime interfaces are unchanged.

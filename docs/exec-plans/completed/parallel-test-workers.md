# Run frontend and backend tests with two workers

## Purpose / Big Picture

Reduce test latency by running two test worker processes inside each existing
GitHub Actions runner. Preserve workflow triggers, required check names, backend
testmon selection and cache lineage, and the full-source 95.01 percent coverage
gate. The user requested implementation, verification, and a ready pull request;
merging and deployment are outside this task.

## Progress

- [x] 2026-10-10 UTC: Inspected workflow commands, test isolation, testmon and
  coverage contracts; refreshed origin/main and created the task branch.
- [x] 2026-10-10 UTC: Implemented fixed two-worker commands and worker-aware
  coverage collection; focused workflow/coverage contracts pass (24 tests),
  and both-worker contract tests pass (8 tests).
- [x] 2026-10-10 UTC: Full frontend Jest suite passed with Node 22.16.0:
  260 suites and 3,040 tests, with no lockfile changes.
- [x] 2026-10-10 UTC: Full backend testmon run reached all 11,061 tests;
  11,039 passed, 15 skipped, and 7 encountered inherited local proxy settings.
  Removing proxy variables from the test process let testmon retry those seven
  and the changed regression: 8 passed in 11.77 seconds.
- [x] 2026-10-10 UTC: Developer-tool doctor, actionlint, repository harness,
  architecture boundary check, and full pre-commit hooks passed.
- [x] 2026-10-10 UTC: Full backend coverage command passed 11,046 tests with
  15 conditional skips; required isolated Redis tests ran. Coverage is 95.18%
  (66,278 of 69,637 application statements), above the unchanged 95.01% gate.
- [x] 2026-10-10 UTC: Prepared ready-PR metadata with complete local verification
  evidence. PR publication and subsequent CI readback are tracked on GitHub.

## Surprises & Discoveries

- Frontend CI already uses a CPU-relative Jest worker limit; backend pytest is
  serial. A recent backend run executed 11,050 collected tests in about fourteen
  minutes, while frontend test execution took about eighty-five seconds.
- Backend fixtures use per-process temporary SQLite databases and per-test
  Redis instances. A custom shared test database URI needs separate isolation.
- The existing manual coverage command measures only its initiating process;
  worker coverage must be collected and combined explicitly.
- This checkout has no installed test dependencies. Validation uses an ignored
  local virtual environment and the workflow's Node version.
- The repository developer tools require newer packaging than the application's
  pinned dependencies, so they run in a separate temporary virtual environment.
- Local proxy variables caused Langfuse's HTTP client to require an uninstalled
  SOCKS extra. Validation removes proxy variables only from test subprocesses,
  matching CI; no application dependency or global proxy setting is changed.

## Decision Log

- Keep one existing job and runner per workflow. Set Jest maxWorkers to 2 and
  pytest-xdist to two workers with file-level distribution.
- Preserve PR target selection, testmon's incremental/full modes and cache
  lineage. Do not introduce matrix shards or duplicate cache writers.
- Use pytest-cov for xdist coverage collection and merging. Preserve separate
  JSON/XML/text evidence and the final coverage.py threshold check, including
  test-failure precedence.

## Outcomes & Retrospective

Implementation and local validation are complete. Both existing jobs use two
test workers, testmon still selects affected tests, and coverage includes both
workers and unimported application modules. Full coverage and frontend suites
pass. No comparative speedup is claimed from local macOS timings; added workers
share the runner's CPU and memory. GitHub publication and CI status are delivery
metadata recorded on the pull request.

## Context and Orientation

`.github/workflows/backend-tests.yml` selects PR targets and runs testmon, full
main tests, or manually dispatched coverage. `src/api/requirements-ci.txt` owns
CI-only Python plugins. `src/api/.coveragerc` owns the complete application
denominator and 95.01 percent threshold. Workflow and real coverage contracts
live in `src/api/tests/scripts/`. `src/web/package.json` owns Jest's CI command.
The canonical verification guidance is `docs/engineering-baseline.md`.

## Plan of Work

Update the frontend command and backend CI-only dependencies, all backend test
invocations, and the manual coverage invocation. Extend behavior-level workflow
and coverage tests to protect worker collection and failure handling. Update the
handbook to match. Verify full suites and cache reuse before publishing a PR.

## Concrete Steps

1. Install isolated Python and frontend dependencies matching CI.
2. Run focused workflow/coverage contracts, then complete two-worker suites.
3. Run a real testmon warm-cache selection and worker coverage merge check.
4. Run the full coverage gate and repository hooks, commit, push, and open PR.
5. Read back the PR's frontend/backend checks and any coverage dispatch evidence.

## Validation and Acceptance

Both runners use exactly two test workers; no matrix is introduced. Existing
selected targets and testmon flags remain correct. An unchanged warm-cache run
can deselect tests without failing. Coverage includes executed worker code and
unimported application modules, rejects exactly 95 percent, and retains evidence
on failure. Full frontend and backend tests pass with required Redis tests
enabled. Developer-tool, repository harness, architecture and pre-commit checks
pass. Prepared PR metadata describes the complete local verification evidence;
publish the ready PR and read back its checks after committing this change.

## Idempotence and Recovery

Test caches and coverage outputs are ignored local artifacts and can be cleared
before retrying. Do not share a custom database URI between workers. Reverting
this focused PR restores prior worker limits without application data changes.

## Interfaces and Dependencies

Add pinned pytest-xdist and pytest-cov only to backend CI requirements. Keep
production dependencies, package lockfiles, external services, workflow triggers,
and existing check names unchanged. Jest already supports process workers.

# Backend Test Coverage Above 95 Percent

## Purpose / Big Picture

Improve backend regression protection comprehensively and verify more than 95
percent statement coverage over the complete application source. Tests must
assert observable contracts, including successful operations, validation,
authorization, transaction failures, retries, streaming termination, and
provider failures. Coverage is evidence of exercised code, not a substitute for
behavioral assertions.

## Progress

- [x] 2026-09-20 01:29 UTC: Inspected repository/backend instructions, current
  test fixtures, CI workflow, and engineering expectations. Fetched origin;
  created `sunner/backend-test-coverage-95` from current `origin/main`
  (`0ff9c19c3`). Working tree was initially clean.
- [x] 2026-09-20 01:42 UTC: Established full application baseline: 5,056 passed,
  107 skipped, 46 subtests passed in 259.52 seconds; 54,108 / 64,879 statements
  covered (83.398326 percent) across 445 files. This snapshot includes early
  test additions collected when the run started, not all later batches.
- [x] 2026-09-20: Expanded authentication/account, billing/order, learning,
  speech, framework, commands and remaining application areas through Round 8.
- [x] 2026-09-20 11:02 UTC: Added full-source coverage configuration, 95.01 percent
  CI threshold, report artifacts, and 17 passing coverage/workflow contract tests.
  The threshold is intentionally still failing while coverage work continues.
- [x] 2026-09-20 11:02 UTC: Built isolated Redis 7.4.11 under `/private/tmp`;
  formerly skipped real Redis tests now run (96 passed independently). CI
  installs Redis and fails if it is missing.
- [x] 2026-09-20 11:02 UTC: User-service suite reaches 3,053 / 3,189 statements
  (95.7353 percent); user routes 489 / 513 (95.3216 percent), 808 user tests
  passing. Whole-backend target remains incomplete.
- [x] 2026-09-20 11:02 UTC: Round 2 full run produced 5,752 passed, 13 skipped,
  and 8 failures in new reserved campaign bonus tests. Fix test interaction before
  accepting another baseline. Diagnostic coverage is 55,952 / 64,879 (86.2405
  percent); remaining misses are 8,927. Later batches were not collected yet.
- [x] 2026-09-20 11:06 UTC: Round 2 bonus failures were missing seed fields
  (`priority`, `effective_from`) in the collected pre-fix snapshot. Independently
  reran the corrected file: 8 passed.
- [x] 2026-09-20: Round 3 full suite is complete: 5,894 passed, 12 skipped,
  46 subtests passed in 240.11 seconds. Statement coverage is 56,537 / 64,879
  (87.142219 percent), with 8,342 missing statements across 445 files.
  Evidence: `/private/tmp/ai-shifu-round3.{log,coverage,json}`. The remaining
  skips require MySQL (2) or the optional SaaS configuration plugin (10).
- [x] 2026-09-20: Added 102 admin credit/profile cases; all 574 shifu tests
  pass at the checkpoint; final admin batch is 107 tests with 579 domain tests
  passing. Credit queries cover 634 / 643 statements, profiles 282 / 290.
- [x] 2026-09-20: New Tencent stream regression proved HTTP errors left the
  response open. Moved the status check inside the existing cleanup guard;
  all 33 Tencent provider/stream tests pass after the fix.
- [x] 2026-09-20 11:06 UTC: Coordinator foundation suite passes 170 tests
  (plugin lifecycle, operator CLI, real migration transactions, checkpoint
  recovery, workflow/coverage gates, dotenv isolation). Separate Volcengine
  protocol batch passes 40 cases. All API Ruff checks and repository harness
  were green at this checkpoint.
- [x] 2026-09-20: Round 4 full suite passes 6,773 tests, with 12 integration
  skips and 46 passing subtests in 261.78 seconds. Measured application statement
  coverage is 58,301 / 64,879 (89.861126 percent), with 6,578 statements missing.
  Evidence: `/private/tmp/ai-shifu-round4.{log,coverage,json}`. Later batches are
  not included in this snapshot; the target is still unmet.
- [x] 2026-09-20: The new HTTP favorite-route regression exposed a missing path
  parameter in the route handler; added that parameter and verified the real
  request path. A real subscription refund test exposed a non-serializable
  metadata DTO assigned to a JSON column; the field now uses the same normalized
  JSON conversion as the adjacent order field, with successful refund and
  transaction rollback cases passing.
- [x] 2026-09-20: MiniMax transport regressions failed in six cleanup scenarios
  (normal completion, cancellation, HTTP errors, malformed JSON/audio and
  provider rejection). Added a response cleanup guard; all 559 TTS tests pass.
  LLM provider/gateway suites pass 168 tests; cache lifecycle tests pass 19.
  New OSS tests exercise bounded CDN polling, public URL retries, profile
  isolation and upload failure contracts.
- [x] 2026-09-20: Completed full-suite verification, the 95.01 percent coverage
  gate, repository checks and PR separation; prepared the final test-only PR.

## Surprises & Discoveries

- Initial source inventory contains 444 Python files under `src/api/flaskr`.
- Existing CI runs coverage without a source restriction, which can count test
  modules and miss never-imported application modules. No coverage configuration
  or minimum threshold currently defines an application-only denominator.
- Existing shared Python environment has pytest but lacks coverage; install
  measurement tools in a task-local temporary directory without changing the
  shared environment.
- An initial measurement failed with 1,955 setup errors: coverage source-module
  discovery and third-party dotenv loading consumed the local developer
  configuration. Two more failures came from an inherited SOCKS proxy without
  the optional httpx SOCKS dependency. These are invalid baseline evidence.
  Use directory-based source discovery, disable dotenv at process startup, and
  clear proxy variables for offline runs. A worktree-local `.venv` now contains
  the exact backend/CI pins and Ruff 0.16.5.
- Real Redis tests account for 89 skips in the initial full run. They now run
  against a task-local Redis 7.4.11 executable; the fixture owns its short-lived
  Unix socket and process. The remaining integration dependencies include
  optional MySQL and the uninstalled SaaS plugin.
- Four skipped tests targeted removed `RunScriptContextV2` async helpers. They
  were retired after verifying active replacements in `agent/test_bridge.py`
  and `agent/test_bridge_gevent.py`. The old database-sampling SSE test has been
  replaced by eight deterministic persisted narration/visual replay cases.

## Decision Log

- 2026-09-20: Measure every module under `flaskr` and the `app.py` entrypoint.
  Include never-imported modules. Do not omit low-coverage modules, add exclusion
  pragmas, remove real behavior, or count test code to reach the target.
- 2026-09-20: Interpret the requested percentage as statement coverage above
  95 percent; collect branch coverage as additional diagnostic evidence. Tests
  should explicitly cover decision boundaries even when statement coverage alone
  would pass.
- 2026-09-20: `.coveragerc` uses directory source discovery and includes all
  `flaskr/*` plus `app.py` in application reports. Standard coverage runs gate
  statement coverage at 95.01 percent; `coverage run --branch` is a separate
  diagnostic run whose combined line/branch percentage is not the statement
  percentage. No application modules are omitted.
- 2026-09-20: Use deterministic local doubles at external network/provider
  boundaries and the existing database fixtures. No production credentials or
  services are needed for the regression suite.
- 2026-09-20: The user requires each kind of production behavior change to
  have its own pull request. Separate each confirmed runtime fix together with
  self-contained regression tests; publish comprehensive remaining tests and
  the coverage gate in a separate PR. Preserve a reproducible combined state
  and make any PR dependencies explicit. Do not put unrelated runtime fixes
  into the comprehensive test PR.

## Outcomes & Retrospective

Implementation and local acceptance are complete. The final frozen suite
passes 9,085 tests and 50 subtests, with 12 optional integration skips.
Application statement coverage is 62,692 / 65,947 (95.0642182359 percent),
above the enforced 95.01 percent gate. All 451 application Python files
are included, including unimported namespace modules. No low-coverage source
modules or new exclusion pragmas were removed from the denominator.

Fourteen ready business-fix PRs (#2882 through #2895) each contain one kind of
runtime correction and its required regressions. The final comprehensive
test/CI change targets #2895 and has no application-runtime diff. Its tests
cover successful operations, validation, authorization, persisted state,
transaction rollback, retries, provider failures and stream termination.

The optional skips are two isolated MySQL integrations and ten tests requiring
the absent SaaS configuration plugin. Real Redis admission tests run locally
and are required in CI. The developer-toolchain check and all-files lefthook
gate pass. Python source/test files and coverage configuration are identical
before and after the accepted full measurement.

Eleven verified review threads are resolved. The [existing refund idempotency
and reconciliation concern](https://github.com/ai-shifu/ai-shifu/pull/2888#discussion_r4056996840)
predates the metadata-serialization correction and remains open for separate
work. A BuildKit cache-layer export failure on #2890 passed on retry without
a code change. Current CI results and downloadable coverage evidence remain
attached to the PRs.

## Context and Orientation

`src/api/app.py` creates the Flask app; `src/api/flaskr` contains the application,
providers, persistence, routes, services, and utilities. Existing pytest tests
live under `src/api/tests`. The shared `tests/conftest.py` configures temporary
SQLite, fake Redis and LLM responses, and skips local dotenv loading.
`.github/workflows/backend-tests.yml` uses testmon for incremental PR runs and
unrestricted coverage for main/manual runs. `src/api/requirements-ci.txt` already
pins coverage. Root `PLANS.md` defines this document's maintenance requirements.

## Plan of Work

First run collection and the complete suite under an explicit application source
   measurement. Record existing failures separately from new-test failures. Rank
missing statements and branches by module and business risk. Expand tests in
disjoint batches, using real service logic and database behavior with isolated
external collaborators. Rerun focused tests after each batch and periodically
measure the complete suite. Once the requested threshold is proved, enforce it
in a reproducible command and CI without testmon deselection. Update the stable
testing handbook and generated documentation indexes.

## Concrete Steps

1. Use Python 3.11 with backend dependencies and the pinned CI coverage package.
   Use the task-local `.venv/bin/python`, created from the pinned CI dependency
   file. The shared source-checkout environment is stale; do not use it.
2. From `src/api`, collect tests, then run coverage over `flaskr,app` and all
   `tests`, disabling testmon selection if loaded. Retain JSON and text reports
   as local artifacts and record their authoritative totals here.
3. Add focused tests based on missing behavior and run affected pytest modules
   plus repository-configured Ruff checks.
4. Integrate coverage configuration/gating and document exact commands. Run the
   full suite and inspect raw totals, not rounded console percentages.
5. Regenerate knowledge indexes; run repository harness, architecture boundaries,
   `python scripts/check_dev_tools.py`, and required pre-commit checks before
   committing/pushing the ready PR.

## Validation and Acceptance

- Complete backend suite passes with no unexplained collection errors or newly
  skipped cases. Existing optional integration skips are reported honestly.
- Every application Python source file under `flaskr` plus `app.py` belongs to
  the measurement; tests and vendored external dependencies do not inflate it.
- Full-run covered statements divided by total statements is strictly greater
  than 0.95, without cached test selection or narrowed source exclusions.
- New tests exercise real code and assert business outputs, persisted state,
  authorization, side effects, rollback, and error behavior as appropriate.
- Coverage remains reproducible and enforced in CI. Repository-required checks
  pass, and the ready PR describes the final implementation and evidence.

## Idempotence and Recovery

Use separate coverage data/report paths for concurrent focused runs. Never merge
coverage databases from different source revisions or substitute a targeted run
for the final complete-suite result. Tests use temporary databases and synthetic
identifiers. Keep this plan active until all acceptance conditions are verified.

## Interfaces and Dependencies

Reuse pytest, coverage.py, Flask test clients, SQLAlchemy fixtures, existing
fake Redis/LLM helpers, and provider interfaces. Do not introduce production
dependencies to make tests pass. Shared fixture or CI edits remain coordinated
centrally so parallel test work does not change another batch's assumptions.

## Completion Snapshot

The complete suite and standard coverage gate pass. Review each of the 14
business PRs in the table below separately, followed by the comprehensive
test-only change. The recorded source/test manifests make the local result
reproducible; CI runs the same complete-source denominator independently of
testmon. The execution history below preserves earlier diagnostic checkpoints
and discovered regressions.

### Round 5 diagnostic checkpoint

Full run: 7,387 passed, 12 skipped, 22 failed, 46 subtests passed in
277.78 seconds. Source SHA256 manifests before collection and after report
creation match exactly. Diagnostic statement coverage: 59,812 / 64,891 =
92.1730286172 percent, 5,079 missing. Evidence:
`/private/tmp/ai-shifu-round5.{log,coverage,json}` and
`/private/tmp/ai-shifu-round5-source.json`. This is not a passing gate.

All 22 failures came from new tests collected before their correction: 17
renewal fixture/API-shape assumptions and five wrong expected parameter-error
codes. The corrected billing/order domain passes 1,687 tests (10 skips); the
corrected shifu domain passes 943 tests. Future whole-suite measurement freezes
both source and collected tests to prevent stale intermediate snapshots.

Post-round-5 coordinator additions: 32 callback isolation/routing tests and
27 authenticated partner HTTP tests pass. Additional tests cover translation
startup failures, request observability, configuration type boundaries, and
idempotent demo import/publication with independent per-course transactions.
The new profile-research corrupt-cache regressions proved UTF-8 decoding and
schema conversion escaped the established SessionNotFound recovery contract;
the narrow fix moves both into its existing exception mapping, with all 121
profile-research tests passing.

### Round 6 passing checkpoint and upstream refresh

Frozen source and tests pass the entire suite: 7,995 passed, 12 skipped,
46 subtests passed in 314.96 seconds. Coverage: 60,827 / 64,891 =
93.7371900572 percent; 4,064 missing statements. SHA256 manifests include
all runtime and test Python files and match before/after measurement.
Evidence: `/private/tmp/ai-shifu-round6.{log,coverage,json}` and the source
manifest. The >95 percent target is still incomplete.

Fetched origin and fast-forwarded this task branch from `0ff9c19c3` to
`407a00c96` (18 upstream commits), preserving all task changes in a named
stash backup before restoring them. Resolved the generated harness document
by regeneration and the upload helper conflict in favor of upstream safe
outbound HTTP behavior; retained only the needed video AppError correction.
The latest baseline changes numbered course models, descendant model settings,
learning preview/listening, safe outbound requests and payment reconciliation.
Adapt new test fixtures and expectations to those contracts before the next
full measurement; do not restore superseded behavior to satisfy old tests.

Independent review found observability tests retaining global metric/request
state. Their metrics now use a private CollectorRegistry and an isolated
thread-local object; traced providers shut down after each test. The review
also identified a partial-refund assumption in a new atomicity regression;
change that case to full refund and assert wallet/bucket/snapshot rollback.

### Round 7 passing checkpoint and PR separation

The refreshed baseline passes 8,753 tests, with 12 integration skips and
50 passing subtests in 348.86 seconds. Complete application coverage is
62,272 / 65,930 statements (94.4516911876 percent), with 3,658 missing across
451 files. Runtime and test SHA256 manifests match exactly before and after
measurement. Evidence: `/private/tmp/ai-shifu-round7.{log,coverage,json}` and
`/private/tmp/ai-shifu-round7-source.json`. The remaining skips are the same
two isolated MySQL integrations and ten optional SaaS-plugin tests. This is
still below the gate: at least 369 additional covered statements are needed.

Real SQL payment tests exposed legacy public user-state constants being used
as persisted states. A paid user was saved as unregistered; importing the
canonical user constants fixes both payment completion and notification
counts. Independent review also caught the proposed Pingxx empty-lock early
return acknowledging an unpaid order. That proposal was replaced with an
application error, a non-2xx legacy callback response, and four real HTTP
regressions covering empty/busy locks on scoped and legacy callbacks.

The user requires separate PRs for each kind of runtime change. Fourteen
business-fix groups now have minimal self-contained test subsets under their
original test filenames. Build them as a linear PR stack, then expand those
files and add the remaining comprehensive tests/coverage gate in a final PR
with no production-code diff. The isolated assembly worktree is
`/private/tmp/ai-shifu-backend-pr-stack`; its group manifest, verification logs
and completed commit state live under `/private/tmp/ai-shifu-pr-stack`.
The main task worktree retains the full combined test suite. Each business
group must pass its focused tests and the repository-wide lefthook gate.

### Published business-fix PR stack

Each ready PR contains one runtime correction and focused regression tests.
The base of each PR after the first is the preceding branch; merge in order.
The final comprehensive test PR must target the last branch and contain no
application runtime changes. All listed subsets and all-files gates passed.

| PR | Focus |
| --- | --- |
| [#2882](https://github.com/ai-shifu/ai-shifu/pull/2882) | fix: release TTS connections after stream failures |
| [#2883](https://github.com/ai-shifu/ai-shifu/pull/2883) | fix: recover from malformed speech token cache entries |
| [#2884](https://github.com/ai-shifu/ai-shifu/pull/2884) | fix: ignore malformed saved listening payloads |
| [#2885](https://github.com/ai-shifu/ai-shifu/pull/2885) | fix: handle corrupted profile research sessions consistently |
| [#2886](https://github.com/ai-shifu/ai-shifu/pull/2886) | fix: keep learner answers on active interactions |
| [#2887](https://github.com/ai-shifu/ai-shifu/pull/2887) | fix: persist referral operator audit metadata |
| [#2888](https://github.com/ai-shifu/ai-shifu/pull/2888) | fix: complete subscription refunds with valid metadata |
| [#2889](https://github.com/ai-shifu/ai-shifu/pull/2889) | fix: accept course favorite requests at the registered URL |
| [#2890](https://github.com/ai-shifu/ai-shifu/pull/2890) | fix: restore speech settings in course listings |
| [#2891](https://github.com/ai-shifu/ai-shifu/pull/2891) | fix: reject malformed course import documents safely |
| [#2892](https://github.com/ai-shifu/ai-shifu/pull/2892) | fix: preserve actionable video lookup errors |
| [#2893](https://github.com/ai-shifu/ai-shifu/pull/2893) | fix: retry payment callbacks when their lock is unavailable |
| [#2894](https://github.com/ai-shifu/ai-shifu/pull/2894) | fix: keep successful Stripe payment synchronization idempotent |
| [#2895](https://github.com/ai-shifu/ai-shifu/pull/2895) | fix: preserve the paid account state after checkout |

### Round 8 passing coverage gate and review follow-up

The frozen complete suite passes 8,986 tests and 50 subtests, with the same
12 optional integration skips, in 389.13 seconds. Application coverage is
62,672 / 65,930 statements (95.0583952677 percent), with 3,258 missing
statements across all 451 application files. The standard coverage report
passes its 95.01 percent threshold without an override. Runtime and test
SHA256 manifests match before and after the run. Evidence:
`/private/tmp/ai-shifu-round8.{log,coverage,json}` and its source manifest.

Current-head review of all 14 business PRs found six in-scope omissions:
MiniMax cleanup errors replacing stream errors; non-string cached speech
tokens; infinite profile schema values; malformed persisted profile input;
Redis lock acquisition exceptions acknowledged by the legacy payment route;
and already-paid Stripe orders with old unfinished snapshots. Each receives
focused failure-first regression coverage and a separate review-fix commit
in its existing PR. Strengthen Tencent lifecycle and video error assertions
in those same owning PRs. A subscription-refund idempotency concern predates
its metadata-serialization patch and remains outside that PR's scope.

Upstream added two inspected changes after the previous refresh:
`3050042bc` makes the generated harness-health report local and ignored, and
`731473479` adds a learner-facing engine prompt guard and one offline test.
Preserve both while rebuilding the PR stack; do not reintroduce the generated
health report into version control. The next full run includes these changes.

The independent coverage-workflow review found and fixed three gate defects:
namespace packages must be included explicitly so unimported service modules
remain in the denominator; deleted tests must trigger a complete run; and
artifact upload must include the hidden raw coverage database. Three focused
regressions failed before the corrections; all 19 coverage/workflow contract
tests pass afterward. Source discovery now independently matches all 451
application files. These changes belong to the final test/CI PR.

### Round 9 and historical account compatibility

The reviewed stack on `731473479` passes 9,081 tests and 50 subtests, with
12 optional integration skips, in 372.66 seconds. The complete application
report passes 95.01 percent: 62,690 / 65,945 statements, or 95.0640685420
percent. All 451 files are included, and runtime/test hashes remain unchanged.
Evidence: `/private/tmp/ai-shifu-round9.{log,coverage,json}`. The merged focused
verification (including the vendored engine) passes 354 tests; all-files
lefthook and developer-toolchain checks pass.

A subsequent review of #2895 identified real historical rows using public
account states alongside canonical stored states. Its isolated database
regressions verify fixed paid/registered/visitor counts for legacy, canonical
and mixed populations, include soft-deleted rows, and prove notification
queries preserve raw persisted states. Two cases fail before the correction;
all nine focused cases and 268 order/callback cases pass afterward. The fix
uses the existing state mapping only for notification queries; successful
payments continue writing canonical states. It remains in #2895.

### Final acceptance after review

Round 10 caught one pre-existing notification-formatting test double that
supported range comparison but not the new state-membership query. The real
database regressions passed. Update that double in #2895; keep the final test
PR free of the runtime correction and its necessary compatibility change.

Round 11 passes: 9085 passed, 12 skipped, 929 warnings, 50 subtests passed in 360.82s (0:06:00). Application coverage is
62,692 / 65,947 statements (95.0642182359 percent), with 3,255 missing
and 451 files included. The standard 95.01 percent report gate passes.
The source/test SHA256 manifests match before and after this run. Evidence:
`/private/tmp/ai-shifu-round11.{log,coverage,json}` and
`/private/tmp/ai-shifu-round11-source.json`. The previous baseline was
54,108 / 64,879 statements (83.398326 percent); subsequent upstream work
increased the denominator and is included in this final measurement.

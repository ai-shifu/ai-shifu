# Provider-independent first administrator setup

## Purpose / Big Picture

A fresh self-hosted installation can create its first administrator without
SMTP, SMS or OAuth configuration. A server-console operation authorizes one
initialization transaction, either directly or through a short-lived Web setup
code. Local administrator password login remains independent of learner login
methods. Preserve the ordinary verification-code security boundary.

## Progress

- [x] 2026-10-25 UTC: User selected the Web setup design with console fallback
  and explicitly authorized implementation.
- [x] 2026-10-25 UTC: Refreshed main `a37b6e6` and existing PR #3175. Created
  isolated branch `feat/first-run-admin-setup` from verified head `3f5de08`;
  the OTP fix remains a dependency while its PR is unmerged.
- [x] 2026-10-25 UTC: Read repository, auth, Web and Docker ownership rules;
  agreed shared service, local identity, API and analytics contracts.
- [x] 2026-10-25 UTC: Implemented durable installation state, migration provenance and console
  initialization/recovery commands.
- [x] 2026-10-25 UTC: Implemented local administrator identity, login and token/session checks.
- [x] 2026-10-25 UTC: Implemented setup/status/login HTTP boundaries and deployment startup.
- [x] 2026-10-25 UTC: Implemented setup and local login UI, translations, analytics and tests.
- [x] 2026-10-25 UTC: The historical local frontend run passed 281 suites/3,444
  tests; the local backend run passed 15,105 tests with 107 skipped. That local
  backend run measured 95.18% coverage against the 95.01% gate. PR CI did not
  collect new coverage; skip reasons are recorded in delivery evidence.
- [x] 2026-10-25 UTC: Restored the missing task-local Redis test binary after
  identifying 92 skipped real-Redis cases. Both affected modules passed all
  120 tests with Redis required. Across runs, 15,197 distinct backend cases
  passed and 15 remain skipped for MySQL or optional SaaS plugin prerequisites;
  this is not a single full-run result.
- [x] 2026-10-25 UTC: Corrected independently identified local-password reset
  races, non-demo ownership transfer and unsafe schema downgrade. Independent
  domain follow-up passed seven targeted cases. The review tool blocked the
  final independent identity follow-up; the 15,105-pass/107-skip local backend
  run includes the new threaded identity regressions, and root inspected the
  shared lock boundary.
- [x] 2026-10-25 UTC: TypeScript, complete frontend lint, production build,
  repository pre-commit and migration/domain checks passed. Fixed missing
  product-spec metadata and regenerated the knowledge indexes after the first
  pre-commit attempt identified them.
- [x] 2026-10-25 UTC: Native Chrome acceptance passed setup, administrator
  access, password change, logout, old-password rejection and new-password
  login. Fixed the new modal's accessible title/description; three focused
  suites (16 tests) and a fresh native dialog check passed afterward.
- [x] 2026-10-25 UTC: Following authorization to submit the PR, refreshed remote
  main and dependency PR #3175, then created ready PR #3183 at `e0cb7e5` based
  on the OTP branch. This was the original stacked review arrangement.
- [x] 2026-10-25 UTC: The user requested one combined PR. Retain #3183, target
  main directly and include the complete OTP-fix ancestry; close #3175 as
  superseded after verifying the combined PR. Preserve both branches and
  all existing review history without rewriting commits.
- [x] 2026-10-25 UTC: Corrected two #3183 review findings: restore contactless local
  administrator sessions and preserve the validated admin return path before
  the login store clears its redirect parameter. The new regressions failed
  on the old implementation; the corrected source passed 106 focused tests,
  TypeScript, full frontend lint and 281 suites/3,452 frontend tests.
- [x] 2026-10-25 UTC: Native Chrome confirmed refresh/new-tab navigation
  preserves local administrator login without resubmitting credentials, and logout then
  local login returns to the exact original admin path including its query.
  Isolated browser/API/Web processes and synthetic credentials were cleaned up.
- [x] 2026-10-25 UTC: Rechecked the session-restoration and return-path fixes
  against code, regressions and native evidence; replied to and resolved both
  corresponding review threads. Corrected missing Progress timestamps.
- [x] 2026-10-25 UTC: Aligned browser HTTP loopback handling with the backend,
  including alternate 127/8, expanded IPv6 and mapped loopback addresses.
  Strict invalid-address, non-loopback and fake-host rejections remain covered.
  The old implementation failed the new regressions; the correction passed
  109 focused tests, all 281 suites/3,490 frontend tests, TypeScript, complete
  frontend lint and the production Web build.
- [x] 2026-10-25 UTC: The user authorized false-positive classification of
  GitGuardian incidents 38999521, 38999522 and 38999520 only. The dashboard
  could not open workspace 601861, but the native GitHub check exposed the
  approved action and listed exactly those three findings. The platform
  confirmed the classification at `c9a8d2c`: check 121319994457 completed as
  skipped with its false-positive title. This is not a clean scan, and the
  incident lifecycle rows remained Triggered. No broad exclusion or history
  rewrite was used.
- [x] 2026-10-26 UTC: Integrated main `ee125ce1` without rewriting history.
  At immutable head `21fd8586`, all seven Actions passed: one full backend CI
  run passed 15,197 tests with 15 skipped (911.30s, testmon selection disabled),
  eight separate contract tests passed, 282 frontend suites/3,492 tests passed,
  and four production-image browser cases passed on the first attempt. These
  CI results are separate from the earlier multi-run local union and do not
  count for later heads. CI did not collect new coverage.
- [x] 2026-10-26 UTC: Reproduced a new learner-login review finding with five
  failing controls for verified contactless local identities. Centralized the
  persisted local-credential fact and shared server-resolved login predicate
  across trial entry, interaction continuation, event emission and history.
  The nine targeted modules passed 258 tests and four subtests after the fix;
  negative cases retain guest, unverified-local and payment restrictions.
  Aggregate and DTO facts agree for active, unverified and deleted credentials.
  Subsequent-head CI still needs its own results; these are local regressions.
- [x] 2026-10-26 UTC: The broader local learn/user/common run recorded 5,157
  passes, 93 skips and two failures during loopback-listener setup with
  socket-bind `EPERM`. The skips comprise 92 real-Redis cases and one MySQL
  case. A required-Redis supplement stopped on its first Unix-socket bind
  error, with no tests counted as passed. No permissions were widened or tests
  suppressed; the new head's full CI must cover these environment-blocked cases.
- [ ] 2026-10-25 UTC: The single-check rerun request returned HTTP 404 through
  the current GitHub connection; no rerun is confirmed from that request.
  Do not retry it or widen permissions. Observe the final source revision's
  automatically triggered scan and CI separately.
- [ ] 2026-10-25 UTC: On a Docker/MySQL-capable runner, run the final head's
  runtime harness and fresh/existing MySQL acceptance before release.

## Surprises & Discoveries

Existing password login resolves phone/email accounts and cannot be treated as
an independent local username contract. The existing password reset requires a
verified contact. The default Docker gateway is HTTP, so browser setup must use
loopback/SSH forwarding or HTTPS. Console-issued codes bind to the selected
origin and never enter URLs or ordinary login/OTP/reset flows.

Plugin initialization may migrate tables before the core CLI runs. Empty-schema
provenance is captured before plugins, development repair shares that same
process, and workers/beat wait for prepared API startup before importing the
application. A conditional user-row write lock serializes local token issuance,
recovery and password changes on SQLite and MySQL; SELECT FOR UPDATE alone is
insufficient on SQLite. Managed setup transfers only configured demo IDs.
Schema downgrade refuses to drop mappings while local-account bindings remain.

## Decision Log

- Keep the completed universal-code fix; never introduce default credentials.
- Persist installation state and one-time code digests in SQL. Fresh-install
  provenance is captured before migrations on a genuinely empty schema; normal
  upgrades seed closed legacy state. User count is not setup authority.
- Both trusted console provisioning and Web initialization call one domain
  service. Account, roles, demo ownership and completion commit together.
- Add a distinct local administrator identity namespace and uniqueness. Do not
  mark an optional email or phone as verified or implicitly link it.
- Local administrator login is automatically available and independent of
  learner `LOGIN_METHODS_ENABLED`. Existing administrator accounts survive.
- Local recovery requires server-console access and revokes previous sessions;
  it does not reopen setup or create a public recovery bypass.
- The user's later requests authorize pushing this feature branch, publishing
  its ready PR and consolidating #3175 into #3183. Merge into main, auto-merge,
  deployment and production configuration changes remain outside the current
  authorization.

## Outcomes & Retrospective

Implementation, native browser acceptance, the production Web build and
repository checks are present in this isolated branch. Historical local backend
evidence comprises the 15,105-pass/107-skip run and the subsequent 120-pass Redis
module run, yielding 15,197 distinct passes across runs with 15 remaining skips.
The 95.18% coverage measurement belongs only to the former local run. Separately,
head `21fd8586` passed a single full backend CI run (15,197 passed/15 skipped),
282 frontend suites/3,492 tests and four container browser cases. PR CI did not
collect new coverage. No earlier OTP CI results count as feature verification.
The combined review target is #3183 against main; the previous stacked PR
arrangement is historical. Any additional review fixes require fresh CI for
their actual head and do not inherit earlier revision results.
Docker/MySQL container smoke is unavailable locally; discovering four Playwright
harness cases is not evidence that they ran. The CI browser results above cover
that immutable head's real MySQL/Redis happy paths; fresh/existing MySQL upgrade
and concurrency acceptance remains pending before release, as recorded in
Progress. The five MySQL-specific pytest cases and ten optional SaaS-plugin
cases remain skipped. The independent final identity
review remained blocked by the review tool; it was not retried through an
alternate model or wider permissions.

Source cost comparison: local passwords reuse the existing bcrypt cost-12
helper, with one password verification on an ordinary successful login and
bounded credential rechecks before token persistence. Installation state is one
SQL singleton; issuing a new code replaces its digest rather than appending
history. These are structural observations, not production latency or memory
measurements.

## Context and Orientation

- Domain state and CLI: `src/api/flaskr/service/user/installation*.py`.
- Local identity/provider: `local_accounts.py`, `auth/providers/local_password.py`,
  repository and token-store helpers in the same user service.
- HTTP boundary: `src/api/flaskr/route/installation.py`.
- Web routes: `/setup`, `/admin-login`, and the existing `/admin` gate.
- Durable product and analytics contract:
  [First-run administrator setup](../../product-specs/first-run-admin-setup.md).

## Plan of Work

Establish the installation/local-account models and migration first. Implement
the shared bootstrap transaction and provider contract, then wire sensitive
HTTP routes and console commands. Add the guided Web experience and startup
integration. Validate ordinary existing logins alongside first-run, retry,
upgrade, concurrency and recovery paths before preparing a reviewable patch.

## Concrete Steps

1. Add installation and local-account models; generate and inspect migration.
2. Implement console preparation, code issuance, direct creation and recovery.
3. Implement local credential creation, rate-limited login and locked token
   evidence confirmation; revoke durable/cache sessions after recovery commit.
4. Add bounded sensitive HTTP endpoints and preserve standard response/token
   infrastructure, request-origin and language handling.
5. Add UI, shared translations and allowlisted analytics with focused tests.
6. Update normal startup and installation guidance; run relevant checks and
   independent boundary review. Publish the authorized PR without merging or
   deploying it, and report the current head's CI results.

## Validation and Acceptance

A new instance creates and signs in its administrator with no external identity
provider. Concurrent and replayed setup has one winner; wrong, expired, rotated,
wrong-origin and consumed codes fail. Crash/retry and post-commit session errors
do not reopen setup. Existing, imported and zero-user legacy schemas remain
closed on upgrade. Restart, Redis loss and deleting users do not reopen setup.
Local account aliases never prove contact ownership. Recovery revokes sessions,
including a login racing an old password. Ordinary issued-code, password and
Google paths keep their contracts and cannot consume setup codes.

Run focused backend/Jest tests, user auth and relevant integration/migration
suites, full applicable backend checks, frontend type/lint, Compose semantic
validation and full pre-commit. Record actual skipped/unavailable Docker checks.
Compare local login/hash cost and bounded setup-state growth without inventing
latency or memory results.

## Idempotence and Recovery

The feature has a separate worktree and branch. SQL completion is authoritative;
cache loss is never eligibility. Console access can rotate an unconsumed setup
code or reset a local password, but cannot silently reopen completed Web setup.
Keep compatible local-auth/recovery code when disabling the wizard; an old image
that cannot read local credentials is not a safe rollback target.

## Interfaces and Dependencies

Public status returns `setup_required` and `local_admin_login_enabled` only.
Sensitive initialize/login endpoints return the existing `UserToken` shape.
Initialization codes are POST body secrets, never URL/analytics fields. No new
mandatory environment secret or runtime dependency is required. The original
OTP fix stays intact. Installation analytics use coarse exposure/attempt/result
events described in the product specification and remain best-effort.

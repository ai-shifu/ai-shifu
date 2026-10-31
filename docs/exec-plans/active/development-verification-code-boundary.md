# Confine Universal Verification Codes to Explicit Development Bootstraps

## Purpose / Big Picture

Prevent a legacy universal-code setting from authenticating phone/email users
or resetting passwords in ordinary deployments. Preserve normal issued-code
validation and the explicitly selected local development and test workflow.

## Progress

- [x] 2026-10-24 UTC: Read repository policies and traced all universal-code
  reads and login/password consumers against main `26b5da9a`.
- [x] 2026-10-24 UTC: Reconciled an independent read-only boundary and
  compatibility investigation, including the browser smoke harness.
- [x] 2026-10-24 UTC: Added a programmatic bootstrap capability plus a positive
  environment allowlist; removed release Compose and example default codes.
- [x] 2026-10-24 UTC: Passed 50 focused tests and 1,440 user/configuration tests;
  the unchanged base accepts unissued codes in all six auth-flow controls.
- [x] 2026-10-24 UTC: Independent candidate review found no concrete bypass or
  regression; its separate focused run passed 77 tests (overlapping coverage).
- [x] 2026-10-24 UTC: Full backend suite passed 15,081 tests and 50 subtests,
  with 15 skipped; application coverage is 95.25% against a 95.01% gate.
- [x] 2026-10-24 UTC: Passed Ruff, syntax checks, repository-wide pre-commit,
  architecture/UOW/harness guards, all three edited Compose configurations,
  and frontend type checking with locked dependencies and Node 22.23.4.
- [x] 2026-10-24 UTC: Following explicit user approval, committed and pushed
  `b091ca8` and created ready-for-review PR #3175. Its runtime harness passed
  authentication, admin, and learner smoke (3 tests). This is historical
  evidence for that head only; local container smoke remains unrun (no daemon).
- [x] 2026-10-24 UTC: Confirmed review discussion `r4367049467` and aligned the
  English/Chinese README quick-start, configuration, and login instructions.
- [x] 2026-10-24 UTC: Documentation head `a6d5501` passed all seven Actions
  workflows, including 15,081 backend passes (15 skips) and 3 runtime smoke tests.
- [x] 2026-10-24 UTC: Following explicit integration approval, merged main
  `8fe412d6` into this feature branch without conflicts or history rewriting;
  its frontend parser fix and this branch's auth/documentation fix are preserved.
- [x] 2026-10-24 UTC: Verified main's five frontend files byte-for-byte and
  preserved all auth/docs files; passed 50 focused auth tests, 8 parser tests,
  frontend types/formatting, and repository harness on the integrated tree.
- [x] 2026-10-24 UTC: Integrated head `32d29ae` passed all seven Actions
  workflows, including 15,081 backend passes (15 skips), 8 contract tests,
  and 3 runtime browser smoke tests.
- [x] 2026-10-24 UTC: A read-only refresh found main advanced to `2d7ee955`
  with lesson reset quotas (#3176), no new review findings, and strict branch
  protection requiring another synchronization. Merged it without conflicts;
  the existing auth patch and upstream quota implementation remain intact.
- [x] 2026-10-24 UTC: Main advanced again during validation with dependency
  update `07ece7f1` (#3162). Preserved that update in a normal conflict-free
  local merge; the attempted push was rejected before execution.
- [x] 2026-10-25 UTC: At the user's request, rebased the auth and setup-doc
  commits onto main `a37b6e69`. Preserved the existing local verification log
  and the remote branch's upstream changes; kept backup refs for both old tips.
- [x] 2026-10-25 UTC: Rebased head `3f5de08` passed all seven Actions workflows,
  including 15,101 backend passes (15 skipped), eight contract checks and three
  runtime browser smoke tests. These results cover only that OTP revision.
- [x] 2026-10-25 UTC: The user requested one PR for the OTP fix and the first
  administrator setup feature. Retain their full commit ancestry in #3183
  targeting main, with #3175 superseded and its reviews/history preserved.
- [ ] 2026-10-25 UTC: Follow the latest combined revision's exact-head CI at
  <https://github.com/ai-shifu/ai-shifu/pull/3183/checks>; earlier-head passes do
  not count for a newer revision. PR merge and deployment remain out of scope.

## Surprises & Discoveries

The shared consumer returned before code locking, expiry, attempts, and durable
consumption. SMS delivery also treated any universal setting as successful
delivery. Browser smoke tests depend on the shortcut, so environment-only
gating would either retain a misconfiguration risk or break the harness.

## Decision Log

- Require both explicit programmatic activation and an exact `development` or
  `testing` environment. The production app factory never activates this
  capability; environment values, debug, and testing flags cannot activate it.
- Recheck the environment at use time in the shared consumer and SMS delivery
  fallback. Disabled bypasses continue through ordinary validation rather than
  blacklisting a value that might coincide with a legitimate issued code.
- Keep the development factory separate and explicitly select it in development
  Compose and the runtime harness. No universal-code default is supplied.
- Preserve HTTP payloads, business errors, and existing single-use semantics.
  The user subsequently authorized commit, push, and ready-for-review PR
  publication with CI follow-up. Merge, deployment, production account access,
  and online security-configuration changes remain outside this task.

## Outcomes & Retrospective

The patch closes the shared bypass while preserving ordinary issued-code flows
and explicit isolated development/test usage. All runnable checks listed above
passed; the added executable runtime lines are covered. Runtime browser smoke
subsequently passed in CI for `b091ca8` and the documentation head `a6d5501`.
The frontend parser integration `32d29ae` passed all seven Actions workflows,
including the backend suite and runtime browser smoke. Local integration and
the subsequent rebase onto main `a37b6e69` passed fresh CI at `3f5de08`.
The user-authorized consolidation adds first administrator setup and its review
fixes in PR #3183 against main. That combined revision needs its own exact-head
CI; the earlier OTP-only passes do not establish its status. PR #3175 remains
available as historical review evidence after it is superseded.
Local container smoke was not run. Do not treat this plan as evidence that a
running deployment has been patched.

The remaining minimum acceptance is the existing runtime-harness stack and
`cd src/web && npm run test:e2e -- --project=runtime-harness-smoke`, which also
runs the shared authentication setup. It must cover authentication, the admin
operations page, and the learner course shell without server errors. Use the
workflow's synthetic environment and local isolated MySQL/Redis; this task does
not authorize a production deployment or a new system daemon installation.

## Context and Orientation

`src/api/app.py` owns runtime factories. The shared consumption boundary is
`flaskr/service/user/verification_codes.py`; phone/email login and password
setup/reset call it. `flaskr/service/user/utils.py` owns delivery preparation.
Configuration metadata is in `flaskr/common/config.py`. Development and runtime
harness Compose files select local bootstraps; release/latest images use
`app:app`. Tests use synthetic identities, SQLite, and fake delivery/cache.

## Plan of Work

Implement one shared development-code resolver, guarded by bootstrap capability
and environment. Reuse it for consumption and SMS fallback. Update fixtures and
local bootstraps, regenerate environment examples, and document upgrade actions.
Cover the attack and legitimate issued codes through real shared consumers and
login/reset entrypoints. Challenge the final patch in one independent review.

## Concrete Steps

1. Create the isolated branch from latest main and inspect owning rules/tests.
2. Implement the boundary and migrate explicit development/test consumers.
3. Run focused syntax, Ruff, configuration/auth regression checks.
4. Review one alternate input and all direct callers; obtain independent review.
5. Run full backend and repository validation and record exact results.
6. Prepare a unified patch and reviewable PR description; after the user's
   explicit approval, commit, push, create the ready PR, and follow exact-head CI.

## Validation and Acceptance

Production and ordinary factories cannot accept unissued universal codes or
pretend SMS delivery succeeded. Explicit development/testing apps preserve the
shortcut without altering cache/DB state. Normal SMS/email codes preserve
expiry, wrong-code errors, attempt limits, and single-use behavior. Login and
password reset cannot issue tokens or change passwords through the shortcut.
Run user/config tests, full backend tests, Ruff, Compose configuration checks,
repository harness, architecture and unit-of-work guards, and full pre-commit.
Report unavailable tools or checks without claiming verified completion.

## Idempotence and Recovery

All source work remains isolated to this branch. Publish it only under the
user's explicit PR authorization. Rebuild artifacts from the recorded base.
Do not read existing deployment credentials or copy real env
files. Compose validation uses disposable synthetic env values and does not
start services. Existing operators must upgrade API code/images and recreate
their processes; no running deployment is changed here.

## Interfaces and Dependencies

The optional `UNIVERSAL_VERIFICATION_CODE` key remains compatible with explicit
development/testing bootstraps. `create_development_app()` opts in through
`enable_development_verification_codes(app)`; normal factories do not. No new
runtime dependency or HTTP contract is introduced. Installation instructions
explain provider setup and removal of legacy deployment overrides.

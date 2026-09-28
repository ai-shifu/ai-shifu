# Custom manual credit validity

## Purpose / Big Picture

Allow ordinary operator reward/compensation grants to take a positive integer
and day/month/year unit, effective immediately. Preserve wallet, consumption,
expiry, transaction, notification and legacy API semantics. No schema migration.

## Progress

- [x] 2026-09-28: Inspected grant UI, DTOs, service, wallet and existing tests.
- [x] 2026-09-28: Baseline dialog Jest: 9 passed.
- [x] 2026-09-28: Backend baseline: 39 grant tests passed before backend edits;
  final relevant backend suites: 171 passed in isolated Python 3.12 / SQLite.
- [x] 2026-09-28: Additive API and persisted value/unit implemented; old CLI
  choices and positional grant-result constructor arguments preserved.
- [x] 2026-09-28: Initial main-based implementation: custom UI, all 8 locales, confirmation/result, analytics and
  regression coverage implemented. 36 frontend tests and 17 New York timezone
  preview tests passed with the original local dependencies.
- [x] 2026-09-28: Locked-dependency verification copy: type-check and all 36
  frontend tests passed. Full `lefthook run pre-commit --all-files` passed all
  20 checks, including Ruff, ESLint, translations, harness, boundaries and UOW.
  Main checkout developer-tool check passed with the isolated toolchain on PATH.
- [ ] Validate 15-day and 6-month grants in an authorized test deployment.
- [ ] 2026-09-28: User authorized deployment to cook02. Deployment repository
  documentation maps it to Docker CICD environment group `dev02`; GitHub access
  is available, but this session has no CICD deployment tool or documented
  platform URL. Requested the deployment entry point; no rollout started.

- [x] 2026-09-28: dev02 port validated: 171 backend tests, 36 frontend tests,
  type-check, developer tooling and all 20 full pre-commit checks passed.
  The first full gate normalized locale JSON ordering; the repeat passed.
  Evidence: /private/tmp/credit-dev02-{backend,ui,types,precommit-final}.log.
- [ ] Push the validated feature commit to origin/dev02 and confirm the remote SHA.

## Surprises & Discoveries

- System Python has no pytest; use an isolated temporary Python 3.12 environment.
- The legacy preset tuple is also the CLI choice list. Keep it unchanged and
  accept custom separately in the shared service, so CLI help never advertises
  a custom mode without value/unit flags.
- Existing request-id reuse returns the first persisted grant, even when a
  retry supplies a different valid amount/source/preset. Preserve this contract.
- The unrelated untracked course-share-preview directory must remain untouched.

## Decision Log

- 2026-09-28: Follow the user request to deliver directly to dev02 with a normal
  fast-forward push, preserving remote history. Do not merge unrelated main
  changes or include the untracked course-sharing preview.

- Use `validity_preset=custom`, `validity_value` (strict positive integer), and
  `validity_unit` (`day|month|year`). Keep legacy preset calls compatible.
- Reject custom fields with legacy presets and custom validity for referral grants.
- No business maximum; reject unrepresentable datetime values before writes.
- Days are 24 hours; calendar month/year addition clips missing days to month end.
- Backend UTC time is authoritative. UI previews are estimates only.
- Do not dispatch `build-latest.yml` for this feature: it publishes the shared
  `latest` tag and does not select the cook02 environment. Use the established
  dev02 pipeline after its entry point and target are verified. Source:
  `ai-shifu/deploy-config/docs/numbered-model-rollout.md` (read on 2026-09-28).

## Outcomes & Retrospective

Implementation and local SQLite validation completed. Deployed test-environment
verification remains pending. The user supplied https://cook02.dev.pillowai.cn/admin
and a dedicated test account. After the user manually logged in, browser inspection
confirmed that the ordinary credit dialog still exposes the six legacy presets,
with no custom value/unit input. The deployed frontend therefore cannot exercise
the new 15-day and 6-month flows yet; backend deployment status is unverified.
Screenshot evidence is saved locally at /private/tmp/credit-test-old-validity.jpg.
Credentials are not stored in this plan. No deployment or credit issuance was
performed during browser inspection. The user subsequently requested committing
and pushing this feature to dev02. Work now targets a dedicated checkout based
on dev02 commit 7db093516, retaining its unrelated contact-change work. Only the
feature changes were ported; its five supported locales were updated, and its
existing documentation paths and generated indexes were retained. The initial
main-based local changes remain in the original checkout. Deployment and
issuance/readback acceptance still require verification after the push.

The original checkout type-check reports pre-existing missing imports under the
untracked course-share-preview folder and an installed markdown-flow-ui 0.2.26
versus locked 0.2.29 mismatch. A temporary tracked-file verification copy uses
`npm ci --ignore-scripts` to check the real lockfile without touching those local
files or dependencies. Node is 24.12.0 (repository requests 22.16.0); npm reports
an engine warning. Final locked-dependency type-check, focused tests and full
pre-commit all passed. Existing lint warnings remain outside this feature.

Evidence logs live in /private/tmp/credit-backend-final.log,
/private/tmp/credit-ui-final.log, /private/tmp/credit-timezone-tests.log,
/private/tmp/credit-locked-typecheck.log and /private/tmp/credit-precommit-final.log.
Logs are local artifacts, not deployment evidence.

## Context and Orientation

The operator dialog submits the user grant DTO to the shifu operator service,
which calls billing/manual_credit_grants.py. That helper computes effective_to
and delegates to the existing wallet/ledger transaction. Only the input and
expiry-resolution layers change; the wallet implementation remains unchanged.

## Plan of Work

Extend request/response DTOs and the shared grant helper; persist duration
metadata and return it from the saved grant. Replace preset UI with value/unit,
show a refreshed UTC preview and authoritative success expiry. Update every
supported locale, design contract, tests and generated knowledge indexes.

## Concrete Steps

1. Record existing grant, package/referral and idempotency regression results.
2. Implement and test additive backend validity inputs, forwarding and outputs.
3. Implement UI state, validation, confirmation, success and tracking.
4. Run backend and frontend focused tests, type/lint, harness, boundaries and UOW.
5. Run dev-tool and pre-commit gates before any commit; report unavailable gates.

## Validation and Acceptance

Freeze time and compare all five duration presets against custom equivalents.
Cover active/inactive alignment, 15 days, 6/18 months, leap days, UTC serialization,
invalid/mixed/overflow inputs with zero writes, persisted retry results, concurrent
wallet uniqueness, notifications, historical metadata, consumption priority and
exact expiry boundaries. Keep package/referral tests green. UI tests cover empty
value, units, refreshed preview, submit/retry, privacy and tracking failure.
Test-environment smoke must read back bucket, ledger, balance and expiry for
15-day and 6-month grants; local SQLite tests are not deployed-environment proof.

## Idempotence and Recovery

Keep request-id semantics and notification dispatch unchanged. Deploy compatible
backend first, then frontend. Revert frontend first if necessary; retain backend
read support for custom metadata and never rewrite already-issued expiry dates.

## Interfaces and Dependencies

No new runtime dependencies. Optional result value/unit are read only from saved
metadata (null for old records). Public API preserves preset and expires_at.
See [billing design](../../billing-subscription-design.md) for the
canonical duration and analytics contract.

### Analytics contract

- Events: `operator_credit_grant_attempt`, `operator_credit_grant_result`.
- Eligible: authorized operator's custom ordinary credit HTTP submissions only.
  Exclude validation failures, double clicks, packages and referral grants.
- Trigger/count: once before each actual request, once on its terminal result;
  retries are new attempts, not new grants. No render/open events.
- Payload allowlist: `surface=operator_user_management`, `unit=day|month|year`;
  result also has `outcome=success|failed`.
- Consumer: operations grant-experience reporting; per-unit request success rate,
  not billing truth. No IDs/correlation payload; aggregate delivery may be lossy,
  so ratios are approximate rather than exact per-request conversion.
- New additive event names; no existing consumer migration. Never send account,
  amount, notes, dates, request IDs or raw errors. Tracking is fire-and-forget and
  both synchronous and asynchronous failures must not change grant behavior.

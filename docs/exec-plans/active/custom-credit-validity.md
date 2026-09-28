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
- [x] 2026-09-28: Custom UI, all 8 locales, confirmation/result, analytics and
  regression coverage implemented. 36 frontend tests and 17 New York timezone
  preview tests passed with the original local dependencies.
- [x] 2026-09-28: Locked-dependency verification copy: type-check and all 36
  frontend tests passed. Full `lefthook run pre-commit --all-files` passed all
  20 checks, including Ruff, ESLint, translations, harness, boundaries and UOW.
  Main checkout developer-tool check passed with the isolated toolchain on PATH.
- [x] 2026-09-28: Test deployment smoke verified 15-day and 6-month issuance,
  ledger rows and balance; user also confirmed the manual flow passed.
- [x] 2026-09-28: Fixed input/select height and confirmation-label wrapping;
  verified deployed controls are 40px high and the long label no longer overlaps.
- [x] 2026-09-28: Prepared a focused branch from main 954c293e1, including all
  eight supported locales and the tested layout/copy fixes, excluding unrelated
  dev02 history and local course-share-preview files.
- [x] 2026-09-28: Main-based branch passed 171 backend tests, 36 frontend
  tests, type-check, developer-tool check and all 20 full pre-commit gates.
- [x] 2026-09-28: Aligned CLI input with custom durations: require value/unit,
  remove the preset flag and implicit subscription alignment, and include
  duration value/unit in generated request IDs.
- [x] 2026-09-28: Verified CLI duration persistence, rejected inputs and retry
  behavior (109 CLI/failure-contract tests), plus 142 shared validity, wallet,
  admin, compensation-script and DTO compatibility tests. All 20 repository
  pre-commit gates passed with the pinned local tooling.
- [ ] Read back actual test database bucket and ledger expiry timestamps.
- [ ] Production release (separate from this PR preparation).

## Surprises & Discoveries

- System Python has no pytest; use an isolated temporary Python 3.12 environment.
- Legacy presets remain accepted by the API and shared service. The CLI now
  forwards custom durations only; the compensation script calls the shared
  service directly and retains its explicit subscription alignment.
- Existing request-id reuse returns the first persisted grant, even when a
  retry supplies a different valid amount/source/preset. Preserve this contract.
- The unrelated untracked course-share-preview directory must remain untouched.

## Decision Log

- Use `validity_preset=custom`, `validity_value` (strict positive integer), and
  `validity_unit` (`day|month|year`). Keep legacy API/service preset calls compatible.
- 2026-09-28: The user requested removing the CLI preset parameter. Require
  `--validity-value` and `--validity-unit`, with no implicit validity default.
  Generate daily request IDs from the custom value/unit too; explicit IDs still
  return the original persisted result. Retrying a former preset CLI grant must
  reuse its original request ID explicitly.
- Reject custom fields with legacy presets and custom validity for referral grants.
- No business maximum; reject unrepresentable datetime values before writes.
- Days are 24 hours; calendar month/year addition clips missing days to month end.
- Backend UTC time is authoritative. UI previews are estimates only.
- User accepts at most one second between expected and persisted expiry.
  Bucket and ledger expiry must still agree, and spending must stop exactly at
  the persisted expiry. This tolerance does not relax retry or duration rules.

## Outcomes & Retrospective

The CLI now requires an explicit custom duration and no longer accepts preset
flags. Focused verification passed 251 backend tests, including the two formerly
failing DTO compatibility assertions. No live credit issuance was used for this
CLI verification; the separate deployed-database acceptance below remains open.

The test deployment includes the feature and follow-up UI fixes through
commit a3971f047. Independent CICD success was followed by browser verification;
GitHub Actions records are not the source of truth for that pipeline.

Three credits were issued to the dedicated test account: two reward grants
(15 days and 6 months) and one compensation grant (6 months). Balance and ledger
rows were read back. The final confirmation-layout check did not issue a grant.
No production deployment was performed, and credentials are not stored here.

A 15-day success response and subsequent account readback differed by one second.
The user accepted that tolerance. Database datetime precision is a possible cause,
not a confirmed diagnosis: actual bucket/ledger readback remains unavailable.
The UI does not expose all required batch fields. Local SQLite coverage proves
expiry-boundary behavior in tests, not the contents of deployed MySQL rows.
This remaining release check must be completed before declaring production ready.

Prior local validation passed 171 backend tests, 36 frontend tests, the 17 preview
tests under America/New_York, type-check and all 20 pre-commit checks. The current main-based branch also passed 171 backend tests, 36 frontend tests,
type-check and all 20 full pre-commit gates. The first gate run rejected partially
staged generated documentation; staging the complete change resolved it.
Node is 24.12.0 while the repository requests 22.16.0; record the engine warning.
Use the lockfile dependency install and isolated Python 3.12 test environment.
Local screenshots include /private/tmp/credit-validity-final-deployed.jpg,
/private/tmp/credit-validity-final-grant-success.jpg and
/private/tmp/credit-confirm-wrap-deployed.jpg; these are local evidence only.

## Context and Orientation

The operator dialog submits the user grant DTO to the shifu operator service,
which calls billing/manual_credit_grants.py. That helper computes effective_to
and delegates to the existing wallet/ledger transaction. Only the input and
expiry-resolution layers change; the wallet implementation remains unchanged.
The billing CLI calls the same helper with `validity_preset=custom` and the two
required duration options; it does not calculate expiry independently.

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
CLI coverage checks required positive integer/unit input, removed preset flags,
UTC duration persistence, generated-ID separation, and persisted explicit-ID
retries. The existing DTO serialization and Swagger assertions must include the
additive nullable duration fields.
Test-environment smoke must read back bucket, ledger, balance and expiry for
15-day and 6-month grants; local SQLite tests are not deployed-environment proof.

## Idempotence and Recovery

Keep explicit request-id semantics and notification dispatch unchanged. CLI
automation must migrate to the two custom duration options; the generated ID
now incorporates both duration fields. Deploy compatible
backend first, then frontend. Revert frontend first if necessary; retain backend
read support for custom metadata and never rewrite already-issued expiry dates.

## Interfaces and Dependencies

No new runtime dependencies. Optional result value/unit are read only from saved
metadata (null for old records). Public API preserves preset and expires_at.
See [billing design](../../design-docs/billing-subscription-design.md) for the
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

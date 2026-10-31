# Standard password and session consistency

## Purpose / Big Picture

Prevent a standard password login from issuing a session using a password
verification made obsolete by a committed password write. Prevent a stale
old-password check from overwriting another committed password. Verification-code
recovery must atomically change the effective account password and revoke all
old durable sessions; cache eviction follows commit. Ordinary password changes
retain the existing session policy.

## Progress

- [x] 2026-10-31 07:21 UTC: Fetched origin/main at `0aeb9e8570f2a4977bd80e1fd9940ce8f91c275a`; created isolated branch `sunner/password-session-consistency` and copied local environment files without exposing values.
- [x] 2026-10-31 07:21 UTC: Read layered backend/user rules and auth workflow; existing password/UOW route controls pass (22 tests).
- [x] 2026-10-31 07:36 UTC: Established five ordinary-account failures on unchanged main: stale login after reset/change, stale change overwrite, and reset retention of active/expired tokens.
- [x] 2026-10-31 07:36 UTC: Implemented repository locks, verified-hash versions, current identifier revalidation, effective-password recovery and commit-bound session revocation; 15 focused new SQLite cases pass.
- [x] 2026-10-31 07:36 UTC: Passed 23 new MySQL regressions, 36 MySQL provider/route cases and five real InnoDB concurrency/evidence cases; independent candidate review found no concrete in-scope bypass or regression.
- [x] 2026-10-31 07:39 UTC: Completed full backend suite (14,904 passed, 112 skipped, three failures reproduced on untouched main), source-mapped type comparison (zero new diagnostics), and all-files pre-commit gate (all 21 commands passed).
- [x] 2026-10-31 07:39 UTC: Prepared the local commit and reviewable PR description on the isolated branch; publication and merge remain outside this task authorization.

## Surprises & Discoveries

- Main already locks user/contact/password rows before password token persistence,
  but confirms identifiers only, not the verified hash version.
- ORM locking queries need `populate_existing()` when the identity map already
  contains a pre-verification credential; a database lock alone does not refresh it.
- Main login/change select the oldest active password row account-wide, whereas
  reset writes by recovery identifier. Recovery through another linked contact
  must update the effective password, rather than add an unused credential.
- Existing session-management revocation evicts after a possibly nested UOW and
  selects active rows only. It cannot be reused for atomic recovery unchanged.

## Decision Log

- Use the account row as the common lock, then credential rows, then token rows.
  Password writes and every token-store save share this order; no Redis guard is
  trusted as the password consistency boundary.
- Capture a SHA256 version of the bcrypt hash actually verified. Confirm user,
  current contact, credential identity and this version under locks in the same
  UOW as persistence. Never put plaintext passwords or bcrypt hashes in metadata.
- Keep existing phone/email contact resolution. A password credential identifier
  is evidence about a row, never a permanent login alias.
- Recovery updates the effective oldest password row. It deletes all token rows,
  including expired rows; cache/token-row markers and attribution are evicted only
  through `uow.on_commit`. Durable rows remain authoritative if eviction fails.
- Keep ordinary password-change sessions. No installation state, local admin,
  wizard, Google linkage, frontend or universal-code configuration changes.
- Preserve existing verification-code consumption semantics, including fail-closed
  cache tombstones; session cache rollback behavior is verified separately.

## Outcomes & Retrospective

Local implementation and validation are complete. The original five ordinary-account
triggers fail on main and pass with the patch. Final combined MySQL execution
passes all 28 regression/concurrency cases; provider/route controls pass 36 cases.
Independent candidate review found no concrete surviving in-scope bypass or
introduced regression. Repository-wide lint, formatting, harness and all-files
hook pass. Whole-backend and typing commands retain documented baseline failures;
they are not reported as clean. No deployment or production-account probe was
performed, and local reproductions do not establish production exploitability.

## Context and Orientation

`src/api/flaskr/service/user/auth/providers/password.py` verifies passwords and
prepares a non-persisted token. `src/api/flaskr/route/user.py` confirms evidence
and persists it in a UOW. `password_flow.py` owns password writes, `repository.py`
owns credential access, and `token_store.py` owns durable/cache session state.
`flaskr/dao/uow.py` defers external effects until the outermost commit.

Reference-only checkout: `/Users/sunner/Documents/Codex/2026-10-24/task-6/ai-shifu-setup`
at `90da103dc621272031ef288434a9d246dfb7f16e` (PR #3183). Do not modify it or
cherry-pick its installation-coupled patch.

## Plan of Work

First reproduce stale login evidence, stale password replacement and missing
recovery revocation using normal accounts and real bcrypt/ORM/UOW paths. Then
add repository-native locks, hash-version evidence, recovery revocation and
commit-bound cache effects. Test transaction failures and both serialization
orders with separate connections on a disposable local MySQL server.

## Concrete Steps

Run tests from `src/api` using the existing Python 3.11 environment. Default
tests use isolated file-backed SQLite; use `TEST_SQLALCHEMY_DATABASE_URI` only
for a disposable local test database to validate InnoDB locks. Run targeted user
coverage before the full backend suite. Run Ruff, formatting, applicable type
checks, repository harness, architecture and UOW gates, and the required
all-files pre-commit hook. Record exact results below before delivery.

## Validation and Acceptance

A stale successful bcrypt check must fail final issuance after a password write.
A competing password write must reject a stale old-password check. Recovery must
commit password and durable-session deletion together, and rollback must retain
both old password and sessions without eviction. Cache failures must not revive
revoked rows. Real InnoDB tests must prove reset and issuance mutually exclude
one another. Normal login/change/recovery and identifier semantics must remain.

## Idempotence and Recovery

Use unique test users/databases and disposable local data; never use deployment
configuration or real accounts. Preserve the source checkout and #3183. Undo
only changes owned by this task. Local commits are the review boundary; pushing,
PR publication and merge require further authorization.

## Interfaces and Dependencies

Reuse provider/factory, repository, token store and UOW. No schema migration or
new production dependency is planned. After this foundation lands, #3183 should
remove duplicate password version, lock and reset-revocation changes while
retaining installation-specific policy; this task does not rewrite that branch.

## PR #3183 overlap and follow-up

After this foundation is merged through a separately authorized PR, rebase #3183
and remove its duplicate standard-password implementation rather than cherry-pick
this patch back into the installer branch:

- Reuse `password_utils.password_credential_version`, the provider's
  `credential_version` evidence and the route's final locked confirmation.
- Reuse repository account/effective-credential locks and locking identifier
  reads instead of retaining #3183's password-flow-local locking helpers.
- Reuse the optimistic old-hash check in ordinary `change_password`.
- Reuse `token_store.revoke_all` and the atomic ordinary-code reset transaction.
- Keep installation-only state, account provisioning, wizard policy, preview
  migration and password-policy additions in #3183. They are absent here.

This foundation additionally serializes every durable token save with recovery,
updates the effective password through alternate recovery contacts and documents
the existing ordinary-change session policy. Reconcile installer-specific
callers against these contracts during #3183's rebase; this task does not modify
that checkout or branch.

## Verification record

Commands below run from the repository root unless they start in `src/api`.
The backend interpreter is the pre-existing Python 3.11.18 environment; its
dependencies were not changed.

- Before patching, `python -m pytest tests/service/user/test_password_session_consistency.py -q -p no:testmon --tb=short --show-capture=no`
  (from `src/api`) failed all five initial triggers: stale login after reset and
  change, stale change overwrite, active and expired token retention on reset.
- Initial existing controls: password routes and user UOW failure paths,
  22 passed. Candidate's expanded SQLite regression/provider/route run: 59 passed.
- Disposable MySQL 8.4.13, InnoDB, REPEATABLE-READ, UTC, socket only:
  23 regression cases, 36 provider/route cases and five concurrency/evidence
  cases passed. The final combined regression/concurrency run passed all 28 in
  29.08 seconds. Actual account-row waits were observed with independent
  connection IDs in `performance_schema.data_lock_waits`. Concurrent same-code
  recovery used the actual in-memory cache provider lock and original DB/code
  validator. Event/barrier hooks only arrange ordering.
- `python -m pytest -p no:testmon tests -q --tb=short` (from `src/api`):
  14,904 passed, 112 skipped, three failed, 505.45 seconds. Failures are
  `test_transitive_dotenv_loader_cannot_override_test_environment`,
  `test_legacy_package_session_resumes_its_remaining_pending_answer`, and
  `test_litellm_1106_native_adapter_contracts`. All three exact nodes fail with
  the same signatures on an immutable `git archive` snapshot of the original
  main (three failed in 1.64 seconds); no unrelated source or dependency fixes
  were included. Skipped tests are not counted as validated; the MySQL-specific
  regression/concurrency cases were run separately and passed.
  Installed LiteLLM is 1.102.0; the repository test expects 1.106.2.
- The attempted CI-style `-n 2 --dist loadfile` invocation could not run because
  this environment lacks pytest-xdist; the complete suite was run sequentially
  instead. No test-selection cache was used.
- `mypy --follow-imports=skip --ignore-missing-imports` over the six changed
  production files: main has 38 diagnostics, candidate has 37. Source mapping
  confirms all 37 are inherited; one old Optional-argument diagnostic is gone.
  The whole command remains failing, so this is no-new-diagnostics evidence,
  not a claim of clean repository typing. No typing rules were suppressed.
- `ruff check .` and `ruff format --check .` with pinned Ruff 0.17.3 passed
  (1,843 Python files formatted). Compile/import checks passed.
- Repository harness, architecture boundary check (zero new violations), UOW
  commit-site ratchet (zero grandfathered sites), and dev-tools doctor passed.
  `lefthook run pre-commit --all-files` passed all 21 commands in 40.59 seconds
  after regenerating tracked indexes. Frontend ESLint/Prettier also passed as
  part of that required hook; no frontend files changed.
- No frontend/browser harness changes: frontend unit/e2e suites, Docker
  packaging, remote CI, coverage threshold, publication and deployment were
  not run. The full backend suite is not a coverage-threshold measurement.

The all-files hook first found the system Python missing markdown-it-py. A
task-local Python shim selects the already-complete environment without changing
shared dependencies; pinned Ruff remains on PATH. A second run exposed generated
index staleness because the new ExecPlan had just become tracked; regenerate
after staging it. The final rerun passed; these setup failures did not change
production code.

## Local delivery

Branch: `sunner/password-session-consistency`, based on main
`0aeb9e8570f2a4977bd80e1fd9940ce8f91c275a`. Review the local Conventional Commit
before any remote action. PR title: `fix: keep passwords and login sessions consistent`.
The standalone PR description is prepared at
`/private/tmp/ai-shifu-password-session-delivery/PR.md`; the local handoff includes
publication commands that must only be executed after separate user authorization.
No branch push, PR creation, merge, deployment or production configuration change
was performed. The source checkout and read-only #3183 checkout were preserved.

# Authenticate Google subjects without trusting unverified email

## Purpose / Big Picture

Google OAuth must authenticate a previously bound provider subject independently
of mailbox verification. An unverified email claim must never select another
account, replace a Google subject, copy a guest profile into that account, or
issue its session. Only the explicit boolean `true` enables email association.
This independent foundation is based on main `ea4a31fba459d99d205dbe404190b0caef3ccc33`.

## Progress

- [x] 2026-10-31 09:13 UTC: Established isolated branch and source-to-session trace.
- [x] 2026-10-31 09:13 UTC: Ran new regressions before runtime edits: 41 failed,
  7 passed; existing Google tests passed 6/6.
- [x] 2026-10-31 09:16 UTC: Added strict claim semantics and subject-first lookup.
- [x] 2026-10-31 09:24 UTC: Completed compatibility, rollback/retry, lint,
  syntax, type-baseline comparison and full repository hook checks.
- [x] 2026-10-31 09:24 UTC: Reconciled one independent candidate review and
  prepared the local commit contents and standalone PR description.

## Surprises & Discoveries

- `ensure_user_for_identifier` repeats canonical/email lookup internally; merely
  skipping the provider's first email lookup leaves a second selection path.
- Google credential identifiers are consumed as email by operator, billing and
  admin code. Keep that representation while authenticating by exact subject.
- An existing display-name test depended on unverified email association. It now
  seeds a matching Google binding and preserves the same authorized behavior.
- The callback uses server-side code exchange and access-token-authenticated
  userinfo. It does not read identity claims from a client-supplied decoded ID
  token. Existing signed state, callback URI and initiator checks remain intact.

## Decision Log

- Use the repository for exact active subject lookup, including a Python equality
  check for database collations that compare case-insensitively.
- Preserve the binding identifier and trusted email credentials when a bound
  subject presents an unverified changed email. Name/avatar/language may update.
- Reject unverified email-based account selection before mutation, profile
  transfer, grants or tokens. Verified mailbox linking retains the supported
  account association path, adding a distinct subject binding instead of
  replacing a different subject's row.
- A bound subject always authenticates its own account. If a verified changed
  email belongs to another account, skip mailbox association and preserve both
  accounts' trusted identifiers and credentials.
- Subject-keyed credential upsert is opt-in; existing non-Google consumers keep
  identifier-keyed behavior. Deleted other-subject rows remain deleted.
- One independent candidate review reproduced two compatibility gaps in the
  initial candidate: unverified preclaims blocked subsequent verified owners,
  and a verified mailbox collision blocked an existing subject. Both have
  focused regressions in the final patch.
- Fresh unverified accounts use their random user ID as canonical identity and
  have no email credential. Current guest association keeps its canonical ID.
- Keep existing transaction ownership and post-commit token-cache publication.
  No schema, installation, password alias, concurrency or frontend changes.

## Outcomes & Retrospective

Implemented and locally validated. An exact-base reproduction used a normal
synthetic account with a valid bcrypt password hash and existing creator/operator
roles. A different Google subject with `email_verified=False` selected that
account and persisted its privileged session without changing the password.
The fixed regression rejects this callback twice, preserving account, password,
Google bindings, guest profile, roles and sessions.

Tests use synthetic identities, a Google HTTP-session substitute and local
SQLite. They establish application behavior given provider claims, not production
exploitability or Google's issuance of a particular unverified address. No real
Google account, production identity or production configuration was used.

## Context and Orientation

`src/api/flaskr/service/user/auth/providers/google.py` owns OAuth callback account
selection and token creation. `repository.py` owns account/credential persistence;
`token_store.py` publishes caches only after the outer unit of work commits.
`route/user.py` joins the same transaction. Auth workflow instructions are in
`src/api/skills/user-auth-flows/SKILL.md`.

## Plan of Work

Reproduce ordinary email/password account selection before the patch. Enforce
strict verification semantics and resolve existing Google subjects first. Keep
verified mailbox linking, new accounts and current guest linking compatible.
Exercise rejection, rollback after session write, retries and surrounding auth
flows; then obtain one independent bypass/regression review.

## Concrete Steps

From the repository root, run Ruff on changed Python files and the repository
harness checks. From `src/api`, run the Google auth, Google OAuth boundary,
learner-profile sign-in merge and new Google email-linking suites, followed by
`pytest tests/service/user/ -q`. Run the dev-tool doctor and full lefthook gate
before committing. Record static type-check results against the base if the
repository has no configured checker or contains existing diagnostics.

## Validation and Acceptance

Missing/false/null/string/numeric/container claims cannot select existing email
or password accounts. Different subjects cannot replace a binding. Bound
subjects still authenticate with false/malformed verification claims and changed
email. Verified-email account linking, guest linking and ordinary creation work.
Rejected calls preserve account ownership, credentials, profile, roles and
sessions. Injected failure after token persistence rolls back writes and drops
cache publication; retry creates exactly one binding and usable session.

## Idempotence and Recovery

Use only this isolated worktree and branch. Publication and review follow-up
are authorized for the independent PR #3261. Production calls, deployment,
merging and modifying #3183 remain outside the authorized scope. Rejected and
failed callbacks can retry without partial writes. Do not alter the independent
password task or the first-administrator branch.

## Interfaces and Dependencies

No dependencies or schema changes. Add an exact-subject repository lookup and
an opt-in `match_by_subject` argument on credential upsert; existing callers keep
their defaults. Keep OAuth response types and email-shaped Google identifiers
compatible. A verified changed mailbox updates the Google email label; an
unverified or conflicting mailbox preserves the existing label and trust state.

Overlap with [PR #3183](https://github.com/ai-shifu/ai-shifu/pull/3183), inspected
at `90da103dc621272031ef288434a9d246dfb7f16e`: strict `email_verified is True`,
unverified existing-account rejection, prevention of unverified subject
replacement and associated Google tests. After this foundation lands, rebase that PR and remove duplicate
Google changes while retaining its separately owned installation behavior. This
task does not modify that branch or cherry-pick its installation contracts.


## Verification Results

These results describe the initial local foundation commit `0a3efa514`.
The later publication and review follow-up are recorded below.

Commands use `/Users/sunner/src/ai-shifu/.venv/bin/python` (Python 3.11), with
Ruff 0.17.3 on PATH. A local `python3` wrapper selects that interpreter for hooks;
frontend hook tooling reuses the source checkout's ignored `node_modules`.

| Gate | Command / observation | Result |
| --- | --- | --- |
| Original behavior | Existing `test_google_auth.py` before changes | 6 passed |
| Red regressions | New email-linking suite before runtime edits | 41 failed, 7 passed; later refined verified-mailbox compatibility expectations |
| Explicit impact on base | Exact `git archive ea4a31fba` plus synthetic callback/account/token assertions | 1 passed, confirming existing privileged account session issuance |
| Security and compatibility | `python -m pytest tests/service/user/test_google_email_linking.py tests/service/user/test_google_auth.py tests/service/user/test_google_oauth_boundaries.py tests/service/user/test_learner_profile_sign_in_merge.py -q --tb=short --show-capture=no` from `src/api` | 122 passed |
| Owning service | `python -m pytest tests/service/user/ -q --tb=short --show-capture=no` from `src/api` | 974 passed, 5 skipped in 66.61 seconds |
| Syntax | `python -m compileall -q` on four changed Python files | Passed |
| Lint and formatting | `ruff check` and `ruff format --check` on four changed Python files | Passed |
| Full repository gate | `lefthook run pre-commit --all-files` | All 21 commands passed in 49.64 seconds |
| Dev tooling | `python scripts/check_dev_tools.py` | Passed, including frontend tools |
| Repository contracts | Harness, architecture and UOW checks | Passed; 120 inherited architecture entries, zero new; zero grandfathered commit sites |
| Focused static types | mypy 2.4.1, same config on exact base and final candidate | Command exits 1: 58 inherited diagnostics versus 64 on base, zero new, six removed; new regression file has zero diagnostics |

The five skipped tests require MySQL row-lock infrastructure and belong to the
pre-existing password concurrency suite. They are not counted as validated here.
SQLite tests use the repository's existing test schema fixture; Alembic migrations
are not run because this patch has no schema changes.

An early full-hook attempt used Homebrew's default Python and failed to import
`markdown_it`. Selecting the already installed test interpreter fixed the
execution environment; the final full gate passed without dependency edits.
Two existing warnings concern Pydantic class-based configuration and `audioop`.

The repository has no configured backend type-check gate. The focused type
comparison follows the existing password-session plan's configuration. From
`src/api`, its reproducible command is:

```sh
UV_CACHE_DIR=/tmp/google-auth-typecheck-uv-cache \
UV_TOOL_DIR=/tmp/google-auth-typecheck-uv-tools \
uvx --from mypy==2.4.1 mypy \
  --python-executable /Users/sunner/src/ai-shifu/.venv/bin/python \
  --follow-imports=skip --ignore-missing-imports \
  --cache-dir /tmp/google-auth-typecheck-jsjsj65i/cache-candidate-final \
  flaskr/service/user/auth/providers/google.py \
  flaskr/service/user/repository.py \
  tests/service/user/test_google_auth.py \
  tests/service/user/test_google_email_linking.py
```

Not run: complete backend suite outside the owning user module, frontend
unit/E2E suites, real Google integration, MySQL-specific password tests, Docker
packaging or remote CI. No push, PR publication, deployment or merge occurred.

## Files Changed

- `src/api/flaskr/service/user/auth/providers/google.py`: trust and account
  selection boundary; preserve existing OAuth transport/state checks.
- `src/api/flaskr/service/user/repository.py`: exact subject lookup and opt-in
  subject-keyed credential persistence.
- `src/api/tests/service/user/test_google_auth.py`: reusable callback arguments,
  accurate result type and authorized display-name control.
- `src/api/tests/service/user/test_google_email_linking.py`: 66 security,
  compatibility, rollback and retry parametrizations.
- This completed plan and generated plan/doc indexes: independent delivery,
  validation limits and #3183 reconciliation instructions.

## PR Review Follow-up

Published [PR #3261](https://github.com/ai-shifu/ai-shifu/pull/3261) as non-draft
on `0a3efa514`. Its initial CI passed: backend contract/targeted tests,
production image smoke checks, fast-value/browser runtime checks, lint, static
checks, CodeQL and GitGuardian. Frontend tests used their expected no-change
skip; Cursor's security check was neutral.

[Devin's admin-grant finding](https://github.com/ai-shifu/ai-shifu/pull/3261#discussion_r4431266041)
identified a real compatibility regression: an exact, previously verified Google
subject could authenticate with an unverified current mailbox but missed the
explicitly configured admin/demo grants. The focused reproduction on the
initial candidate produced four failures and four passing unverified-binding
controls.

Capture historical verification only from the exact active subject credential
before updating it. Permit admin/demo grants for that prior trust or a newly
verified mailbox association. The shared helper still enforces its deployment
flag and explicit admin context. First-account initialization remains gated by
current verified mailbox association; no installation behavior changes.

The follow-up adds eleven real-persistence regressions covering creator/demo
grants, unverified-binding exclusions, changed unverified mailbox, retries,
disabled flags, non-admin logins and rollback. Local validation: 75 focused
Google/grant-helper tests passed; the complete user suite passed 985 tests with
five existing MySQL-only skips. Ruff/formatting/compilation passed. Focused mypy
still exits 1 with the same 58 inherited diagnostics and none in the new tests.
An independent source review found no concrete remaining concern in this fix.

## Proposed Pull Request

Title: `fix: protect accounts during Google sign-in`

Google sign-in previously treated truthy email-verification claims as verified
and could select an existing email/password account or overwrite a Google
subject using an unverified matching address. Authenticate existing Google
bindings by exact subject, require the explicit boolean `true` for mailbox
authority, and keep distinct subjects in separate credential rows. Bound subjects
continue to log in when current mailbox association is untrusted or conflicts.

Keep verified mailbox linking, fresh accounts and current guest/account linking
compatible. Add rejection, preserved trust/permissions, duplicate subject labels,
deleted bindings, rollback after session persistence and retry regressions.
Preserve configured admin/demo grants for exact subjects with historical verified
bindings even when the current mailbox is unverified. Validation: 75 focused
Google/grant-helper tests and 985 user-service tests passed; five unrelated
MySQL-only cases skipped. Full repository hooks passed. Focused mypy reports no
new diagnostics (58 inherited versus 64 on base); its command remains failing.
This PR is independent of #3183; remove overlapping Google validation changes
from that PR after this foundation lands, retaining its installation behavior.

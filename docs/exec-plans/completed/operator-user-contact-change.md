# Operator User Contact Change

> Lifecycle review, 2026-09-26: Completed original scope. Contact-change workflow and recorded focused tests are delivered. Merge evidence: [#2948](https://github.com/ai-shifu/ai-shifu/pull/2948) (`a0b1e3d0e`)

## Purpose / Big Picture

Allow an operator to replace one user's primary contact login identifier without changing
the user's `user_bid`, so learning history, orders, credits, permissions, and
other business data remain attached to the same account. Phone deployments
replace phone numbers and email deployments replace email addresses according
to `LOGIN_METHODS_ENABLED` / the shared contact-mode resolver. The old contact
becomes available for a new registration, the new contact must not already
belong to an account, and every existing login session is revoked after a
successful change.

## Progress

- [x] 2026-09-24 10:00 CST: Confirmed the product contract and inspected user
  credentials, password login, token persistence, and operator user detail UI.
- [x] 2026-09-24 10:10 CST: Add backend replacement service, route contract,
  safe logging, and focused rollback/session tests.
- [x] 2026-09-24 10:20 CST: Add the operator confirmation dialog, translations,
  request types, analytics contract, and focused frontend tests.
- [x] 2026-09-24 12:10 CST: Run focused and shared verification and document the
  outcome.

## Surprises & Discoveries

- Learning, order, billing, referral, and permission data use `user_bid`, so
  preserving that identifier avoids data migration.
- The account's phone or email is an `AuthCredential`, while `UserInfo.user_identify`
  and a password credential can also retain the old identifier and therefore
  must be updated consistently.
- Session revocation deletes durable token rows first and then evicts cache
  entries; the existing helper must be extended to revoke every session for an
  operator-triggered identity change.

## Decision Log

- Decision: implement a dedicated operator contact-change action instead of a
  generic editable user profile.
- Decision: resolve the allowed contact type from the deployment login-method
  configuration: phone for the CN deployment and email for the COM deployment.
- Decision: reject a contact linked to any other active account; do not merge
  accounts automatically.
- Decision: soft-delete old credentials of the selected type and create a new
  verified credential under the same `user_bid`.
- Decision: require a reason and an exact repeated-contact confirmation in the
  Cook Web dialog.
- Decision: do not add an audit table in this release; emit structured security
  logs with masked contact values, operator, target, reason presence, and result.
- Decision: revoke all target-user sessions after the database change commits.
- Decision: measure dialog exposure, submission, and terminal outcome with the
  `operator_user_contact_change_*` Umami family. Eligible users are active
  operator-managed accounts; one exposure is emitted per dialog open, one
  submission per single-flight request, and one result per request. Payloads
  contain only `contact_type` (`phone` or `email`) and, for results, `result`
  (`success` or `failed`). Phone numbers, email addresses, user IDs, reasons,
  and raw errors are excluded. Operations reporting consumes the event family
  to measure adoption and success rate over 7- and 30-day periods.

## Outcomes & Retrospective

Operators can now modify the configured phone number or email address from the
user detail page without changing the user's business identity. The backend
atomically replaces the verified contact credential, updates the aligned
password identifier and user summary, rejects contacts owned by another active
account, and revokes every existing session. The dialog requires repeated
entry and a reason, prevents duplicate submission, and reports only allowlisted
analytics properties. Verification completed with 4 focused backend tests, 25
focused and adjacent frontend tests, frontend type checking and lint, Ruff,
translation validation, architecture-boundary validation, and the UoW ratchet.

## Context and Orientation

Authentication persistence lives in `src/api/flaskr/service/user/`, operator
routes live in `src/api/flaskr/service/shifu/admin_operations/route.py`, and the
operator detail UI lives under
`src/web/src/app/admin/operations/users/[user_bid]/`. Shared translations live
in `src/i18n/*/modules/operations-user.json`.

## Plan of Work

1. Add a user-domain service that validates and atomically replaces the configured contact
   and aligned password/user-identify fields.
2. Extend session helpers with a revoke-all operation and call it only after
   the identity transaction commits.
3. Expose an operator-only POST route with a typed request and stable response.
4. Add a guarded, single-flight confirmation dialog to the user detail page.
5. Define a privacy-safe Umami event family for dialog exposure, attempt, and
   terminal result without collecting phone numbers or free-form reasons.
6. Add backend and frontend regression coverage, then run shared gates.

## Concrete Steps

1. Add backend request/result DTOs and service tests for both phone and email modes first.
2. Implement conflict detection, row locking, credential replacement, password
   alias update, safe logs, and full session revocation.
3. Register the operator route and API contract.
4. Add the dialog, i18n strings, request types, tracking producer, and tests.
5. Run focused pytest/Jest, type checking, lint, architecture, UoW, harness,
   and developer-tool checks.

## Validation and Acceptance

- The same `user_bid` remains after changing the phone.
- Learning, order, credit, referral, and permission rows are untouched.
- The new configured contact logs into the original account; the old contact no
  longer does.
- A contact already linked to an active account is rejected without any writes.
- The old contact can subsequently register a distinct new account.
- Phone deployments reject email replacement requests and email deployments
  reject phone replacement requests.
- Existing sessions are all revoked after success.
- Missing reason, mismatched confirmation, malformed phone, duplicate request,
  and cancelled-user targets are rejected safely.
- A mid-transaction failure rolls back every credential and user change.
- Tracking never contains either contact value, the reason, or another free-form
  field and never affects the phone change result.

## Idempotence and Recovery

Repeating the same completed request is rejected because the target already has
the new contact; it never creates duplicate credentials. Database changes are one
unit of work. Cache eviction occurs after durable token deletion; incomplete
cache eviction returns a stable failure so operators do not receive a false
clean-success message.

## Interfaces and Dependencies

- Existing `AuthCredential`, `UserInfo`, and `UserToken` models.
- Existing contact normalization, contact-mode, and user repository helpers.
- Existing operator guard and common response envelope.
- Existing Cook Web request client, dialog primitives, i18n inventory, and
  `useTracking` analytics path.

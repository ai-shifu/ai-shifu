# Operator-Initiated User Account Cancellation

This ExecPlan is a living implementation document. Keep `Progress`,
`Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective`
current as the work proceeds.

## Purpose / Big Picture

AI Shifu does not currently have an account-cancellation workflow. The first
delivery adds the domain logic and an operator-only action under Operations >
User Management. It deliberately does not expose a learner or teacher
self-service entry yet.

After this work, an operator can inspect whether an account is safe to cancel,
enter a required audit reason, explicitly confirm the target account, and
cancel it. Cancellation immediately prevents authentication and invalidates
all sessions. Direct personal profile and credential data is erased or
de-identified, while immutable financial, credit, course, learning, and audit
records retain the stable `user_bid` required for referential integrity and
legal or operational review. A cancelled account cannot silently become active
again.

This feature is an account lifecycle transition, not a recursive physical
delete. A later self-service entry can reuse the same backend preflight and
execution service with a different actor and identity-verification policy.

## Progress

- [x] 2026-09-08 12:28 CST: Created `feat/admin-user-account-cancellation`
  from the latest `main` and confirmed a clean worktree.
- [x] 2026-09-08 12:28 CST: Inventoried the user aggregate, authentication
  credentials, sessions, operator user list, course ownership, learning,
  billing, order, credit, referral, notification, TTS, and profile references.
- [x] 2026-09-08 12:28 CST: Defined the proposed cancellation boundary,
  operator workflow, blockers, audit model, and retention categories in this
  plan.
- [x] 2026-09-08 12:45 CST: Confirmed a two-PR delivery, required database
  migration, automatic renewal cancellation, new-account identifier reuse,
  non-blocking credit forfeiture, published-course batch transfer, and frozen
  preservation of draft-only courses.
- [x] 2026-09-08 13:50 CST: Kept unsettled payments as a conservative blocker
  and kept the free-form cancellation reason out of the routine list column
  while exposing it through the detail contract.
- [x] 2026-09-08 13:50 CST: Added the cancellation persistence model and
  migration.
- [x] 2026-09-08 13:50 CST: Implemented preflight, renewal preparation,
  published-course transfer, credit forfeiture, session revocation,
  de-identification, identifier release, and idempotent cancellation.
- [x] 2026-09-08 13:50 CST: Added operator routes, cancelled-user list/detail
  contracts, localized errors, and focused backend regression coverage.
- [x] 2026-09-09 10:20 CST: Hardened cancellation review boundaries: open
  credit reservations are terminally forfeited, cached sessions revalidate
  account activity, cancelled lists exclude unrelated legacy soft deletions,
  audit reasons remain detail-only, and batch course transfer is concurrency
  safe with failure-tolerant post-commit work.
- [ ] Add the User Management action, confirmation dialog, i18n, API client,
  analytics contract, and frontend tests.
- [ ] Update the canonical operator user-management specification and run the
  required focused and repository checks.

## Surprises & Discoveries

- `user_users.deleted` already excludes a user from the normal aggregate and
  identifier lookup paths, but that flag alone does not revoke cached tokens,
  disable `user_auth_credentials`, clear `api_key`, or remove personal data.
- Session validation reads Redis before falling back to `user_token`. Existing
  session revocation therefore deletes database rows first and then evicts all
  token cache entries; cancellation must preserve that ordering and must not
  report clean success while known cached credentials remain usable.
- Operation-credit holds are independently capturable or releasable after
  reservation. Account cancellation must lock the user lifecycle before wallet
  mutation, terminally consume every open hold, and make later capture/release
  calls reject the cancelled owner; zeroing available buckets alone is not
  sufficient.
- The stable account key is copied across many independent domains rather than
  enforced by one cascading foreign key. Examples include course authoring,
  learning progress and generated content, orders, subscriptions, credit
  ledgers, referral records, notifications, feedback, metering, and cloned
  voices. Re-keying or deleting those records would damage history and audit
  consistency.
- Draft and published courses store their responsible user in
  `created_user_bid`. Operator course list/detail loading is driven by the
  course records and continues to work when that user is cancelled, but the
  current user-enrichment query filters out deleted users. Without an explicit
  fallback, the course remains inspectable while its owner phone, email, and
  nickname appear blank and creator-contact search no longer finds it.
- China-facing retention rules are not equivalent to indefinite retention.
  Personal Information Protection Law Article 47 requires deletion when the
  processing purpose ends, while allowing storage-only handling with necessary
  safeguards where a statutory period has not expired or deletion is
  technically difficult. E-commerce Law Articles 24 and 31 distinguish user
  information deletion from transaction-record retention. Product counsel must
  confirm the exact applicability and periods for each deployment; the code
  must not hard-code a universal legal conclusion.

## Decision Log

- Decision: Phase 1 is operator-initiated only; no learner/teacher-facing entry
  is added. Rationale: this delivers the lifecycle primitive and controlled
  operations workflow without prematurely defining self-service identity
  verification, cooling-off, or recovery UX.
- Decision: Cancellation retains `user_bid` as a pseudonymous business key.
  Rationale: orders, credits, authored courses, learning history, and audit
  records require stable attribution and must not be rewritten destructively.
- Decision: Cancellation is terminal in Phase 1. A later login with the same
  phone, email, or federated identity creates a new account only if product and
  legal policy explicitly permit reuse; it must never reactivate the cancelled
  row. Rationale: accidental resurrection would restore retained data to a new
  login and violate the meaning of cancellation.
- Decision: Operators cannot cancel themselves or any account that currently
  has `is_operator=1`. Operator privileges must be removed through a separate,
  auditable role-management process first. Rationale: prevents privilege abuse
  and administrative lockout.
- Decision: Draft-only courses do not block cancellation and are neither
  physically nor logically deleted. They retain the cancelled owner's stable
  `created_user_bid` and become frozen orphan drafts: operators can still list,
  inspect, and later transfer them, but no cancelled account can edit, publish,
  or invoke paid/model operations through them. Published courses must be
  transferred before cancellation because learner access, progress, payment
  configuration, and support responsibility depend on a live course owner.
- Decision: The reason is required, trimmed, 5-500 characters, persisted only
  in the authoritative cancellation audit record, and never sent to Umami or
  ordinary logs. Rationale: it is free-form operational data needed for later
  review, not analytics.
- Decision: Financial, credit-ledger, and transaction records are retained and
  processing is restricted to settlement, refund, dispute, statutory
  retention, and audit needs. Direct profile and authentication data is erased
  or de-identified. Rationale: deletion and retention obligations apply to
  different data purposes.
- Decision: The workflow automatically cancels future subscription renewal
  before final account cancellation. The user does not need to do this
  separately. A provider/local cancellation failure is a temporary blocker and
  the operator can retry; a successfully scheduled end-of-period cancellation
  is sufficient to proceed.
- Decision: Unused credits are shown in the final warning, forfeited without a
  refund, and do not block cancellation. Wallet and ledger history remains for
  audit, but the cancelled account can no longer consume the balance.
- Decision: A previously cancelled phone/email may register a wholly new
  account after the old credentials are de-identified. It must not reactivate
  or regain data from the cancelled account.
- Decision: Add a `cancelled` operator-list filter while leaving the default
  list active-only. Show cancellation time/status in the list; keep the
  free-form reason in the user detail/audit view rather than a wide, routinely
  exposed list column.
- Decision: Do not require typing `user_bid`. A compact second confirmation
  dialog presents the target identity and effect summary and owns the final
  destructive action.

## Outcomes & Retrospective

PR 1 now owns the complete backend lifecycle and operator API contract. It
adds the migration and audit record, authoritative preview, batch published
course and cloned-voice transfer, automatic renewal preparation, atomic credit
forfeiture, credential/profile de-identification, verification-code cleanup,
session revocation, cancelled-user filtering, and audit detail fields. Drafts
remain frozen and recoverable, while the old login identifier is released for
a new account without reconnecting retained history.

Focused cancellation, operator-user, and creator-transfer tests pass, as do
the repository harness, translation validation, architecture boundary check,
and full pre-commit suite. The broader `tests/service/user` collection remains
blocked by the local environment's pre-existing `markdown_flow` package, which
does not export `USER_ANSWER_CONTEXT_KEY`; the focused suites do not exercise
or depend on that missing symbol. The migration graph reports
`b1c2d3e4f5a6` as its single head.

PR 2 remains intentionally separate: it will add the operator dialogs,
cancelled filter UI, analytics contract, and frontend tests. Later work may
add self-service cancellation and jurisdiction-specific retention jobs.

## Context and Orientation

The canonical product description for the current operator user list is
`docs/product-specs/operator-user-management.md`. The backend list and detail
routes are registered in
`src/api/flaskr/service/shifu/admin_operations/route.py`; their query and DTO
construction live in the adjacent `users.py` and `admin_dtos_users.py`. Backend
regression coverage is in
`src/api/tests/service/shifu/test_admin_users.py`.

The account aggregate and credential records live in
`src/api/flaskr/service/user/models.py` and
`src/api/flaskr/service/user/repository.py`. `UserInfo` (`user_users`) contains
the stable `user_bid`, direct profile fields, roles, `api_key`, and `deleted`.
`AuthCredential` (`user_auth_credentials`) contains provider identities and raw
provider profile data. `UserToken` (`user_token`) and Redis token cache entries
represent live sessions. `src/api/flaskr/service/user/sessions.py` contains the
safe database-delete-then-cache-evict ordering that cancellation must reuse or
generalize.

The frontend list is
`src/web/src/app/admin/operations/users/page.tsx`. Its row menu uses
`AdminRowActions`, and credit granting demonstrates the adjacent dialog and
post-success refresh patterns. API types are under the operations user files in
the same subtree. User-facing strings belong in the shared JSON namespace
`src/i18n/*/module.operationsUser.json`, not in React source.

Data falls into four cancellation classes:

1. **Disable immediately:** active authentication, all sessions, API key,
   notification eligibility, and any background work that can initiate new
  user-facing processing.
2. **Erase or de-identify:** canonical phone/email identity, credential
   identifiers and provider raw profiles, nickname, learner profile, avatar,
   birthday, and global profile variable values. Course-owned cloned voices
   follow the course lifecycle: voices for transferred published courses move
   to the new owner, while voices attached only to frozen drafts remain frozen
   with those drafts so a later operator transfer does not silently break the
   course.
3. **Retain pseudonymously:** learning progress/generated lesson data,
   feedback, favorites, risk and metering records, referral history, and
   notification delivery records, plus draft course structures and provenance,
   provided direct personal payloads are separately scrubbed. They retain
   `user_bid` but are no longer reachable by an authenticated account. Draft
   content may itself contain personal information, so it is frozen with
   operator-only access and remains subject to the deployment retention policy
   rather than being treated as anonymously safe forever.
4. **Retain as controlled records:** orders, provider payment records,
   subscriptions, entitlements, wallets, credit buckets and ledgers, refunds,
   disputes, and cancellation audit. Access must be purpose-limited and governed
   by the deployment's retention schedule.

Official references informing, but not replacing, product counsel review:

- [Personal Information Protection Law, Article 47](https://www.npc.gov.cn/WZWSREL25wYy9jMi9jMzA4MzQvMjAyMTA4L3QyMDIxMDgyMF8zMTMwODguaHRtbD9yZWY9aW1i)
- [E-commerce Law, Articles 24 and 31](https://www.npc.gov.cn/WZWSREL3pncmR3L25wYy9sZnp0L3JseXcvMjAxOC0wOC8zMS9jb250ZW50XzIwNjA4MjcuaHRt)
- [Internet User Account Information Management Provisions](https://www.cac.gov.cn/2022-06/26/c_1657868775042841.htm)

## Plan of Work

### Delivery and database plan

Deliver the feature in two dependent pull requests:

1. **PR 1 — account cancellation domain and operator APIs.** Add the database
   migration, cancellation audit/lifecycle models, preview, published-course
   batch transfer, automatic renewal cancellation orchestration, account
   de-identification, all-session revocation, frozen-draft enforcement, and
   backend regression coverage. This PR intentionally exposes no learner or
   teacher self-service entry. Operator-only APIs may land before the UI because
   they remain protected by the existing operator guard.
2. **PR 2 — operator User Management workflow.** Add the cancelled-user filter,
   cancellation time/detail presentation, row action, preparation and summary
   dialogs, translations, API bindings, analytics contract/producer, product
   specification update, and frontend regression coverage. This PR depends on
   PR 1's stable API contract.

Do not split a schema-only migration PR: the new schema has no standalone
product value and must ship with the backend behavior that owns it. Do not put
the frontend in PR 1: separating the destructive transaction from the dialog
makes both review surfaces smaller and lets backend invariants be reviewed and
tested before exposure.

A database migration is required. The existing `user_users.deleted` flag is
necessary for compatibility but insufficient for an auditable cancellation.
PR 1 adds `user_account_cancellations` with the operator, reason, timestamps,
idempotency, status, and privacy-safe decision snapshot, plus explicit
`cancelled_at` and `cancellation_bid` lifecycle fields on `user_users`. Course
tables do not require a new cancellation column in the first delivery: frozen
draft status is derived from `created_user_bid` resolving to a cancelled user.
This keeps transfer recovery simple and avoids writing a new state onto every
historical course revision.

### 1. Persist an immutable cancellation case

Add a `user_account_cancellations` table rather than storing the reason on
`user_users`. Each user has at most one successful cancellation case. Proposed
fields are:

- numeric primary key and unique `cancellation_bid`;
- unique `user_bid`;
- `status` enum (`pending`, `completed`, `failed`) if execution has external
  cleanup, otherwise record only committed `completed` cases and use structured
  application logs for failed attempts;
- `actor_type` (`operator` initially, extensible to `self_service`);
- `operator_user_bid`;
- required `reason`;
- `requested_at`, `completed_at`, `created_at`, and `updated_at`, all UTC;
- a schema-version integer and a JSON `retention_snapshot` containing only
  low-risk counts/booleans needed to explain the decision (for example owned
  course count, active subscription flag, and whether unused credits existed),
  never phone, email, nickname, token, raw provider data, or full payloads;
- unique idempotency key supplied by the UI or derived from the cancellation
  case.

Add explicit lifecycle fields to `user_users`: `cancelled_at` and
`cancellation_bid`. Continue setting `deleted=1` for compatibility with all
existing active-user queries. An explicit timestamp/case reference avoids
conflating cancellation with legacy soft deletion.

### 2. Add preflight as the single policy source

Add an operator-only preflight endpoint:

`GET /api/shifu/admin/operations/users/{user_bid}/cancellation-preview`

It returns the current target identity summary, blockers, warnings, draft
course count, published course summaries, and a short-lived `preview_version`
derived from cancellation-relevant state. At minimum inspect operator role,
self-targeting, account state, owned courses, active/non-renewing subscriptions,
unsettled payment states, available/reserved credits, and active sessions. Do
not return raw payment or credential secrets.

The execute endpoint recomputes all rules under database locks; the preview is
for operator understanding, not authorization. If relevant state changed, the
request fails with a bounded conflict code and the UI reloads the preview.

### 3. Execute cancellation idempotently

Add:

`POST /api/shifu/admin/operations/users/{user_bid}/cancel`

with `{ cancellation_bid, preview_version, reason }`. Require an authenticated
operator and reject self-targets/operators before any mutation.

Within one unit of work:

- lock and revalidate the active user and preflight state;
- verify that every published course has already been transferred;
- leave draft-only course and outline records intact under the cancelled
  `created_user_bid` and enforce their frozen-owner behavior;
- verify that future subscription renewal has been cancelled;
- create the immutable audit case;
- set `deleted=1`, `cancelled_at`, `cancellation_bid`, `is_creator=0`, clear
  `api_key`, and replace direct profile fields with non-identifying defaults;
- mark every credential deleted and replace unique identifiers, subject ids,
  and raw profiles with deterministic tombstones scoped to credential BID;
- delete all `user_token` rows while collecting their token values for
  post-commit cache eviction;
- soft-delete or scrub user-owned profile variable values and other direct PII
  identified by the inventory;
- disable future user-targeted notifications/background actions;
- preserve business and controlled-retention rows without copying PII into the
  cancellation record.

Cache invalidation occurs only after commit. Unlike the general best-effort
`on_commit` helper, token invalidation needs an observable recovery mechanism:
either synchronously retry and leave a durable cleanup task when eviction
fails, or use a short token-cache TTL plus a per-user cancellation generation
checked by authentication. The preferred robust design is an account/session
generation check so a cancelled user fails authentication even if an old token
cache entry survives. This avoids a committed cancellation being reported as
rolled back when the database is already durable.

Repeated requests using the same cancellation BID return the original completed
result. A different request for an already-cancelled account returns an
`already_cancelled` result without creating a second audit case.

### 4. Build the operator dialog

Add `注销` / `Cancel account` as a destructive row-menu action. Opening it
loads one preparation dialog. For a user without published courses it shows the
target summary, impact/warnings, and required reason. For a user with published
courses, the same dialog additionally shows the course count/list and an
inline `Transfer all courses` section:

- the operator enters one target phone number or email address;
- the existing transfer-target resolver finds the target or creates a new
  registered user, grants the teacher role, and preserves current onboarding
  behavior;
- a dedicated batch transfer updates every published course owned by the
  cancelling account to the same target in one transaction;
- draft-only courses are not transferred and remain available to operators as
  frozen drafts owned by a cancelled user;
- after success the dialog refreshes its preview in place and enables Continue
  rather than closing and reopening a separate workflow.

The preparation dialog shows:

- immutable target `user_bid`, current masked login identifier, nickname, and
  roles;
- blockers in a non-submittable state;
- warnings for sessions, learning access, retained transaction records,
  subscription state, and remaining credits;
- a required reason textarea with character count and validation;
- Cancel and Continue actions, with double-submit prevention.

Continue opens one compact second dialog with no additional input. It shows the
masked target identity and a fixed summary: published courses transferred (when
applicable), draft courses frozen and retained, renewal cancelled, remaining credits
forfeited without refund, sessions ended, and personal profile de-identified.
Its actions are Back and Confirm cancellation.

The action is disabled for an operator row and explains why. Backend checks
remain authoritative. On success, close the dialog, refresh list/overview/detail
caches, show a success message, and remove the row from the default active list.
On conflict, keep the reason, reload the preview, and show the changed blocker
or warning. Never display raw backend exceptions.

### 5. Add decision-relevant analytics

Authoritative audit remains in the database, not Umami. Add this product
analytics family only to understand whether the operations workflow is usable:

#### `operator_user_cancellation_v1`

- Business question: Of cancellation dialogs opened by eligible operators,
  how often are valid attempts completed, blocked by policy, explicitly
  abandoned, or failed technically?
- Metric definition: count distinct cancellation workflow IDs by terminal
  outcome over a selected time window; compare with distinct dialog-open
  workflow IDs. This is operational UX telemetry, not the audit source.
- Event names: `operator_user_cancellation_opened`,
  `operator_user_cancellation_attempted`, and
  `operator_user_cancellation_result`.
- Actor and surface: authenticated operator on `operations_user_list`.
- Trigger: opened after preview resolves; attempted after local validation and
  before the request; result once per accepted attempt on success, policy
  conflict, technical failure, or explicit dialog cancellation.
- Population: operator sessions only; exclude denied/non-operator renders.
- Count unit and deduplication: one generated workflow ID per dialog lifecycle,
  at most one attempt in flight and one terminal result per attempt.
- Correlation: pseudonymous workflow ID only; shared analytics identity already
  identifies the actor. Do not send target user BID.
- Consumers: Operations product review and failure monitoring queries.
- Compatibility: new v1 event family.
- Verification: exact triggers, result deduplication, failure isolation, and
  and negative assertions for reason, target identity, login identifier,
  nickname, URLs, raw errors, and preview payload.

Allowed payload fields are `surface=operations_user_list`, `workflow_id`,
`result` (`success`, `blocked`, `conflict`, `failed`, `cancelled`),
`blocker_category` (`none`, `operator`, `self`, `course_owner`,
`active_subscription`, `unsettled_payment`, `already_cancelled`, `other`), and
bounded numeric `warning_count`. `reason` and all target data are prohibited.

## Concrete Steps

1. Confirm the remaining unsettled-payment and list-detail presentation policy
   in the Decision Log.
2. Add the model and Alembic migration under `src/api/migrations/versions/`.
3. Add a cancellation domain module under `src/api/flaskr/service/user/` and a
   safe all-session revocation primitive shared with `sessions.py`.
4. Add DTOs and routes to `admin_operations`, keeping operator authorization at
   the route and policy enforcement in the domain service.
5. Add backend tests for every blocker, warning, mutation, idempotent retry,
   rollback, stale preview, session invalidation, credential reuse behavior,
   and absence of PII in retained/audit payloads.
6. Add frontend API types/wrappers, `UserAccountCancellationDialog`, the row
   action, shared translations, analytics producer/contract, and focused tests.
7. Update `docs/product-specs/operator-user-management.md` with the final
   workflow and data lifecycle matrix.
8. Run focused checks, migration upgrade/downgrade in an isolated database,
   architecture checks, developer-tool verification, and relevant frontend and
   backend suites before commit.

## Validation and Acceptance

- A non-operator cannot call preview or execute, including by constructing the
  request manually.
- An operator cannot cancel self or any current operator.
- A published-course owner cannot be cancelled until the in-dialog batch
  transfer succeeds; draft-only courses remain operator-visible and frozen.
- A valid cancellation requires a reason and a separate summary confirmation.
- Immediately after success, all old tokens fail in both database-fallback and
  warm-Redis-cache paths, and the API key no longer works.
- Phone/email/password/Google/WeChat login cannot load or reactivate the old
  aggregate.
- Direct profile and credential PII is no longer present in active tables,
  provider raw profile fields, profile variable values, retained audit JSON,
  analytics, or normal logs.
- Orders, payment records, subscriptions, wallets, ledgers, learning history,
  and other retained rows remain referentially intact through `user_bid`.
- Repeating the same request is idempotent; racing two requests yields one
  completed audit case.
- The default operator user list no longer shows the account; the approved
  cancelled-account query can find its non-sensitive cancellation status and
  audit metadata.
- The dialog exposes all relevant blockers/warnings, prevents accidental target
  selection and double submit, preserves entered reason across a state conflict,
  and surfaces localized bounded errors.
- Analytics failure cannot block cancellation, and analytics never contains
  the reason or target-user data.

Minimum focused checks:

    cd src/api
    pytest tests/service/shifu/test_admin_users.py -q
    pytest tests/service/user -q

    cd src/web
    npm test -- --runInBand src/app/admin/operations/users/page.test.tsx
    npm run type-check

    cd /Users/iris/ai-shifu
    python scripts/check_dev_tools.py
    python scripts/check_architecture_boundaries.py
    python scripts/check_repo_harness.py

Use the repository's actual frontend focused-test command if its runner syntax
differs; record the final commands and results here rather than blindly copying
this draft.

## Idempotence and Recovery

The execute request carries a unique cancellation BID and is safe to retry.
Database mutations occur in one outer `unit_of_work`; a validation or database
failure rolls back the user transition and audit case together. The service
locks the target user so two operators cannot both complete cancellation.

External/provider subscription cancellation is a preparatory, idempotent step
before the account transaction. It schedules cancellation at period end where
the provider supports renewal, then refreshes the preview. A provider failure
leaves the account active and presents a retryable error; it never produces a
half-cancelled account. Local/manual plans cancel pending renewal work without
pretending an external provider call occurred. Object-storage cleanup and cache
invalidation must be represented by durable, idempotent cleanup work. A retry
checks the current tombstone/audit state before deleting anything and never
restores PII.

Migration downgrade removes only the new schema when no cancellation data must
be preserved. In deployed environments, rollback of application code must
remain compatible with `deleted=1`; it must not reactivate cancelled users even
if the older application ignores the new audit table.

## Interfaces and Dependencies

Proposed API interfaces:

    GET /api/shifu/admin/operations/users/{user_bid}/cancellation-preview

    POST /api/shifu/admin/operations/users/{user_bid}/transfer-published-courses
    {
      "contact_type": "phone",
      "identifier": "<target phone>"
    }

    POST /api/shifu/admin/operations/users/{user_bid}/cancel
    {
      "cancellation_bid": "<uuid>",
      "preview_version": "<opaque version>",
      "reason": "<5-500 character operator reason>"
    }

Preview DTO:

    {
      "user": {
        "user_bid": "...",
        "masked_identifier": "...",
        "nickname": "...",
        "roles": ["creator"]
      },
      "draft_course_count": 3,
      "published_courses": [{"shifu_bid": "...", "title": "..."}],
      "can_cancel": true,
      "blockers": [],
      "warnings": [{"code": "remaining_credits"}],
      "preview_version": "..."
    }

Execution result:

    {
      "cancellation_bid": "...",
      "user_bid": "...",
      "status": "completed",
      "cancelled_at": "2026-09-08T04:28:00Z"
    }

New bounded server/i18n error keys cover target not found, already cancelled,
self/operator protection, published-course transfer required, subscription
cancellation failure, unsettled payment, stale preview, invalid reason, and
incomplete session invalidation. UI copy lives under `module.operationsUser`
in every supported locale.

The implementation depends on the existing user aggregate, unit-of-work,
operator authorization, session token/cache, billing subscription/order/credit,
course ownership, profile variable, notification, and frontend request/SWR
modules. The batch transfer reuses the existing target lookup/auto-registration
semantics from `courses_transfer_copy.py`, but exposes them through an
appropriate shared service boundary instead of calling a one-course HTTP route
repeatedly. It must not introduce direct SQL in the route or duplicate
authentication logic in `admin_operations`.

# Referral Invitation Rewards Implementation Plan

## Purpose / Big Picture

Build the first version of AI-Shifu's existing-user-invites-new-user reward
flow. Existing domestic users get an invite code and link; new phone-registered
users can bind to one inviter at registration; the inviter receives one month
of the configured 199 CNY plan for each valid invite, capped at 12 months.

## Progress

- [x] 2026-06-08 22:30 CST: Read the Feishu wiki proposal, inspected the
  current user auth, post-auth, billing, manual plan grant, and operator
  referral reward paths.
- [x] 2026-06-08 22:45 CST: Captured the product and technical design in
  `docs/design-docs/referral-invitation-rewards.md`.
- [ ] 2026-06-08 22:45 CST: Implement backend referral domain models,
  migrations, services, routes, and tests.
- [ ] 2026-06-08 22:45 CST: Implement creator invite and invitee landing
  frontend surfaces.
- [ ] 2026-06-08 22:45 CST: Implement operator referral monitoring and abnormal
  handling surfaces.
- [ ] 2026-06-08 22:45 CST: Validate in dev02 with real configured billing
  product and database rows.

## Surprises & Discoveries

- `src/api/flaskr/service/billing/referral_reward_grants.py` already exists,
  but it is an operator manual credit pool. It does not model invite codes,
  invitee binding, automatic rewards, or the 12-month cap.
- `src/api/flaskr/service/billing/manual_plan_grants.py` already has the
  useful `manual + paid` billing order pattern, but it currently implements
  operator package grants with immediate activation/upgrade semantics. Referral
  rewards need same-plan extension and deferred activation after higher/yearly
  paid plans.
- `src/api/flaskr/service/user/post_auth.py` is the right registration-side
  extension point. It is already used by billing trial bootstrap and is
  best-effort so login success is not coupled to side-effect delivery.
- The test fixture product `creator-plan-monthly-pro` represents the 199 CNY
  monthly plan, but implementation must verify the live catalog credit amount
  before feature enablement because the Feishu proposal states 1000 credits per
  30-day reward cycle.

## Decision Log

- Add a new `src/api/flaskr/service/referral/` domain for invite codes,
  relation binding, click tracking, reward audit rows, repair scripts, and
  operator read models.
- Keep billing as the package/credit truth by creating billing orders,
  subscriptions, wallet buckets, and ledger entries for each granted reward.
- Do not reuse the existing operator `referral_reward_grants.py` helper for
  automatic invitation rewards; keep that helper as the current manual credit
  tool. A separate cleanup can rename or merge these surfaces only after the
  automatic invitation reward flow is live.
- Extend `PostAuthContext` with optional referral metadata instead of placing
  invite binding directly inside route handlers.
- Treat post-auth reward generation as best-effort and idempotent; missing
  reward side effects are repairable from `referral_invite_relations` and
  `referral_invite_rewards`.
- Store hashed click IP and user-agent values for funnel analysis. Do not store
  raw click IP/user-agent in referral event rows.

## Outcomes & Retrospective

This section is updated after implementation. Expected outcome: a feature-flagged
referral reward system that can be enabled in dev02, verified through DB rows
and operator screens, and then rolled forward without changing existing paid
billing semantics.

## Context and Orientation

Start from these files:

- Design source: `docs/design-docs/referral-invitation-rewards.md`.
- Billing design: `docs/billing-subscription-design.md`.
- User auth rules: `src/api/AGENTS.md`,
  `src/api/flaskr/service/user/AGENTS.md`, and
  `src/api/skills/user-auth-flows/SKILL.md`.
- Billing rules: `src/api/flaskr/service/billing/AGENTS.md`.
- Frontend rules: `src/cook-web/AGENTS.md`, `src/cook-web/src/app/AGENTS.md`,
  and nearest `AGENTS.md` files in touched directories.

Existing code to reuse:

- `src/api/flaskr/route/user.py`: SMS login payload and post-auth context.
- `src/api/flaskr/service/user/post_auth.py`: post-auth extension contract.
- `src/api/flaskr/service/billing/subscriptions.py`: paid order activation and
  `grant_paid_order_credits`.
- `src/api/flaskr/service/billing/manual_plan_grants.py`: manual paid-order
  orchestration pattern.
- `src/api/flaskr/common/public_urls.py`: public origin URL construction.
- `src/api/flaskr/service/shifu/admin_operations/route.py`: operator route
  namespace pattern.
- `src/cook-web/src/lib/request.ts` and `src/cook-web/src/lib/api.ts`: frontend
  request stack.
- `src/i18n/*/modules/operations-user.json` and billing i18n modules for
  existing operations copy style.

Do not edit existing applied Alembic migrations. Generate a new migration for
referral tables.

## Plan of Work

1. Add referral backend domain scaffolding and database schema.
2. Add invite profile, invite click, and relation binding helpers.
3. Extend SMS login post-auth context and add the referral post-auth handler.
4. Add billing referral plan reward helper with extension/deferred semantics.
5. Add creator-facing referral APIs.
6. Add operator referral APIs and read models.
7. Add focused backend tests for relation binding, cap handling, billing
   artifacts, and operator status changes.
8. Add creator invite and invitee landing frontend flows.
9. Add operator referral monitoring UI.
10. Regenerate i18n/type surfaces and run validation.
11. Verify in dev02 behind a feature flag.

## Concrete Steps

### Step 1: Create Backend Referral Domain

Files:

- Create `src/api/flaskr/service/referral/AGENTS.md`.
- Create `src/api/flaskr/service/referral/__init__.py`.
- Create `src/api/flaskr/service/referral/consts.py`.
- Create `src/api/flaskr/service/referral/models.py`.
- Create `src/api/flaskr/service/referral/dtos.py`.
- Create `src/api/flaskr/service/referral/service.py`.
- Create `src/api/flaskr/service/referral/routes.py`.
- Create `src/api/tests/service/referral/`.

Implementation requirements:

- Define status/type constants in a referral-local range, not in billing
  constants.
- Add models for:
  - `ReferralInviteCode`
  - `ReferralInviteClick`
  - `ReferralInviteRelation`
  - `ReferralInviteReward`
- Use `String(36)` business IDs, soft delete, `SmallInteger` status fields, and
  JSON metadata following existing model conventions.
- Add unique constraints for invite code and active invitee binding.

Validation:

- Generate a new Alembic migration from `src/api`.
- Review the migration manually for table names, indexes, and comments.
- Add model tests that insert minimal rows and enforce unique invitee binding.

### Step 2: Build Invite Code And Profile Helpers

Files:

- Modify `src/api/flaskr/service/referral/service.py`.
- Modify `src/api/flaskr/service/referral/dtos.py`.
- Add `src/api/tests/service/referral/test_invite_profile.py`.

Implementation requirements:

- Generate immutable random invite codes with collision retry.
- Lazily create the inviter profile on `GET /api/referral/invite-profile`.
- Build invite links through a public-origin helper, not hardcoded hostnames.
- Return rewarded count, remaining count, cap, and reward queue summary.
- Keep invitee mobile/user details out of inviter-facing responses.

Validation:

- Invite code is stable across repeated profile loads.
- Invite link uses configured/request public origin.
- Disabled invite codes are not returned as usable.

### Step 3: Record Invite Clicks

Files:

- Modify `src/api/flaskr/service/referral/service.py`.
- Modify `src/api/flaskr/service/referral/routes.py`.
- Add `src/api/tests/service/referral/test_invite_clicks.py`.

Implementation requirements:

- Add `POST /api/referral/invite-click`.
- Accept invite code, landing path, and frontend session id.
- Hash IP and user-agent before persistence.
- Return only a success status and a generated referral session id when needed.
- Do not reveal inviter account data on anonymous calls.

Validation:

- Valid invite code records one click event.
- Invalid invite code returns a generic non-identifying error or no-op response,
  matching product choice in the design.
- Raw IP and raw user-agent are not persisted.

### Step 4: Extend PostAuthContext And SMS Login Payload

Files:

- Modify `src/api/flaskr/service/user/post_auth.py`.
- Modify `src/api/flaskr/route/user.py`.
- Add/update tests under `src/api/tests/service/user/`.

Implementation requirements:

- Add optional `invite_code`, `referral_session_id`, `client_ip_hash`, and
  `user_agent_hash` fields to `PostAuthContext`.
- In SMS login, read `invite_code` and `referral_session_id` from the payload.
- Pass referral fields only to post-auth context. Do not bind referral state in
  the route.
- Preserve existing temp-user and verification-code behavior.

Validation:

- Existing SMS login tests still pass.
- New test confirms SMS login passes referral metadata to post-auth handlers.
- Existing user login with invite code does not imply a new registration.

### Step 5: Add Referral Post-Auth Handler

Files:

- Create `src/api/flaskr/service/referral/auth_hooks.py`.
- Ensure the module is imported by the plugin/registration path used by service
  extensions.
- Add `src/api/tests/service/referral/test_post_auth_binding.py`.

Implementation requirements:

- Register an extension for `run_post_auth_extensions`.
- Act only when `created_new_user = true` and invite code is present.
- Reject self-invites.
- Create one active relation per invitee.
- Count rewardable prior invite rewards.
- Create a reward row for reward months 1 through 12.
- Mark 13th and subsequent valid invitees as cap-skipped without billing side
  effects.
- Never fail login because of referral processing errors; log enough BIDs for
  repair.

Validation:

- New invited user creates relation and reward.
- Existing user login does not create relation.
- Duplicate post-auth retry returns the existing relation/reward.
- 13th invite creates relation with skipped reward state.

### Step 6: Add Billing Referral Plan Reward Helper

Files:

- Create `src/api/flaskr/service/billing/referral_plan_rewards.py`.
- Modify `src/api/flaskr/service/billing/api.py` to export the helper.
- Add `src/api/tests/service/billing/test_referral_plan_rewards.py`.

Implementation requirements:

- Load reward product by configured product code.
- Verify the product is an active plan and has the intended 199 CNY monthly
  campaign shape before granting.
- Create idempotent `manual + paid` billing orders with provider reference
  `referral-reward:{reward_bid}`.
- Use metadata `checkout_type = referral_invitation_reward`.
- Reuse `grant_paid_order_credits`.
- Support immediate activation when no active paid subscription exists.
- Support same-plan extension when active self-managed subscription uses the
  reward product.
- Support deferred activation after higher/yearly paid plan end.
- Return subscription, order, wallet bucket, and ledger BIDs to the referral
  service.

Validation:

- New user with no subscription gets active reward immediately.
- Same reward call is idempotent.
- Existing same-plan subscription extends by one cycle.
- Existing higher/yearly plan leaves paid plan current and records deferred
  reward.
- Ledger/order metadata contains relation and reward BIDs.

### Step 7: Wire Reward Artifacts Back To Referral Rows

Files:

- Modify `src/api/flaskr/service/referral/service.py`.
- Add tests in `src/api/tests/service/referral/test_reward_generation.py`.

Implementation requirements:

- After billing grant, update `referral_invite_rewards` with billing artifact
  BIDs and effective windows.
- If billing grant fails after relation creation, leave reward in a repairable
  pending/failed state with error metadata.
- Add a repair helper that scans pending reward rows and retries billing grant.

Validation:

- Successful reward row links to billing artifacts.
- Failed billing call leaves relation intact and retryable.
- Repair helper grants a previously pending reward without duplicating relation
  or order rows.

### Step 8: Add Creator Referral APIs

Files:

- Modify `src/api/flaskr/service/referral/routes.py`.
- Ensure route registration under `/api/referral`.
- Add route tests in `src/api/tests/service/referral/test_referral_routes.py`.

Implementation requirements:

- `GET /api/referral/invite-profile` requires authenticated user.
- `POST /api/referral/invite-click` supports anonymous use.
- Responses use the shared response envelope.
- Add feature flag checks so the feature can be disabled by default.

Validation:

- Authenticated profile returns invite code and link.
- Unauthenticated profile is denied.
- Click endpoint does not require auth.
- Feature disabled state returns the configured disabled error/no-op.

### Step 9: Add Operator Referral APIs

Files:

- Modify `src/api/flaskr/service/shifu/admin_operations/route.py` or add a
  focused referral route module under that namespace if the file grows too much.
- Add referral read model helpers under `src/api/flaskr/service/referral/`.
- Add DTOs under `src/api/flaskr/service/referral/dtos.py` or
  `src/api/flaskr/service/shifu/admin_dtos.py`, following existing patterns.
- Add tests under `src/api/tests/service/referral/` and
  route permission tests under `src/api/tests/service/shifu/`.

Implementation requirements:

- Add overview metrics route.
- Add relation list route with inviter keyword, invitee keyword, reward status,
  abnormal status, and created time filters.
- Add relation detail route with billing artifacts.
- Add status update route for abnormal reviewing, cancel, freeze, and note.
- Keep operator permission guard as the real access control.

Validation:

- Non-operator users are denied.
- Operators can list, filter, inspect detail, and update abnormal status.
- Status updates do not delete billing truth.

### Step 10: Add Frontend API And Types

Files:

- Modify `src/cook-web/src/api/api.ts`.
- Create or modify referral API wrappers under the existing frontend API layer.
- Add `src/cook-web/src/types/referral.ts` if a separate type file is cleaner.
- Update i18n JSON under `src/i18n/zh-CN`, `src/i18n/en-US`,
  and `src/i18n/fr-FR`.

Implementation requirements:

- Keep calls on the shared request stack.
- Add creator invite profile and invite-click endpoints.
- Add operator referral endpoints.
- Keep all user-facing copy in i18n JSON.

Validation:

- API endpoint string tests include new routes.
- TypeScript type-check passes.

### Step 11: Add Creator Invite Page

Files:

- Add a route under the creator/admin area in `src/cook-web/src/app/admin/`.
- Add components near the route or under `src/cook-web/src/components/` if they
  are shared.
- Update navigation only in the existing creator/admin navigation path.
- Add frontend tests for rendering and copy action.

Implementation requirements:

- Show invite link, invite code, copy action, reward count, remaining reward
  count, queue summary, and cap state.
- Do not show invitee private data.
- Use restrained admin styling consistent with billing/operations pages.

Validation:

- Page renders loading, success, empty, disabled, and cap states.
- Copy action uses the generated link.
- All copy resolves through i18n.

### Step 12: Add Invitee Landing Flow

Files:

- Add invite route under `src/cook-web/src/app/`.
- Modify existing login/SMS call site to include stored invite code and
  referral session id.
- Add tests for payload propagation.

Implementation requirements:

- Read invite code from route/query.
- Record click event once per referral session.
- Preserve invite code through SMS login.
- Do not display extra invitee reward promises.

Validation:

- Landing route stores invite context.
- SMS login payload includes invite code.
- Clearing the flow removes stale invite context after successful login.

### Step 13: Add Operator Referral UI

Files:

- Add page under `src/cook-web/src/app/admin/operations/referrals/`.
- Add route/nav entries in operations menu.
- Add tests near the new page.

Implementation requirements:

- Show overview metrics, filters, table, pagination, detail sheet, and abnormal
  status actions.
- Link relation rows to existing user detail and billing artifacts where routes
  already exist.
- Keep the table dense and consistent with existing operations pages.

Validation:

- Operator guard works.
- Filters call the expected API params.
- Detail sheet shows relation, invitee, and billing artifact fields.
- Status action confirmation sends the expected payload.

### Step 14: Add Repair/Diagnostics Script

Files:

- Add backend script or CLI command under `src/api/flaskr/service/referral/` or
  `src/api/flaskr/service/billing/cli.py` if that is the established CLI route.
- Add tests for dry-run payloads where feasible.

Implementation requirements:

- Scan pending/failed reward rows.
- Retry billing grant idempotently.
- Print relation, reward, order, ledger, and error fields.
- Support dry-run mode.

Validation:

- Dry run reports pending rewards without writes.
- Retry repairs one pending reward and does not duplicate billing rows.

## Validation and Acceptance

Backend acceptance:

- A new SMS-registered invitee creates one relation and one reward for the
  inviter.
- The first 12 valid invitees produce 12 reward months.
- The 13th valid invitee registers and binds, but creates no automatic billing
  reward.
- Reward billing artifacts are visible in `bill_orders`, `bill_subscriptions`,
  `credit_wallet_buckets`, and `credit_ledger_entries`.
- Existing users are not rebound by invite links.
- Invitee accounts receive no extra referral-specific benefit.
- Operator APIs can trace inviter, invitee, relation, reward, order,
  subscription, bucket, and ledger.

Frontend acceptance:

- Creator invite page shows code, link, copy action, reward counts, queue, and
  cap messaging.
- Invite landing sends invite context through SMS login.
- Operator referral page supports list, filters, detail, and abnormal actions.
- User-facing strings live in shared i18n JSON.

Commands:

- `python scripts/build_repo_knowledge_index.py`
- `python scripts/check_repo_harness.py`
- `cd src/api && pytest tests/service/referral/ tests/service/user/ tests/service/billing/ -q`
- `cd src/cook-web && npm run type-check`
- `cd src/cook-web && npm run lint`

Dev02 validation:

- Enable the referral feature flag only after the reward product code is
  configured and verified.
- Run a synthetic invited phone registration.
- Query dev02 DB rows for relation, reward, billing order, subscription, wallet
  bucket, and ledger.
- Confirm the creator invite page and operator referral page show the same
  reward state.

## Idempotence and Recovery

- Invite code generation is unique and immutable. Repeated profile calls return
  the same code.
- Relation binding uses a unique invitee key. Repeated post-auth calls return
  the existing relation.
- Reward generation uses one reward row per relation.
- Billing grant uses provider reference `referral-reward:{reward_bid}` and
  ledger idempotency `grant:{bill_order_bid}`.
- Failed billing side effects leave pending/failed reward rows for repair.
- Repair commands are idempotent and print all relevant business IDs.
- Abnormal status updates preserve rows and record operator notes.

## Interfaces and Dependencies

Backend:

- New referral tables and Alembic migration.
- New `/api/referral` creator/anonymous endpoints.
- New `/api/shifu/admin/operations/referrals` operator endpoints.
- Extended `PostAuthContext` optional fields.
- New billing helper for referral plan rewards.
- Feature flag and reward product code configuration in
  `src/api/flaskr/common/config.py`.

Frontend:

- Creator invite page.
- Invitee landing route.
- Login payload propagation.
- Operator referral page.
- Shared i18n additions.

Operational:

- Configured reward product must represent the intended 199 CNY monthly reward.
- dev02 rollout should verify live DB state, not only tests.
- Existing operator manual `referral_reward` grant remains available and should
  not be silently repurposed.

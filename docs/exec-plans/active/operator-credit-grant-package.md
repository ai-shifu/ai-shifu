# ExecPlan: Operator Credit Grant Package

## Purpose / Big Picture

Add an operator-facing `grantDialog.title` / `page.actions.grantCredits` entry in user management so operators can
either keep granting manual credits or switch to granting an active billing
plan package. The package grant must become effective immediately, compute the
valid-until time from the selected plan, and keep the grant path isolated from
future SMS template work so notification follow-up cannot block the grant
transaction.

## Progress

- [x] 2026-05-14 17:25 CST: Confirmed product direction with the user, including immediate activation, helper-text expiry preview, and a notification extension point without wired templates.
- [x] 2026-05-14 20:10 CST: Added backend operator package bootstrap and grant endpoints plus a billing-side manual paid-order orchestration helper.
- [x] 2026-05-14 20:10 CST: Updated the user-management dialog to switch between credit grants and package grants, including role-based entry disablement.
- [x] 2026-05-14 20:10 CST: Added focused backend/frontend tests and ran the smallest relevant verification commands.

## Surprises & Discoveries

- The billing domain already supports manual paid orders without a real payment
  provider. Trial bootstrap and CLI plan grant both create `payment_provider =
  "manual"` plus `status = PAID` orders before granting credits.
- `billing/paid_side_effects.py` already separates "paid-order aftermath" from
  webhook/provider state updates, so package grants do not need webhook
  plumbing.
- Existing paid-order side effects also stage purchase SMS notifications, so
  this feature must avoid calling template-bound notification staging until a
  dedicated admin-grant template path exists.

## Decision Log

- Use the shared i18n label `grantDialog.title` / `page.actions.grantCredits`
  for both the list action and dialog title.
- Keep the existing credit-grant API contract untouched; add a separate package
  bootstrap route and a separate package-grant route.
- Reuse billing order/subscription/credit activation logic by creating a
  `manual + paid` billing order, but do not reuse the CLI wrapper directly.
- Record a notification extension marker in billing order metadata instead of
  dispatching any SMS template in this iteration.

## Outcomes & Retrospective

- Package grants now reuse billing subscription/order/credit activation without
  requiring webhook/provider flows.
- Notification metadata is recorded for future admin package template work, but
  no template dispatch is attempted in this iteration.
- The operator user-management entry now enforces the creator/operator target
  rule on both the frontend and backend.

## Context and Orientation

- Frontend entry and dialog:
  - `src/cook-web/src/app/admin/operations/users/page.tsx`
  - `src/cook-web/src/app/admin/operations/users/UserCreditGrantDialog.tsx`
  - `src/cook-web/src/app/admin/operations/operation-user-types.ts`
- Frontend i18n:
  - `src/i18n/zh-CN/modules/operations-user.json`
  - `src/i18n/en-US/modules/operations-user.json`
  - `src/i18n/fr-FR/modules/operations-user.json`
- Existing operator credit grant backend:
  - `src/api/flaskr/service/shifu/admin.py`
  - `src/api/flaskr/service/shifu/admin_dtos.py`
  - `src/api/flaskr/service/shifu/route.py`
- Billing primitives to reuse:
  - `src/api/flaskr/service/billing/read_models.py`
  - `src/api/flaskr/service/billing/queries.py`
  - `src/api/flaskr/service/billing/subscriptions.py`
  - `src/api/flaskr/service/billing/models.py`
  - `src/api/flaskr/service/billing/paid_side_effects.py`

## Plan of Work

1. Add backend DTOs and routes for package bootstrap and package grant.
2. Add a billing-side service that creates/updates a manual subscription and a
   manual paid order, then reuses billing activation/grant logic without
   dispatching template-based SMS.
3. Update the operator dialog to switch between credit and package modes and
   fetch package bootstrap data on demand.
4. Disable the entry for unsupported target roles and keep backend role checks
   as the real guard.
5. Add focused pytest/Jest coverage for the new API and UI states.

## Concrete Steps

1. Create `src/api/flaskr/service/billing/manual_plan_grants.py` with:
   - active-plan product loading
   - request-id idempotency lookup on manual paid orders
   - manual subscription create/update
   - manual paid billing order creation
   - credit grant + subscription activation
   - notification metadata placeholder
2. Extend `shifu/admin_dtos.py` with package bootstrap and package grant DTOs.
3. Extend `shifu/admin.py` with:
   - role eligibility helper
   - package bootstrap builder
   - package grant wrapper that returns refreshed operator credit summary
4. Register new routes in `shifu/route.py`.
5. Extend frontend API/type surfaces and refactor the dialog for the new
   grant-mode switch.
6. Update tests and run focused checks.

## Validation and Acceptance

- In user management, creator/operator rows show an enabled
  `grantDialog.title` / `page.actions.grantCredits` action; other roles show
  the same action disabled.
- The dialog opens in credit mode by default and still submits the existing
  credit-grant payload unchanged.
- Switching to package mode loads active billing plans, shows plan details,
  helper-text expiry guidance, and submits the package-grant API.
- A successful package grant creates a manual paid billing order, activates the
  plan immediately, grants credits, and returns refreshed summary data.
- Notification-related metadata exists for future follow-up, but no missing SMS
  template blocks the package grant path.

## Idempotence and Recovery

- Package grants use the request id to find a previously created manual paid
  order and return the persisted result instead of creating duplicate grants.
- The frontend keeps the existing generated request id behavior so retries from
  the same open dialog remain safe.
- Notification extension metadata is best-effort and must not roll back a
  successful grant.

## Interfaces and Dependencies

- New operator routes under `/api/shifu/admin/operations/users/...`.
- Billing plan projections reuse `BillingPlanDTO`.
- Frontend plan display reuses `src/cook-web/src/lib/billing.ts` interval and
  validity helpers.

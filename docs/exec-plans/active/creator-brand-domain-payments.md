# Creator Brand Domain And Payments

## Purpose / Big Picture

Let entitled course owners apply account-level branding, a verified custom
domain, an independent WeChat OAuth app, and independent learner payment
merchant credentials while preserving existing global behavior.

## Progress

- [x] 2026-07-12 16:06 CST: Captured the approved architecture and acceptance
      decisions in the canonical design document.
- [x] 2026-07-12 16:20 CST: Extended the SaaS unified configuration table service
      with encryption/version helpers, entitlements, and customization APIs.
- [x] 2026-07-12 16:45 CST: Connected runtime auth, TLS-gated domains, order
      snapshots, provider credentials, and version-addressed callbacks.
- [x] 2026-07-12 16:32 CST: Added the course-owner brand and payments UI.
- [x] 2026-07-12 16:52 CST: Completed focused backend and frontend validation;
      recorded unrelated dirty-worktree failures from the repository-wide gates.
- [x] 2026-07-13 20:15 CST: Added operator-facing manual entitlement editing
      for all four customization capabilities and a validated managed-OSS logo
      upload endpoint; focused backend and frontend tests passed.
- [x] 2026-07-16 17:35 CST: Recorded the reporting boundary between
      platform-domain independent-payment orders and custom-domain orders, and
      scoped the next implementation pass to platform-domain orders that use
      teacher-owned payment credentials.

## Surprises & Discoveries

- The repository already has `BillingEntitlement`, `BillingDomainBinding`,
  runtime logo overrides, domain verification helpers, and shared payment
  provider adapters. The implementation should extend these paths rather than
  add a tenant subsystem.
- Existing WeChat credentials are globally keyed by OpenID, so custom apps must
  scope identifiers by App ID while preserving the platform-app legacy shape.
- The installed SaaS plugin already owns `saas_user_configs(user_bid, key,
  value, is_encrypted)`. Dedicated brand/integration tables would duplicate
  that storage, so the implementation uses namespaced unified config rows.
- The pre-existing generic course upload used the courses OSS profile while
  branding URL validation accepted only the default OSS host and required a
  filename extension. A dedicated logo upload now preserves the extension and
  accepts both configured managed-storage hosts.

## Decision Log

- Decision: configuration is account-level by `creator_bid`, not course-level.
- Decision: learner purchase funds go directly to the owner's merchant account.
- Decision: paid product entitlements and manual grants can both unlock access.
- Decision: expiry blocks new custom payments but not historic callbacks.
- Decision: custom domains strictly isolate courses by owner.
- Decision: the two logo roles are wide and square.
- Decision: platform-domain orders paid through teacher-owned credentials remain
  AI-Shifu platform orders for teacher and operator order management, but their
  settlement owner is the teacher rather than the platform.
- Decision: custom-domain order dashboards should filter by the matched
  `domain_binding_bid` plus owner `creator_bid`; they are not simply "all orders
  for this teacher". The custom-domain attribution implementation is a separate
  follow-up from independent-payment reporting.

## Outcomes & Retrospective

The feature reuses `saas_user_configs` instead of adding customization tables.
Branding is a mutable JSON row; each integration is an encrypted immutable
version plus an active pointer. Orders snapshot that version and payment create,
webhook, sync, and refund paths reopen the same credentials. The focused backend
suite passed 100 tests with one skip, and the customization UI Jest/ESLint checks
passed. Repository-wide TypeScript and architecture checks remain red only for
pre-existing markdown-flow type drift and unrelated untracked service refactors.
The follow-up operator and logo-upload slice passed 25 backend tests and 15
frontend tests; the full TypeScript check remains blocked by the same unrelated
markdown-flow locale type drift.

## Context and Orientation

Backend ownership is split between `service/billing` for entitlements and
configuration, `service/order` for learner orders and payment providers,
`service/user` for WeChat identity, and `route/config.py` for runtime config.
The creator UI lives under `src/cook-web/src/app/admin/billing` and uses shared
billing request/types modules.

## Plan of Work

1. Add namespaced brand and versioned integration helpers on the unified SaaS
   user configuration table plus encryption support.
2. Expose entitlement-gated customization APIs and runtime summaries.
3. Snapshot learner orders and pass credential contexts through providers and
   webhook verification.
4. Scope WeChat OAuth exchange and credentials to the resolved owner app.
5. Add the admin UI, translations, and focused regression coverage.
6. Extend order management reporting for platform-domain orders that use
   teacher-owned payment integrations.

## Concrete Steps

1. Extend unified configuration helpers and add one Alembic migration without
   editing applied revisions.
2. Add a customization service and creator routes that never serialize secrets.
3. Extend runtime config with capability and readiness fields.
4. Add optional provider credential context with global fallback.
5. Wire course-owner resolution into learner checkout and OAuth.
6. Add focused pytest/Jest coverage, then run type, lint, harness, and boundary checks.
7. For the next order-management pass, add settlement-owner DTO fields and
   filters to learner order list/detail APIs and operator order overview, using
   `payment_integration_bid` as the first reliable indicator of teacher-owned
   payment credentials.

## Validation and Acceptance

- Entitlements gate every write and every new custom checkout.
- Runtime branding and public payment settings resolve by server-owned course data.
- Custom host/course ownership mismatches are rejected.
- Secrets never appear in responses or logs.
- New orders snapshot the integration version; historic callbacks survive rotation.
- All four providers accept scoped credentials and retain global fallback.
- Existing orders and non-entitled owners behave as before.
- Platform-domain orders paid through teacher-owned credentials appear in both
  teacher order menus and operator order management, while platform collection
  metrics exclude their paid amount.

## Idempotence and Recovery

Migrations add nullable/defaulted compatibility columns. Integration updates
append versions, so a failed verification cannot replace the last active row.
Disabling an integration changes only new-payment selection. The global kill
switch leaves public callback routes active.

## Interfaces and Dependencies

The implementation reuses SQLAlchemy, Alembic, cryptography/Fernet, existing
storage, billing entitlement/domain helpers, and payment provider adapters. It
adds `CREATOR_CUSTOMIZATION_ENABLED` and
`CREATOR_INTEGRATION_ENCRYPTION_KEY` to backend configuration.

# Credit Notification Email Delivery

## Purpose / Big Picture

Make overseas credit notifications deliver operationally managed email through
the existing SMTP service. Operators will create, edit, enable, and bind
email templates in the existing notification template-management tab. An
enabled overseas email rule will resolve a valid account email, stage a record
with an email recipient snapshot, render a validated subject and body, and
deliver it through SMTP. Domestic SMS must remain unchanged.

This plan is stacked on PR #2746, `feat/notification-channel-foundation`,
because it requires its `NotificationRecord.recipient_type` and
`recipient_snapshot` migration. The implementation PR must target that branch
until #2746 reaches `main`; rebase onto `main` before final merge.

## Progress

- [x] 2026-09-02 14:15 CST: Confirmed existing SMTP configuration and the
  verification-code SMTP implementation.
- [x] 2026-09-02 14:15 CST: Decided that production email templates are
  operator-managed rather than hardcoded in application code.
- [x] 2026-09-02 14:28 CST: Created the stacked feature branch and inspected
  existing notification template, verified-email, policy, delivery, admin
  route, and template-management contracts.
- [x] 2026-09-02 17:10 CST: Implemented the data model, SMTP adapter, operator template
  create/update interface, policy validation, email recipient staging,
  delivery, and focused notification regression coverage.
- [x] 2026-09-02 17:10 CST: Added focused SMTP delivery and channel-specific frequency
  regression coverage, plus the affected admin-page test suite.
- [x] 2026-09-03 10:45 CST: Resolved review findings for email-rule selection,
  SMTP transport safety and retry classification, template/rule validation,
  contact-error visibility, and the affected frontend regression tests.
- [ ] Validate with a controlled devus recipient after the database migration
  is deployed.

## Surprises & Discoveries

- The repository already has SMTP settings and a verification-code sender in
  `flaskr.service.user.utils`, but that function owns verification-code Redis
  limits and persistence and must not be reused for billing notifications.
- `NotificationTemplate` already has a channel/provider/template-code unique
  key and generic placeholder storage. Email-specific subject, HTML body, and
  locale need structured persistence without changing the Aliyun SMS rows.
- PR #2746 intentionally keeps email rules disabled and stages only mobile
  recipients. This is correct until this plan supplies email-specific staging.

## Decision Log

- 2026-09-02: Use the existing SMTP configuration for email delivery. Extract
  a narrow shared SMTP send helper; keep verification-code rate limiting,
  verification-code content, and persistence in the user service.
- 2026-09-02: Formal notification email templates are created and maintained
  by operators. Code owns rendering, variable validation, the plain-text
  fallback, and UI strings, but not production subject/body copy.
- 2026-09-03: Use `channel=email`, `provider=smtp`, and a server-generated
  stable `EMAIL_<id>` template Code. Operators maintain one HTML-capable email
  body; the service derives the text alternative. Only enabled templates with
  valid variables can be bound to an enabled email rule.
- 2026-09-02: Email frequency is counted separately from SMS by including the
  channel in per-recipient/per-type frequency keys. A single rule still emits
  one channel only, so this does not create duplicate notices.
- 2026-09-02: Resolve the recipient from the account's normalized verified
  email first. Do not fall back to arbitrary identifiers that are not valid
  email addresses; stage an explicit contact error instead.
- 2026-09-02: Do not add an operator-triggered test-send endpoint in this PR.
  It would require a separate audited authorization boundary for arbitrary
  recipients, and the requested template-management workflow does not depend
  on it. Validate SMTP in devus through a disabled rule and controlled account
  instead.

## Outcomes & Retrospective

The implementation provides a complete overseas email notification workflow
without a source-code dependency for production copy. SMTP delivery remains to
be verified with a controlled devus account after the migration is deployed.

## Context and Orientation

`src/api/flaskr/service/billing/credit_notifications.py` owns notification
policy normalization, staging, record persistence, provider dispatch, retry,
and operator DTOs. `NotificationTemplate` and `NotificationRecord` are in
`src/api/flaskr/service/billing/models.py`. The existing SMTP configuration is
defined in `src/api/flaskr/common/config.py`; its verification-code caller is
`src/api/flaskr/service/user/utils.py`.

The operator interface lives in
`src/web/src/app/admin/operations/credit-notifications/`. The existing
template-management tab is the only template-management entry point; do not
add a separate top-level menu. Shared translations live under `src/i18n/`.

## Plan of Work

1. Define structured email-template fields on `NotificationTemplate` while
   preserving SMS columns and Aliyun synchronization semantics.
2. Create a generic SMTP transport helper that accepts an already rendered
   recipient, subject, plain body, and HTML body; make the verification-code
   sender use it only if this does not expand its behavioral surface.
3. Add email recipient resolution and per-channel staging. Missing or invalid
   emails must create an explicit skipped/contact-error outcome and never call
   SMTP.
4. Extend policy and template validation so an enabled email rule must bind an
   active local SMTP email template whose placeholders are satisfiable for that
   trigger event.
5. Add overseas-only operator CRUD and rule-binding UX. Domestic sites
   continue to expose Aliyun SMS template sync, not email-template editing.
6. Dispatch rendered email records through SMTP, preserving idempotency,
   retry, error categorization, and record detail visibility.

## Concrete Steps

1. Inspect `NotificationTemplate` consumers and add nullable email-only
   columns for `locale`, `email_subject`, and `email_html_body`; reuse
   `template_content` for the plain-text body and existing placeholder storage
   for parsed variables. Generate a new Alembic revision from the #2746 head.
2. Add a local SMTP template repository/service that permits create, update,
   enable, and disable only for
   `email + smtp` rows. Keep Aliyun synchronized rows read-only.
3. Extract a shared SMTP message builder/sender with a bounded timeout,
   verified TLS context, authenticated login, MIME alternative bodies,
   recipient normalization, cleanup that cannot overwrite an accepted send,
   and provider-safe error mapping. Do not log recipient addresses or template
   bodies.
4. Add channel-aware recipient staging and channel-specific frequency keys.
   Preserve current SMS keys and behavior exactly.
5. Wire the email branch into notification dispatch and retry. Store recipient
   snapshots, provider result metadata, and bounded failure reasons on the
   existing `NotificationRecord`.
6. Extend the template-management tab and rule editor for overseas email:
   table create/edit, one email body with generated text alternative,
   language/status filters, and active-template-only SMTP selection. Keep all
   user-facing text in shared i18n.
7. Seed no production copy from source. Have an operator create the initial
   three templates in devus, run dry-run/test-send, bind disabled rules, then
   explicitly enable each rule after delivery confirmation.

## Validation and Acceptance

- A devus operator can create an English email template with a valid subject,
  one email body, locale, and server-generated stable Code; invalid/missing
  placeholders prevent binding to an enabled rule.
- An overseas account with a verified email receives each configured credit
  notification exactly once through SMTP, and the record shows `email` plus
  the email snapshot.
- An account without a valid email never invokes SMTP and has an observable
  skipped/contact error record.
- Transient SMTP failures retry the same record, while a sent record is not
  resent. SMTP cannot provide strict exactly-once guarantees after an ambiguous
  network failure, so the service must not claim stronger semantics.
- Email and SMS frequency limits are independently enforced; existing domestic
  SMS frequency tests remain unchanged.
- Domestic template sync, SMS rule selection, and SMS delivery continue to
  pass their current test suites.
- The Alembic migration upgrades cleanly on MySQL and remains compatible with
  the already-applied #2746 recipient migration.

## Idempotence and Recovery

Template creation uses the existing `channel + provider + template_code`
unique key. SMTP errors leave the record retryable with a bounded provider
error code.
Disabling a rule or template prevents pending records from new delivery, using
the current-rule lookup behavior introduced by notification rule management.

The schema migration adds only nullable email-only fields, so domestic SMS
rows remain readable throughout rollout. Rollback disables email rules and
does not delete historical notification records or SMTP template content.

## Interfaces and Dependencies

- Base branch: `feat/notification-channel-foundation` / PR #2746 until merged.
- SMTP configuration: `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`,
  `SMTP_PASSWORD`, and `SMTP_SENDER`; environment-specific values stay out of
  source control.
- Existing policy key: `BILL_CREDIT_NOTIFICATION_SMS_CONFIG`, with managed
  per-rule `channel` values.
- Existing tables: `notification_records`, `notification_templates`; this PR
  requires a new Alembic revision and therefore a database-migration reminder
  in the PR description and release checklist.
- Operator and learner-facing strings: `src/i18n/*/modules/operations-credit-notifications.json`.

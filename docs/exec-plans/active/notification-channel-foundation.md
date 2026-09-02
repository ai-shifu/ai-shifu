# Notification Channel Foundation

## Purpose / Big Picture

Make credit-notification records channel-aware without changing the live
domestic SMS experience. After this work, every record has a generic recipient
type and recipient snapshot, while existing `mobile_snapshot` data and APIs
continue to work. This is the database and dispatch boundary required before
overseas email templates and delivery can be enabled in a later PR.

## Progress

- [x] 2026-09-02 10:40 CST: Created branch and confirmed current SMS-only policy,
  record, delivery, and operator-listing dependencies.
- [x] 2026-09-02 11:05 CST: Added generic recipient columns, a reversible
  backfill migration, and a single Alembic head.
- [x] 2026-09-02 11:05 CST: Kept SMS staging and delivery behavior while
  explicitly skipping unsupported record channels.
- [x] 2026-09-02 11:05 CST: Exposed generic recipient fields in operator APIs
  and the admin record views with legacy mobile fallbacks.
- [x] 2026-09-02 11:18 CST: Completed focused backend/frontend validation,
  migration syntax/head review, architecture-boundary validation, and diff
  review.

## Surprises & Discoveries

- The managed-rule JSON already stores `channel`, but save validation rejects
  every value except `sms`.
- `NotificationTemplate` already has the correct channel/provider/code unique
  key; no template-table migration is needed for this foundation.
- Existing records use `mobile_snapshot` in delivery, filters, frequency limits,
  serialization, and the admin UI. It must remain during the migration.
- The repository's prior Alembic head was `a3f9c1d05b28`, which already
  descends from the billing migration chain. Pointing the new revision at the
  older `b8c1d2e3f4a5` revision would have introduced an unnecessary extra head.

## Decision Log

- 2026-09-02: Add `recipient_type` and `recipient_snapshot` to
  `notification_records`; backfill historical rows as `mobile` and their
  current `mobile_snapshot`.
- 2026-09-02: Keep `mobile_snapshot` and current SMS-specific frequency/budget
  semantics. Email-specific limits and opt-out rules belong to PR4.
- 2026-09-02: Accept the `email` channel only as a disabled managed rule until
  a provider and email-template management are implemented. Enabled email
  rules remain invalid, so this PR cannot accidentally start or queue email
  delivery.
- 2026-09-02: Dispatcher behavior is explicit: SMS uses the current Aliyun
  path; unsupported channels finalize as skipped rather than falling through
  to SMS.

## Outcomes & Retrospective

Implemented on `feat/notification-channel-foundation`. The work preserves the
current domestic SMS path while making recipient storage and operator payloads
channel-aware. The newly added migration depends on the repository's single
current Alembic head and backfills historical records. Email delivery remains
intentionally disabled until the provider and template-management follow-up.

## Context and Orientation

`src/api/flaskr/service/billing/credit_notifications.py` owns policy parsing,
staging, delivery, records, and operator serialization. `NotificationRecord`
in `src/api/flaskr/service/billing/models.py` stores the historical SMS
snapshot. The admin notification page is under
`src/web/src/app/admin/operations/credit-notifications/`. Alembic revisions
live in `src/api/migrations/versions/`.

## Plan of Work

1. Define the generic recipient representation and migration.
2. Have SMS staging populate both legacy and generic snapshots.
3. Route delivery by record channel, retaining all existing SMS validation and
   provider calls in the SMS branch.
4. Return and render generic recipient data without breaking historical rows.
5. Add focused tests for migrated records, unsupported-channel protection, and
   unchanged SMS behavior.

## Concrete Steps

1. Add recipient constants and fields to `NotificationRecord`.
2. Generate and review an Alembic revision that adds both fields, backfills
   records, indexes the generic snapshot for future recipient filtering, and
   removes temporary server defaults.
3. Normalize rule channels as `sms` or `email`; reject enabled email rules
   until PR4 supplies approved email templates and a provider.
4. Create a small dispatch boundary around the current SMS delivery path and
   explicitly skip unsupported record channels.
5. Extend API serializers and admin record types to include generic recipient
   fields, displaying the generic snapshot with mobile fallback.
6. Add focused backend/frontend tests and run migration validation against a
   clean test database.

## Validation and Acceptance

- A migration upgrades a database containing historical SMS records; those
  rows read as `recipient_type=mobile` with their original number.
- New SMS notifications populate both snapshot forms and deliver exactly as
  before.
- A non-SMS record cannot call Aliyun and reaches an explicit skipped result.
- Existing operator list/detail payload consumers retain `mobile_snapshot` and
  can display the generic recipient.
- Existing SMS policy save, dry-run, retry, frequency, and record tests pass.

## Idempotence and Recovery

The migration adds non-null columns with temporary defaults, backfills only
empty generic snapshots from existing mobile snapshots, then removes defaults.
It is safe to rerun in a fresh migration environment. Rollback removes the
new index and columns; it does not alter the preserved legacy mobile data.
The runtime dispatcher treats unknown channels as skipped, preventing an
unsupported configuration from sending SMS to the wrong contact.

## Interfaces and Dependencies

- Existing config key: `BILL_CREDIT_NOTIFICATION_SMS_CONFIG`; this PR remains
  backward compatible and does not write a replacement key.
- Existing provider: Aliyun SMS only. No SMTP or email provider is configured
  or invoked by this PR.
- Database: production migration required before deploying backend code that
  writes generic recipient fields.
- Follow-up PR4 supplies email template management, recipient resolution,
  provider configuration, and email-specific delivery controls.

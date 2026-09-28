---
title: Notification Management Analytics
status: implemented
owner_surface: frontend
last_reviewed: ""
canonical: true
---

# Notification Management Analytics

Transferred without changing event semantics from the delivered plan. A full
producer/consumer review date is not inferred from this document move.

## Template management

- Business question: whether operators use the SMS and email template libraries,
  complete SMS provider synchronization or local email-list refresh, and save
  email template changes successfully. Compare outcomes by channel/provider;
  email refresh is not an SMTP delivery or provider-synchronization result.
- Population: authenticated operators on the credit-notification template tab.
  The resolved site contact mode chooses `sms`/`aliyun` or `email`/`smtp`; email
  views are eligible. Inactive tabs emit no exposure. Initial list loads and
  post-save list refreshes emit no manual sync attempt/result.
- Count units: exposures per mounted tab component; manual refreshes and saves
  per accepted action. Compare attempt/result volumes in the same report window
  by channel/provider. These best-effort events carry no request ID and are not
  a row-level joined funnel or proof of notification delivery.
- Exposure: `operator_notification_template_library_viewed` fires on the first
  active effect, once per component mount. Re-rendering or switching contact
  mode does not reset that component's exposure ref.
- Manual refresh: `operator_notification_template_sync_attempt` fires when
  `fetchTemplateOptions('manual')` starts; the UI disables refresh while loading.
  The current request emits `operator_notification_template_sync_result` after
  settlement. `provider_available` selects `success` versus `failed`; `source`
  uses the response value or `local`. A rejected request reports failed/local.
  Superseded list requests return without a result event, so not every recorded
  attempt is guaranteed a terminal row.
- Filters and details: `operator_notification_template_filter_applied` fires
  when a nonempty keyword field loses focus or a non-All status is selected.
  `operator_notification_template_detail_opened` fires on the detail action.
  Repeated actions are counted; query text and selected template data are absent.
- Email saves: `operator_notification_template_save_attempt` fires when the
  create/update handler or status-change handler starts. Its `action` is
  `created`, `updated`, or `status_updated`. The matching
  `operator_notification_template_save_result` reports `success` after the
  mutation succeeds and its initial-mode refresh settles, or `failed` if the
  mutation rejects. List-refresh errors are handled by the list path and do not
  convert a successful mutation into a failed save. Failed editor saves retain
  the editor; tracking failures never change the save/list behavior.

| Event suffix (`operator_notification_template_`) | Exact custom payload |
| --- | --- |
| `library_viewed`, `sync_attempt`, `detail_opened` | `channel`, `provider` |
| `filter_applied` | `channel`, `provider`, `filter` (`keyword` or `status`) |
| `sync_result` | `channel`, `provider`, `outcome` (`success` or `failed`), `source` (`provider` or `local`) |
| `save_attempt` | `channel=email`, `provider=smtp`, `action` (`created`, `updated`, or `status_updated`) |
| `save_result` | Save-attempt payload plus `outcome` (`success` or `failed`) |

The only channel/provider pairs are `sms`/`aliyun` and `email`/`smtp`. Do not emit
message subjects/bodies, template content/codes/names/IDs, contact details, user
identifiers, filter text, raw errors or provider request IDs. Each save invocation
has one attempt and one result; no cross-invocation deduplication is added.

Consumers are operator notification-center adoption and synchronization/save
reliability reports. This document now includes existing email variants and save
events; it does not change any producer, payload or event name. Reports that
previously filtered only SMS must include the existing email rows and distinguish
refresh success, template-save success and actual email delivery.

Source: `src/web/src/app/admin/operations/credit-notifications/page.tsx`,
`CreditNotificationTemplateManagementTab.tsx`, and `notificationTemplateTracking.ts`.
The adjacent `page.test.tsx` covers SMS sync, email exposure and create success/
failure, status actions, allowed payloads and tracking failure isolation. These
fixtures are not a claim that every email edit/filter/refresh variant is directly
asserted; inspect producer paths when extending that coverage.

## Managed rule actions

- Business question: whether operators configure and maintain notification rules
  in SMS or email mode. Both use `CreditNotificationRuleManagementSection` and
  the same action callback; email actions are eligible too.
- Event name: `operator_notification_rule_action`.
- Population and trigger: authenticated operators in the configuration tab,
  after create, edit, confirmed delete, or enabled-state change in the local
  policy draft. This is an accepted draft action, not a persisted policy save.
  Count each callback invocation; no per-rule/session deduplication is applied.
- Current payload: `channel=sms`, `action` (`created`, `edited`, `deleted`, or
  `toggled`), and `trigger_event` (`credit_granted`, `credit_expiring`, or
  `low_balance`). The page's `NOTIFICATION_RULE_TRACKING_CONTEXT` hardcodes
  `sms` for email actions as well. Consumers must treat this event as combined
  rule-action volume; its channel cannot establish a true SMS/email split.
  This is an existing producer mismatch, not an instruction to keep mislabeling
  new events. A future correction needs coordinated producer/consumer/schema
  compatibility and regression work; existing rows cannot recover rule channel.
- Privacy and delivery: omit rule IDs/names, template codes/content, user/contact
  data and policy conditions. The shared best-effort wrapper must never block
  the local configuration workflow.

## Legacy SMS-to-email rule migration

`operator_notification_legacy_sms_rules_migrated` fires after the operator
confirms migration and the local draft's legacy rules are replaced by disabled
email rules with empty template bindings. The migration control is eligible in
email contact mode when the list is nonempty and every rule is legacy. Opening
or cancelling confirmation emits no migration event. The callback runs once per
accepted confirmation, before any later policy save, and does not emit separate
create/delete action events for the replaced rules.

The exact payload is `channel=email` and `rule_count='3'` (a string literal in
the current producer, not a dynamically measured count). Retain the stable event
name despite its `legacy_sms` wording. Consumers may count accepted draft
migrations; they must not treat this as persisted configuration, email delivery,
or infer a dynamic migrated-rule total from the constant payload. The same
privacy exclusions and best-effort delivery apply.

Sources: `CreditNotificationRuleManagementSection.tsx`,
`notificationRuleTracking.ts`, and the callback wiring in `page.tsx`, all under
`src/web/src/app/admin/operations/credit-notifications/`. The adjacent page suite
covers SMS action payloads, email rule creation and the confirmation migration
payload. It does not directly assert the email action's mislabeled channel; that
limitation is established from the shared callback and constant above.

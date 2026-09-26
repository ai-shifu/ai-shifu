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

- Business question: whether operators are configuring and maintaining managed SMS notification rules.
- Event name: `operator_notification_rule_action`.
- Actor and surface: authenticated operators in the credit-notification configuration tab.
- Trigger: emit after an operator creates, edits, deletes, or changes a rule's enabled state in the local policy draft. The event does not represent a persisted save.
- Payload allowlist: `channel` (`sms`), `action` (`created`, `edited`, `deleted`, or `toggled`), and `trigger_event` (one of the three supported events). Do not emit rule IDs, rule names, template codes or content, user identifiers, phone numbers, or policy conditions.
- Consumers: operator configuration adoption reporting. This is additive and must never block the configuration workflow.
- Verification: focused frontend tests cover eligible exposure, accepted sync attempts and outcomes, filter/detail events, payload allowlists, and analytics failures that do not alter the user workflow.

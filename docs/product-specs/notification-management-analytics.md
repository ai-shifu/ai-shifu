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

- Business question: whether operators discover the domestic SMS template library and complete provider synchronizations successfully.
- Metric definition: per operator session, count one eligible template-library exposure, every accepted manual synchronization attempt, and one terminal result for each attempt.
- Event names: `operator_notification_template_library_viewed`, `operator_notification_template_sync_attempt`, `operator_notification_template_sync_result`, `operator_notification_template_filter_applied`, and `operator_notification_template_detail_opened`.
- Actor and surface: authenticated operators on the credit-notification template-management tab; email-channel placeholder views are excluded.
- Trigger and deduplication: exposure fires once per mounted eligible tab view; sync attempt fires after the refresh guard accepts a click; a result fires once after that request settles; filter and detail events are not deduplicated because repeated operator actions are meaningful.
- Payload allowlist: `channel` (`sms`), `provider` (`aliyun`), `source` (`provider` or `local`), `outcome` (`success` or `failed`), and `filter` (`keyword` or `status`). Do not emit template content, template codes, names, user identifiers, contact information, or provider request IDs.
- Consumers: operator notification-center adoption and provider synchronization reliability reporting. This is a new additive event family.

## Managed rule actions

- Business question: whether operators are configuring and maintaining managed SMS notification rules.
- Event name: `operator_notification_rule_action`.
- Actor and surface: authenticated operators in the credit-notification configuration tab.
- Trigger: emit after an operator creates, edits, deletes, or changes a rule's enabled state in the local policy draft. The event does not represent a persisted save.
- Payload allowlist: `channel` (`sms`), `action` (`created`, `edited`, `deleted`, or `toggled`), and `trigger_event` (one of the three supported events). Do not emit rule IDs, rule names, template codes or content, user identifiers, phone numbers, or policy conditions.
- Consumers: operator configuration adoption reporting. This is additive and must never block the configuration workflow.
- Verification: focused frontend tests cover eligible exposure, accepted sync attempts and outcomes, filter/detail events, payload allowlists, and analytics failures that do not alter the user workflow.

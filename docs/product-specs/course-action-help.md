---
title: Course action menu help
status: implemented
owner_surface: frontend
last_reviewed: 2026-10-26
canonical: true
---

# Course action menu help

The teacher course list keeps each course action as a single-line menu item.
Hovering an available action or focusing it with the keyboard opens a tooltip
explaining the operation. Selecting the item performs the same action as before.
The shared Tooltip primitive owns positioning and accessible descriptions. The
menu requires 300 ms of continuous pointer dwell before showing help; keyboard
focus shows it immediately. Pointer-induced menu focus cannot bypass the delay.
Help does not grant permissions or change whether an action is available.

## Product analytics contract

This help interaction follows the
[frontend product analytics contract](../references/frontend-product-analytics.md).
Moving the explanation from visible menu text into a tooltip introduces a new
invocation path, so tooltip use has an additive event contract.

- Business question: which course actions need the most explanation, so product
  owners can prioritize clearer labels and onboarding?
- Metric definition: weekly help-view event counts and distinct eligible
  signed-in course-administration users by action on the course list. This
  population includes teachers, authorized course collaborators and operators
  that satisfy the shared analytics policy. Compare observed help views across
  actions. Menu-open or action-exposure denominators are not
  collected, so these counts are not help-open rates or action-conversion rates.
- Event: `creator_course_action_help_view`.
- Actor and surface: the same eligible signed-in course-administration users
  defined above, using the course action menu with surface `admin_course_list`.
- Trigger: help becomes visible for an action in an open course menu after
  300 ms of continuous pointer dwell or immediately on keyboard focus. Merely
  rendering a card, opening a menu, pointing briefly at an item, or selecting an
  item does not emit it.
- Population: include draft and published courses and the archive-restore
  variant. Include pointer and keyboard tooltip opens. Exclude hidden actions,
  closed menus, guest learner surfaces, learner/editor previews and accounts
  excluded by the shared analytics policy. Course-list authorization remains
  owned by the existing route; this component does not broaden it.
- Count unit and deduplication: at most one help view per action per opening of
  a course card's menu. A component-local Set is reset when the menu opens;
  repeated hovering or refocusing the same action within that opening does not
  emit again. Closing and deliberately reopening the menu starts a new count
  window. Mark an action before calling tracking so failed delivery is not
  retried by repeated hover or focus.
- Correlation: no course ID or additional user ID is needed. The existing shared
  identity supplies distinct eligible course-administration users. There is no per-menu identifier
  or exact join with action outcomes.
- Consumers: the product owner reviews aggregate weekly help demand by action
  in Umami. No checked-in query or dashboard consumes the new event yet.
- Compatibility: additive new event; historical menu interactions have no
  equivalent signal and must not be backfilled or treated as zero demand.
- Failure isolation: use `useTracking`, without awaiting delivery. Missing or
  failed analytics must not affect tooltips, menu selection or the operation.
- Verification: component tests cover real tooltip hover/focus opening,
  non-opening pointer interactions, per-open deduplication, archive/restore,
  hidden-action exclusions, exact event/payload privacy and tracking failure.

| Field     | Type   | Allowed values                                                                            | Cardinality | Privacy class | Why required                    |
| --------- | ------ | ----------------------------------------------------------------------------------------- | ----------- | ------------- | ------------------------------- |
| `surface` | string | `admin_course_list`                                                                       | One         | Non-personal  | Identifies the menu surface     |
| `action`  | string | `activate_learners`, `create_discount_code`, `manage_collaborators`, `archive`, `restore` | Five        | Non-personal  | Groups help demand by operation |

The payload is an explicit two-field allowlist. It never includes course titles,
descriptions, tooltip text, account contacts, coupon values, URLs, raw errors or
other user-authored content. Shared user exclusions and transport safeguards
apply independently of this feature.

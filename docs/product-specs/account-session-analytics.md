---
title: Account Session Analytics
status: implemented
owner_surface: frontend
last_reviewed: 2026-09-26
canonical: true
---

# Account session analytics contract

Covers the two user-facing flows added for account session control: approving a
command-line client in the browser (`/login/device`), and reviewing or ending
sign-in sessions from the account menu.

Both are asynchronous workflows where a single signal cannot describe the
outcome: a prompt that is opened and abandoned looks identical to one that was
rejected unless the terminal states are recorded separately.

### device authorization

- Business question: when someone is asked to authorize a command-line client,
  how often do they complete it, how often do they refuse, and how often does
  the prompt go unanswered? A refusal rate that is not near zero would mean
  people are being shown requests they did not start.
- Metric definition: numerator is approval events (`device_auth_approved`);
  denominator is prompt exposure events (`device_auth_prompt_shown`) in the
  same UTC calendar week, grouped by the shared `device_os`, `from_link`,
  `host_platform`, `skill_id`, and `skill_version_major` fields.
  Abandonment is the residual, `1 - (approved + denied) / shown`, and is
  meaningful only because exposure is counted separately. Without a request
  identifier, this calculation is aggregate and cannot be presented as a
  row-level join.
- Event name(s): `device_auth_prompt_shown`, `device_auth_approved`,
  `device_auth_denied`.
- Actor and surface: the signed-in user, on the `/login/device` page only.
- Trigger: exposure fires once per resolved pending request, from a
  post-commit effect. The outcomes fire only after the backend confirms the
  decision, never on the click itself.
- Population: signed-in users. A signed-out visitor is redirected to sign in
  first and emits nothing.
- Count unit: one pending authorization request.
- Deduplication: keyed on the pairing code held in a ref, so re-renders and a
  second effect pass cannot inflate the denominator. Scope is one mounted page.
- Correlation: aggregate dimensions only. The pairing code and Skill handoff
  ID are deliberately absent from every payload, so these events cannot be
  joined to a specific request.
- Consumers: the periodic Skill acquisition and journey report compares the
  authorization funnel by host platform, Skill, and version.
- Compatibility: the event names are unchanged. Skill dimensions are additive
  payload fields; ordinary device requests use `unattributed` for all three.
- Verification: `src/web/src/app/login/device/page.test.tsx` asserts the
  exposure fires exactly once, that pairing and handoff identifiers stay out
  of the payload,
  that link-opened and manually entered outcomes retain the same `from_link`
  dimension as their exposure, that outcomes fire on confirmation, and that a
  failed decision emits no outcome.

| Field                 | Type    | Allowed values                                                                   | Cardinality | Privacy class | Why required                                                       |
| --------------------- | ------- | -------------------------------------------------------------------------------- | ----------- | ------------- | ------------------------------------------------------------------ |
| `device_os`           | string  | `android`, `chromeos`, `ios`, `linux`, `macos`, `other`, `unknown`, or `windows` | low         | non-personal  | tells whether refusals cluster on one platform                     |
| `from_link`           | boolean | true/false                                                                       | low         | non-personal  | separates prompts opened from the link from codes typed by hand    |
| `host_platform`       | string  | `workbuddy`, `doubao`, `qclaw`, `lobster`, `codex`, `direct`, `unattributed`     | low         | non-personal  | compares host-platform funnels                                     |
| `skill_id`            | string  | `ai-shifu-course-creator`, `unattributed`                                        | low         | non-personal  | identifies the supported Skill funnel                              |
| `skill_version_major` | string  | `v0` through `v9`, `unknown`, or `unattributed`                                  | low         | non-personal  | finds major-version-specific drop-offs without sending caller text |

### session management

- Business question: do people use session control at all, and when they do,
  are they ending one session they recognise as wrong or clearing everything?
  The second case suggests they could not tell which session was suspicious.
- Reporting window: UTC calendar month, including its first instant and excluding
  the first instant of the next month. Use the event timestamp for membership.
- Adoption metric: distinct users with a successful revoke divided by distinct
  users with `session_list_opened` in that month. This is aggregate best-effort
  telemetry, not a joined funnel; missing open events can make the ratio exceed
  one. Do not infer authorization or account safety from it.
- Revocation cohorts: let S be distinct users with `session_revoked` and B be
  distinct users with `session_revoked_others` in that month. The denominator
  for all three shares is |S union B|. Report single-only |S minus B|, bulk-only
  |B minus S|, and both |S intersect B|. These groups are disjoint and sum to
  the denominator. Repeated actions do not increase a user's cohort weight;
  actions in another month do not change the current month's membership.
- Empty denominator: display unavailable, not a fabricated zero-percent split.
- Event name(s): `session_list_opened`, `session_revoked`,
  `session_revoked_others`.
- Actor and surface: the signed-in user, from the account menu on the learner
  and teacher surfaces. The surface is carried on the open event.
- Trigger: open fires when the menu entry is activated; revoke events fire
  only after the backend confirms, so a failed revoke emits nothing. Capture
  the shared tracking identity generation before each single or bulk request;
  emit its success event only if that generation still matches at completion.
  An account replacement or identity reset suppresses the stale outcome without
  changing the revocation result, list refresh, or error handling.
- Population: signed-in users. The entry is hidden while signed out.
- Count unit: distinct pseudonymous users for both adoption and cohort shares.
  Event volumes may be reported separately, but never labeled as user shares.
- Deduplication: producers still emit each confirmed action and each dialog
  opening. Reporting deduplicates users over the entire UTC month, across all
  their sessions and both surfaces; producer deduplication is not required.
- Correlation: use the existing anonymous analytics identity to associate a
  user's delivered events. Use only rows with that identity for user-based
  metrics. Shared tracking queues calls until identification is ready; calls
  can be discarded before delivery if identification never succeeds or the
  identity changes. The dataset therefore cannot measure all missing-identity
  events or provide an exclusion count for those lost calls. State this
  undercount limitation alongside the observed-user cohorts. Do not invent a fallback
  from session IDs, credentials, or device data. Identity resets can split a
  person into multiple observed users; this limitation belongs with the report.
- Consumers: no dedicated session-report query is deployed in this repository.
  Periodic product reports and future consumers must use these definitions.
- Compatibility: event names, payloads, and successful-confirmation timing are
  unchanged; outcomes crossing an identity replacement are now excluded at the
  producer. This clarification replaces the ambiguous event-based split.
  Recalculate historical cohorts from available user-level events, or label old
  aggregates as incomparable when those events are unavailable. Existing events
  emitted after an identity replacement cannot be reassigned reliably because
  the initiating identity was not recorded; disclose this historical limitation.
- Verification:
  `src/web/src/components/Settings/SessionManagerModal.test.tsx`
  asserts that outcomes fire only on confirmed revocations, that a failed
  revocation emits nothing, and that no session identifier reaches a payload.
  It covers single and bulk requests across identity replacement, unchanged
  identity, and synchronous/asynchronous tracking failures. Tracking failures
  must leave successful revocation and list refresh unaffected.

| Field     | Type   | Allowed values     | Cardinality | Privacy class | Why required                                                 |
| --------- | ------ | ------------------ | ----------- | ------------- | ------------------------------------------------------------ |
| `surface` | string | `learner`, `admin` | low         | non-personal  | shows which surface people manage sessions from              |
| `source`  | string | `web`, `cli`, ``   | low         | non-personal  | distinguishes ending a browser session from ending a CLI one |

Examples for a single UTC month: a user with three single revocations counts
once in single-only; a user with two bulk revocations counts once in bulk-only;
a user with both kinds at least once counts once in both. With one user in
each group, each share is 1/3. A failed request belongs to none of the groups.

The existing event payload allowlist is unchanged: `surface` is on
`session_list_opened`, `source` is on `session_revoked`, and
`session_revoked_others` has no custom fields. Follow the
[shared analytics contract](../references/frontend-product-analytics.md).

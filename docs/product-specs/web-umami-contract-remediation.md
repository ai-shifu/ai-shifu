---
title: Cook Web Umami Contract Remediation
status: implemented
owner_surface: frontend
last_reviewed: 2026-08-31
canonical: true
---

# Cook Web Umami Contract Remediation

## Goal and boundary

This specification owns the Cook Web event families migrated during the 2026-08-30
analytics remediation. It complements, and does not replace,
`docs/references/frontend-product-analytics.md`.

Umami remains best-effort product analytics. None of these events is a billing,
authentication, authorization, audit, or operational source of truth. Producers
do not send user-authored text, prompts, model output, names, descriptions,
contact details, coupon codes, credentials, complete URLs, raw errors, or
provider responses.

## Direct replacement policy

This remediation does not dual-write or retain incorrectly defined events. The
following producer and consumer names are deleted together:

- generic `visit`
- `creator_publish_click` and `creator_publish_confirm`
- `learner_login_success`
- `learner_pay_cancel`
- `creator_billing_checkout_click`
- `creator_shifu_create_click` and `creator_shifu_create_success`

The generic `visit` event has no replacement. The remaining predecessor
families are replaced by:

- `creator_publish_attempt` and `creator_publish_result`
- `learner_login_attempt` and `learner_login_result`
- `learner_pay_modal_view`, `learner_pay_modal_dismiss`,
  `learner_payment_attempt`, `learner_payment_result`, and
  `learner_payment_status`
- `creator_billing_checkout_attempt`, `creator_billing_checkout_result`, and
  `creator_billing_checkout_status`
- `creator_course_create_attempt`, `creator_course_create_result`, and
  `creator_course_create_cancel`

Producers, dashboards, alerts, exports, and ad-hoc queries must switch to those
canonical families in the same release; they must not merge with or fall back
to the old names.

Historical Umami rows under deleted names are not read or backfilled. Canonical
series start when the replacement producers are deployed, and their first
rolling windows may therefore be partial.

## Shared delivered schema

`useTracking` delivers only the producer's reviewed flat scalar event data. It
does not append `user_id`, `user_type`, `device`, or a localized timestamp. The
transport establishes one pseudonymous distinct ID separately and adds a
normalized route without credentials, query, fragment, or dynamic path values.
Umami retains its standard tracker envelope (`website`, `hostname`, browser
`language`, and `screen`); those platform fields are not duplicated into event
data. Arrays, objects, dates, `null`, and non-finite numbers are dropped.

`UmamiLoader` is the only pageview producer. One normalized pageview is emitted
on the first eligible render and after each SPA pathname transition. Query-only
changes are deduplicated; business events never synthesize pageviews.
Calls queued for a pending identity are discarded if the account changes, and
the queue is not drained until the tracker can complete `identify`; this avoids
cross-account attribution at the cost of dropping best-effort telemetry during
an identity race.

Consumer migration impact: dashboards that used the removed implicit fields,
localized `timeStamp`, full URLs/titles/referrers, dynamic route values, object
serialization, or business-event pageview backfill must migrate. These fields
are not backfilled under another name.

## Creator authoring interactions

- Business question: which successful authoring operations and accepted editor
  actions are used, and which follow-up interaction mode is saved, without
  collecting course content or provider configuration?
- Metric definition: raw successful saves/creates and accepted actions per day,
  grouped only by the documented enums or stable business IDs. The follow-up
  adoption view groups successful `creator_shifu_setting_save` rows by
  `follow_up_mode`. These are usage counts, not exact user funnels.
- Actor and surface: authenticated teachers in Cook Web authoring surfaces.
- Population: normal and read-only-aware producer eligibility as implemented by
  each control; failed validation, rejected API calls, and disabled controls are
  excluded unless the event explicitly represents the accepted click.
- Deduplication: no persisted dedupe. A successful API operation or accepted
  handler invocation is one count; render and React re-renders emit nothing.
- Consumer: authoring adoption queries owned by product analytics.
- Consumer change: the listed event names are retained with payloads narrowed
  in place. Queries using removed free-form fields must migrate. The
  2026-09-02 contract revision adds `follow_up_mode` to
  `creator_shifu_setting_save`; historical rows are not backfilled and a
  missing value must be treated as `legacy_unknown`, never inferred as `text`.

| Event                          | Exact trigger                                                                | Complete payload                                                                                                 |
| ------------------------------ | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `creator_shifu_setting_save`   | After the course-settings API succeeds                                       | `shifu_bid`, `save_type`, `tts_enabled`, `default_listen_mode_enabled`, `use_learner_language`, `follow_up_mode` |
| `creator_outline_setting_save` | After lesson settings save succeeds                                          | `shifu_bid`, `outline_bid`, `save_type`, `variant`, `learning_permission`, `hide_chapter`                        |
| `creator_outline_prompt_save`  | After chapter prompt/settings save succeeds                                  | `shifu_bid`, `outline_bid`, `save_type`                                                                          |
| `creator_outline_create`       | After an outline unit is created                                             | `shifu_bid`, `outline_bid`, `parent_bid`                                                                         |
| `creator_shifu_preview_click`  | Immediately after the enabled preview handler accepts the click, before save | `shifu_bid`                                                                                                      |
| `creator_lesson_preview_click` | Immediately after the enabled lesson preview handler accepts the click       | `shifu_bid`, `outline_bid`                                                                                       |

Allowed enums are `save_type=auto|manual`, `follow_up_mode=text|live_voice`,
`variant=chapter|lesson`, and `learning_permission=normal|trial|guest`, as
defined by `LEARNING_PERMISSION` in `src/web/src/api/studyV2.ts`.
Course/chapter/lesson names, descriptions, system prompts, model names, voice
IDs, provider configuration, URLs, and route text are excluded from these
contracts.

## Learner navigation and shared interactions

- Business question: which live learner navigation/reset controls are used, and
  which configured support surface is opened?
- Population: guest and logged-in learners on a successfully loaded live course
  may emit navigation and reset events. Teacher preview, blocked
  access, invalid/unloaded courses, same-lesson clicks, and render-only updates
  are excluded. The support rail separately includes anyone shown the configured
  admin or invite surface.
- Deduplication: navigation and support clicks count per accepted click; reset
  confirm counts once after a successful reset.
- Consumer change: existing navigation/reset/support queries retain their event
  names; removed text/URL fields must not be queried. Generic `visit` is deleted
  without a replacement event.

| Event                   | Exact trigger                                                             | Complete payload                              |
| ----------------------- | ------------------------------------------------------------------------- | --------------------------------------------- |
| `nav_section_switch`    | An accepted live learner catalog navigation changes to a different lesson | `shifu_bid`, `from_lesson_id`, `to_lesson_id` |
| `reset_chapter`         | A live learner reset control accepts a click                              | `shifu_bid`, `chapter_id`                     |
| `reset_chapter_confirm` | The accepted live learner reset operation succeeds                        | `shifu_bid`, `chapter_id`, `lesson_id`        |
| `contact_us_click`      | Immediately before the configured support target opens                    | `surface`                                     |

The only contact enum is `surface=admin|invite|other`.

## Creator publishing

- Business question: how often do accepted publish attempts finish, and at
  which bounded stage do failures occur?
- Metric definition: daily `creator_publish_result` outcomes divided by
  `creator_publish_attempt` events, grouped by learning mode. There is no
  attempt ID, so the ratio is aggregate and must not be presented as a row-level
  join.
- Trigger: attempt after enabled/re-entry guards and before saving; result once
  after save and publish complete or one of them throws.
- Population: eligible authenticated teachers; invalid or disabled controls are
  excluded.
- Count unit and dedupe: one accepted handler invocation; the existing publish
  in-flight guard prevents concurrent re-entry.
- Consumer: creator publish reliability and adoption dashboard.
- Replacement: delete `creator_publish_click` and `creator_publish_confirm`
  producers and consumers. All publish queries use the attempt/result pair.

| Event                     | Fields and allowed values                                                                               |
| ------------------------- | ------------------------------------------------------------------------------------------------------- |
| `creator_publish_attempt` | `shifu_bid`; `learning_mode` is `read`, `listen`, `classroom`, or `default`                             |
| `creator_publish_result`  | attempt fields; `outcome` is `success` or `failed`; failed only: `failure_stage` is `save` or `publish` |

## Learner authentication

- Business question: what is the accepted login volume and terminal success
  rate by method?
- Metric definition: daily results divided by attempts for each `login_method`.
  Repeated deliberate attempts count again; without an attempt ID, only
  aggregate conversion is valid.
- Trigger: after local validation and terms acceptance, immediately before the
  password/SMS/OAuth-start request; result after local login state is committed
  or a bounded terminal failure is known. OAuth callback results correlate to
  the earlier start only at aggregate level.
- Population: guests using password, SMS, or Google login. Validation-only and
  terms-dialog opens are excluded.
- Deduplication: UI submission guards own concurrent suppression; otherwise none.
- Consumer: login conversion and reliability analysis.
- Replacement: delete the `learner_login_success` producer and consumers. Login
  queries use `learner_login_attempt` and `learner_login_result`.

| Event                   | Fields and allowed values                                                                                                                                                                 |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `learner_login_attempt` | `login_method` is `password`, `sms`, or `google`                                                                                                                                          |
| `learner_login_result`  | `login_method`; `outcome` is `success` or `failed`; failed only: `failure_category` is `credentials_rejected`, `request_failed`, `start_failed`, `callback_invalid`, or `callback_failed` |

Credentials, mobile/email identifiers, OAuth code/state, token, user ID, and raw
backend messages are excluded.

## Device authorization

- Business question: which device-authorization prompts are resolved by the
  user, and how does that vary by a bounded operating-system category?
- Metric definition: approved and denied outcomes divided by prompt exposures,
  grouped only by the shared `device_os` and `from_link` fields. There is no
  request identifier, so this is an aggregate ratio rather than a row-level
  join.
- Trigger: prompt shown once after a pairing request resolves; approved or
  denied once after the corresponding API call succeeds.
- Population: authenticated users viewing a valid pending device request.
  Invalid, expired, unauthenticated, and failed-decision requests are excluded
  from terminal outcomes.
- Deduplication: exposure once per pairing code in the mounted page; the
  submitting guard prevents concurrent decisions, and only successful API
  decisions emit a terminal event.
- Consumer: device-authorization adoption and completion analysis.

| Event                      | Complete reviewed field set |
| -------------------------- | --------------------------- |
| `device_auth_prompt_shown` | `device_os`, `from_link`    |
| `device_auth_approved`     | `device_os`, `from_link`    |
| `device_auth_denied`       | `device_os`, `from_link`    |

`device_os` is exactly one of `android|chromeos|ios|linux|macos|other|unknown|windows`.
The pairing code, device name, client version, IP address, raw operating-system
string, user identity, and raw errors are excluded.

## Learner payment

- Business question: which eligible payment surfaces and channels lead from a
  shown modal to an accepted attempt and a confirmed terminal outcome?
- Metric definition: over a named window, distinct `order_id` terminal outcomes
  by channel compared with distinct attempted orders; modal views provide the
  eligible-view denominator. Pending status is not a terminal result.
- Trigger: modal view once after the modal is ready; attempt when Stripe submit
  or redirect, WeChat JSAPI, or a mobile native/QR action is accepted, and when
  a desktop QR credential becomes usable; result once when paid,
  provider-failed, or a provider returns an explicit cancellation marker for a
  product-confirmed order. Closing the learner modal is abandonment only and
  never a terminal payment result. Status fires when the provider accepted work
  but the existing product flow reports a processing state, a direct status
  synchronization rejects, or the existing polling state reaches its timeout
  without confirmed payment. Analytics only observes those states; it does not
  add a query, deadline, retry, or payment-state transition.
- Population: eligible logged-in learners on desktop/mobile payment surfaces.
  Logged-out price previews can emit modal view but cannot emit payment attempt.
- Deduplication: modal view once per open lifecycle. A provider-confirmed
  terminal result closes only its matching unresolved channel; a generic
  order-level terminal result closes the remaining unresolved channel set and
  is emitted once. A deliberate retry reopens its channel.
- Correlation: `order_id` joins attempts/results to product-owned order data;
  `shifu_bid` groups by course. Both are pseudonymous machine IDs. A Stripe
  return-page order ID is eligible only after the product API has confirmed it;
  an unverified query parameter is never analytics data. When a generic
  order-level observation has no provider-confirmed channel, one distinct
  unresolved attempted channel keeps that channel and multiple distinct
  unresolved attempted channels use `channel=other`; the latest selected
  channel is never treated as proof. Direct Stripe PaymentElement and WeChat
  JSAPI confirmation evidence is retained only for the same product-owned
  order and current accepted attempt. Cross-order, cross-lifecycle, superseded,
  and already-closed provider callbacks are ignored for provider-specific
  analytics attribution while their original payment synchronization still
  runs. A generic product-owned paid observation does not carry analytics
  context through the payment hook; it resolves only from the current
  unresolved channel set and uses `channel=other` when that set is ambiguous.
- Consumer: learner checkout conversion and provider reliability dashboard.
- Replacement: delete the `learner_pay_cancel` producer and consumers. Modal
  abandonment uses only `learner_pay_modal_dismiss`; a provider-confirmed
  cancellation of an accepted payment attempt uses `learner_payment_result`
  with `outcome=cancelled`.

| Event                       | Fields and allowed values                                                                                                                                           |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `learner_pay_modal_view`    | `shifu_bid`, finite `price_amount`, `currency` as `CNY`, `USD`, or `other`                                                                                          |
| `learner_pay_modal_dismiss` | `shifu_bid`, optional `order_id`, `dismiss_surface` is `modal` or `payment_page`, `had_payment_attempt`                                                             |
| `learner_payment_attempt`   | `shifu_bid`, optional `order_id`, `channel` is `wechat_jsapi`, `wechat_qr`, `alipay_qr`, `stripe`, or `other`; `surface` is `desktop`, `mobile`, or `stripe_return` |
| `learner_payment_result`    | attempt fields; `outcome` is `success`, `failed`, or `cancelled`; failed only: `failure_category` is `provider_failed`, `missing_order`, or `status_lookup_failed`  |
| `learner_payment_status`    | attempt fields; `status=pending`                                                                                                                                    |
| `learner_coupon_apply`      | `shifu_bid`, `outcome=success`                                                                                                                                      |

The coupon value, checkout URL, client secret, provider payload, payment method,
receipt, and raw failure are excluded. A Stripe SDK or network rejection after
an accepted PaymentElement attempt records `status=pending` because the payment
outcome is unconfirmed; it does not invoke product error handling or expose the
raw rejection.

## Creator billing checkout

- Business question: which billing products and providers reach checkout and a
  terminal payment state in domestic and global markets?
- Metric definition: distinct billing-order outcomes over attempts by market,
  product type, provider, and source surface. Pending and recoverable
  confirmation states are reported separately and are never counted as terminal
  failures.
- Trigger: attempt immediately before an accepted checkout request; result once
  when the producer observes paid, an explicit checkout cancellation, or a state
  the billing state machine cannot later correct; status before a redirect/QR
  handoff, while a Stripe return remains pending, or when its confirmation is
  still recoverable.
- Population: authenticated teachers eligible for billing. Disabled,
  validation-only, and coming-soon controls are excluded.
- Deduplication: existing checkout in-flight guards prevent concurrent duplicate
  requests. Return-page status is deduped per billing order and rendered state;
  each mounted return flow invokes at most one terminal result for an order.
- Correlation: `bill_order_bid` is the pseudonymous product-owned order key. A
  Stripe return-page value is eligible only after the billing API has confirmed
  it. A cancellation additionally requires the session-local analytics marker
  written after checkout confirms a Stripe redirect; missing or unavailable
  storage suppresses the cancellation event without changing synchronization,
  UI, or retry behavior. Cancellation and confirmation-failure events omit an
  unverified query parameter.
- Consumer: billing checkout adoption and provider reliability analysis; the
  billing ledger remains the financial source of truth.
- Replacement: delete the `creator_billing_checkout_click` producer and
  consumers. Billing queries use attempt/result/status.

| Event                              | Complete reviewed field set                                                                                                                                                                                                                                                     |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `creator_billing_checkout_attempt` | applicable subset of `billing_market`, `product_type`, `product_bid`, `product_code`, `billing_interval`, finite `price_amount`, `currency`, finite `credit_amount`, `payment_provider`, `payment_channel`, `checkout_action`, `source_surface`, `source_tab`, `bill_order_bid` |
| `creator_billing_checkout_result`  | attempt fields plus `outcome` as `success`, `failed`, or `cancelled`; failed only: bounded `failure_category`                                                                                                                                                                   |
| `creator_billing_checkout_status`  | attempt fields plus `status` as `pending` or `confirmation_failed`                                                                                                                                                                                                              |

Allowed markets are `domestic|global`; product types `plan|topup`; source
surfaces `global_pricing|billing_overview|stripe_return`; providers
`stripe|pingxx|alipay|wechatpay|manual|other`; payment channels
`wx_pub_qr|alipay_qr|not_applicable`; intervals
`day|month|year|one_time|unknown`. Failure categories are
`checkout_request_failed`, `missing_order`, `missing_redirect`,
`payment_failed`, `redirect_failed`, `unexpected_status`, or `unsupported`.
Localized plan names, checkout URLs, and raw provider errors are excluded.

`confirmation_failed` is non-terminal: it means the existing product flow did
not confirm a terminal paid state. Analytics does not add retries, cache
refreshes, status branches, or user-visible messages. A later product-driven
retry may therefore emit the one terminal success for that order; it must not
emit an early failed result and a later successful result for the same
checkout.
`refunded` cannot transition back to `paid`, so the return page reports it as a
terminal failed result even when a stale return URL still contains `canceled=1`.
Confirmed paid and refunded terminal states consume the session-local Stripe
analytics marker. An explicit `canceled=1` return is recorded as a user
cancellation only after the original product synchronization runs and observes
a non-paid, non-refunded state; the event omits the unverified query order from
analytics.

## Course creation

- Business question: which creation path is selected and does the accepted
  manual operation or AI handoff complete?
- Metric definition: manual API success/failure counts per accepted attempt;
  AI `success` means only that the external handoff link was accepted, not that
  a course was later created. These two path results must not be combined into
  one course-created metric.
- Trigger: manual attempt immediately before the create API and result after its
  terminal response; cancel on explicit modal close; AI attempt/result together
  when the external handoff click is accepted.
- Population: authenticated teachers on the admin course list.
- Deduplication: none beyond the existing UI behavior. Every accepted submit is
  counted independently, and analytics never suppresses a create request.
- Consumer: course-creation path adoption and manual reliability analysis.
- Replacement: delete the `creator_shifu_create_click` and
  `creator_shifu_create_success` producers and consumers. Course-creation
  queries use attempt/result/cancel.

| Event                           | Fields                                                                                                                                   |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `creator_course_create_attempt` | `creation_path` is `manual` or `ai_assistant`                                                                                            |
| `creator_course_create_result`  | `creation_path`; `outcome` is `success` or `failed`; successful manual only: `shifu_bid`; failed only: `failure_category=request_failed` |
| `creator_course_create_cancel`  | `creation_path=manual`                                                                                                                   |

## Learner profile assistant

- Business question: do eligible learners choose the AI-assistant collection
  route, and do accepted assistant transformations complete?
- Metric definition: raw route choices and assistant terminal results per
  attempt, grouped by source and presentation. No attempt ID exists, so only
  aggregate ratios are valid.
- Trigger: route event on an explicit assistant/back choice; attempt only when
  an assistant SSE run actually starts; result once on valid assistant output or
  a bounded terminal stream/runtime/session/missing-result failure.
- Population: learners for whom the profile collection conversation and
  assistant route are rendered; hidden/unavailable assistant controls are
  excluded.
- Deduplication: one event per accepted route action and one terminal result per
  real run attempt; queued work does not emit an early attempt.
- Consumer: profile collection route adoption and assistant reliability.
- Contract relationship: this is an additive event family with no predecessor
  alias.

| Event                                     | Fields and allowed values                                                                                                                                                  |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `learner_profile_collection_route_chosen` | `source` is `guided` or `settings`; `presentation` is `blocking` or `hidden`; `route` is `guided_questions` or `ai_assistant`                                              |
| `learner_profile_assistant_attempt`       | `source`, `presentation`                                                                                                                                                   |
| `learner_profile_assistant_result`        | `source`, `presentation`, `outcome` is `success` or `failed`; failed only: `failure_category` is `stream_failed`, `runtime_failed`, `session_expired`, or `missing_result` |

Prompts, answers, learner profile content, nickname, generated drafts, session
IDs, and raw errors are excluded.

## Learning-mode selection

- Business question: which real learner mode transitions are accepted and from
  which switch surface?
- Metric definition: raw accepted transitions grouped by from/to/source over a
  named period.
- Trigger: immediately after the control accepts a different-mode selection and
  before URL/store mutation.
- Population: learners shown an enabled read/listen/classroom option; preview,
  unavailable modes, and initial local-storage restoration are excluded.
- Deduplication: selecting the already-active mode emits nothing; each real
  later transition counts once.
- Consumer: learning-mode adoption analysis.
- Contract relationship: `learner_learning_mode_select` and
  `learner_last_learning_mode` are independent semantic contracts, not aliases
  or migration writes.

`learner_learning_mode_select` fields are
`from_learning_mode=read|listen|classroom`,
`to_learning_mode=read|listen|classroom`, and
`source=mobile_switch|desktop_switch`.

`learner_last_learning_mode` measures initialization: it is emitted once when a
live learner route restores a stored course-scoped mode, with `shifu_bid`,
optional `outline_bid`, and `learning_mode=read|listen|classroom`. Preview and
missing stored preference are excluded. Capability resolution must confirm that
the stored mode remains available; a fallback to `read` after TTS or classroom
access checks emits no restoration event. An explicit selection made while a
capability check is pending also excludes the initial stored preference from
restoration reporting. It remains because that question is different from an
explicit mode-selection transition.

## Learner run start

`learner_run_start` is emitted immediately before a live learner SSE run starts
and carries only `shifu_bid`, `outline_bid`, and
`learning_mode=read|listen`. Each accepted run invocation counts once; React
renders emit nothing.

`learner_lesson_start` is a separate semantic contract, not a predecessor or
alias for `learner_run_start`. It records initialization of a live lesson with
no existing content and carries only `shifu_bid` and `outline_bid`.
`learner_run_start` measures every accepted SSE invocation, including later
continuations. Teacher preview is excluded from both contracts.

## Removed Umami diagnostics

`learner_course_info_fetch_error`, `learner_course_404_redirect`, and
`learner_course_info_non_404_error` were removed. Request failures, redirects,
and raw diagnostics belong in application logs/metrics, not product analytics.
Their old pathname, user-agent, and arbitrary error dimensions must not be
recreated in another Umami event.

## Verification and production activation

Focused tests cover exact names and payloads, forbidden-field absence, trigger
timing, success/failure/cancel/pending outcomes, deduplication, SPA route
sanitation, identity replacement, bounded queueing, and fail-open behavior.

Before using these contracts in production reporting:

1. deploy producers and transport together, keeping
   `data-auto-track="false"` so only the reviewed manual identify, pageview,
   and event producers can send analytics;
2. remove every deleted producer and every dashboard, alert, export, or ad-hoc
   consumer of its old name in the same release;
3. do not query or backfill historical rows under deleted names; start each
   canonical series at deployment; and
4. verify representative canonical events and their production consumers in
   each production Umami site without copying sensitive payloads into tickets
   or logs.

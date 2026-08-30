# Frontend Product Analytics

This reference is the canonical contract for new or changed Cook Web Umami
product-behavior events. Existing events are grandfathered only while they
remain untouched. Legacy behavior described at the end of this document is
debt to migrate, not a precedent for new code.

## Scope and System Boundaries

Use Umami to answer product-behavior questions such as whether a user saw,
started, completed, cancelled, or failed an interaction. An Umami event is a
versioned data contract between its producer and every query, dashboard,
experiment, or report that consumes it.

Umami is not the source of truth for:

- model and prompt traces, which belong in Langfuse;
- billing, credit consumption, or financial records;
- authorization, entitlements, compliance, or audit records; or
- application logs, errors, metrics, and operational traces.

Analytics must be fail-open. Missing configuration, a blocked script, an
identify failure, or an event delivery failure must never block, delay, or
change the user workflow. Product behavior must not depend on an event being
accepted by Umami.

This document is intentionally not a registry of all events. It defines the
contract required whenever a Cook Web Umami event is added or changed.

## Contract-First Changes

Write or update the event contract before changing a producer. Treat changes to
the event name, meaning, trigger, measured population, count unit,
deduplication, payload fields, or enum values as contract changes. Coordinate
the producer, known consumers, documentation, and tests in the same change or
in an explicitly staged compatibility migration.

Adding a field is not automatically harmless: queries may group by it, its
cardinality may raise cost, and its contents may change the privacy posture.
Removing or renaming an event or field requires identifying consumers and
defining how historical and new data will coexist. Do not silently reuse an
old event name for a new meaning.

## New UI Feature Requirement

Product analytics is part of the definition of done for every new user-facing
Cook Web capability or interaction path. The same feature change must include:

- a documented new or extended event family with a business question and
  metric definition;
- at least one decision-relevant signal for meaningful feature exposure,
  accepted use, or a meaningful outcome;
- the producer implementation through the shared tracking path; and
- focused tests for the trigger, eligible population, deduplication, payload,
  prohibited fields, and failure isolation.

Add an exposure event when the metric requires an eligible-view denominator.
Use separate attempt and terminal-result events when an asynchronous workflow
cannot be measured accurately with one signal. Do not create render-count or
incidental-click noise merely to satisfy this requirement; the event must
represent the feature's documented adoption or outcome question.

An existing generic SPA pageview does not satisfy this requirement unless
entering that route is itself the documented feature-adoption signal.
An existing event family may satisfy the requirement only when its contract is
explicitly extended in the same change and remains semantically accurate for
its producers and consumers.

A new action, control, route, workflow, interaction mode, or user-visible state
transition counts as new functionality. So does any new user-observable
invocation path, including one introduced for keyboard, screen-reader, or other
accessibility use. Pure visual styling, copy-only edits, performance-only work,
test-only changes, and behavior-preserving refactors do not require a new
event. If such work changes behavior already covered by analytics, update that
existing contract. If a privacy-safe, decision-relevant contract cannot be
designed, do not ship the new capability until the product and privacy decision
is resolved.

## Contract Template

Every new event family, and every changed existing event, must document the
following information in its product spec or ExecPlan. Keep the contract close
to the feature decision; link back to this reference rather than copying these
rules.

```markdown
### <event family>

- Business question: <the decision this data will support>
- Metric definition: <numerator, denominator, time window, and distinctness>
- Event name(s): <stable snake_case names>
- Actor and surface: <who can emit it and the fixed surface enum>
- Trigger: <the exact state transition or user action>
- Population: <guest/member/teacher coverage and explicit exclusions>
- Count unit: <event, attempt, user, session, course, or another named unit>
- Deduplication: <key, time or lifecycle boundary, and storage mechanism>
- Correlation: <required stable identifiers and what they may be joined to>
- Consumers: <queries, dashboards, reports, experiments, or owners>
- Compatibility: <additive, dual-write, rename, backfill, or new version>
- Verification: <producer, exclusion, deduplication, privacy, and consumer tests>

| Field | Type | Allowed values | Cardinality | Privacy class | Why required |
| --- | --- | --- | --- | --- | --- |
| `<field>` | string/number/boolean | enum or validation rule | low/high | non-personal/pseudonymous | <metric or join need> |
```

The business question and metric definition are required. “Track usage” is not
a metric definition. State whether the metric counts raw events, distinct
users, distinct sessions, or distinct business objects, and state the time
window. If click and result events cannot be correlated one to one, document
that limitation rather than presenting their aggregate ratio as an exact
conversion rate.

## Event Names and Semantics

- Use stable lowercase `snake_case` names. Prefer
  `<actor>_<object>_<action-or-state>` when one actor owns the event. A shared
  event may omit the actor when a fixed `surface` field distinguishes the
  contexts clearly.
- Keep dynamic IDs, labels, locales, titles, and state in reviewed payload
  fields. Never interpolate them into an event name.
- Name a state that actually occurred. Emit from an event handler or effect
  tied to the documented transition, never during React render.
- A `click` records one accepted user interaction after re-entry or disabled
  guards. An `attempt` records the point at which the product starts an
  operation after local validation. A `success` records confirmed completion.
  A `failed` result records a terminal failure. A `cancelled` result records an
  explicit user cancellation and is not a failure.
- If an interaction needs both intent and outcome measurement, use separate
  intent and terminal-result events. Emit at most one terminal result for each
  accepted attempt.
- Define whether guests are included, whether teacher or learner preview is
  included, and whether internal/test traffic is excluded. Do not let the
  current rendering location answer these questions implicitly.
- Define the deduplication boundary even when the answer is “none.” For
  visibility events, state whether deduplication is per mount, route visit,
  browser session, user, or persisted lifecycle. For actions, prevent render,
  retry, and double-click behavior from inflating counts unless repeat actions
  are the intended count unit.

Enum values are stable API values, not localized display text. Use short
English `snake_case` values and document the complete allowed set. Adding,
removing, or changing an enum value is a contract change.

## Payload Shape and Cardinality

Event payloads must be explicit, flat records of scalar strings, finite
numbers, and booleans.

- Spell out every field at the call site or in a feature-owned typed helper.
  Do not spread a form, store, API response, configuration object, error, or
  arbitrary metadata object into analytics.
- Use stable `snake_case` field names. Keep enum fields low-cardinality and
  bounded by the documented allowed values.
- Add a high-cardinality stable machine identifier only when a named metric,
  join, or deduplication rule requires it. Examples include a course bid or a
  workflow/session ID. Do not add a duplicate user identifier when the shared
  tracking context already supplies identity.
- Send durations as finite numeric values with the unit in the field name,
  such as `duration_ms`. Send timestamps only when the event's metric requires
  a business timestamp that differs from Umami's ingestion time; serialize it
  as UTC ISO-8601 with a trailing `Z`.
- Map failures to a reviewed, bounded error category or code. Never send an
  exception message, stack, response body, or arbitrary provider error.
- Do not rely on field order, automatic string conversion, truncation, or the
  transport's fallback serialization as part of an event contract.

The shared transport currently caps event names at 50 characters, keys at 64
characters, string values at 240 characters, payloads at 30 fields and 1,024
JSON characters, and pageview URL/referrer values at 500 characters. These
limits are delivery safeguards, not authoring targets. Silent truncation or
dropped fields can corrupt a metric, and sanitation does not make prohibited
data safe to collect.

## Privacy Default: Deny

Do not collect a field unless the contract explains why it is necessary. New or
changed application-event payloads and identify session metadata must not
include:

- nickname, name, email address, phone number, or other direct identifiers;
- learner profile/background content or personalization answers;
- prompts, model input/output, chat content, or free-form user text;
- course, lesson, chapter, document, or conversation titles and descriptions;
- discount/coupon codes, credentials, secrets, authorization values, or tokens;
- raw errors, exception messages, stack traces, or provider response bodies; or
- complete URLs, query strings, fragments, or referrers.

Necessary stable machine IDs, booleans, finite numbers, durations, and reviewed
low-cardinality enums are allowed when declared in the contract. Stable machine
IDs remain pseudonymous data: minimize them, scope access appropriately, and do
not expose them in user-facing reports.

The shared identify path is not an exception to this privacy rule. Any new or
changed identity field must have a documented analytics need and explicit
privacy review. Prefer the one stable pseudonymous distinct ID; do not attach
direct identifiers, free text, or duplicated identity without a defined metric.

Hashing, encoding, or truncating a prohibited value does not make it approved.
If a URL-derived distinction is necessary, define a bounded route or source
enum instead of sending the URL. Pageview URL handling is transport-owned and
is not permission for application events to add URL or referrer fields. New or
changed pageview handling must remove query strings, fragments, credentials,
and sensitive path values before delivery; a complete referrer requires its own
documented contract and privacy review.

## Transport Invariants

- Product code emits events through `useTracking` or a shared, reviewed
  tracking helper. It must not call `window.umami`, `umami.track`, or
  `umami.identify` directly.
- `UmamiLoader` is the single owner of SPA pageviews. Umami auto-tracking stays
  disabled, route changes are deduplicated, and feature components do not emit
  pageviews.
- Preserve the identify → queue → drain order. Pageviews and events that occur
  before Umami and user identity are ready are queued with their captured
  context, then drained after identify completes.
- Preserve transport-level name, key, value, field-count, JSON-size, URL, and
  referrer sanitation. Feature code must still satisfy the stricter contract
  before sanitation.
- Tracking calls and identify/pageview work remain fail-open. Callers do not
  await analytics before navigation, native browser actions, or user-visible
  success/failure handling.
- Do not emit during render. Use the true user handler or a guarded effect for
  a documented visibility/state transition.

## Positive Example: Course Sharing

`course_share_click` and `course_share_result` demonstrate a small event family
with stable names, explicit fields, terminal outcomes, and no course content.
They are an example, not the start of an event registry.

### Business and metric contract

- Business question: which eligible share surfaces lead users to initiate a
  share, and which method/outcome completes the attempt?
- Actors and population: teachers in the authoring header and eligible
  learners, including guests when the learner share control is rendered.
  Learner preview is excluded. Teacher drafts are included because sharing is
  independent of publication.
- Count unit: one accepted share-button interaction. Concurrent re-entry is
  blocked; later deliberate interactions count again. There is no persisted
  cross-session deduplication.
- Metric limitation: `shifu_bid` supports aggregate grouping by course, but
  there is no per-attempt correlation ID. Click/result counts must not be
  presented as exact row-level joins.
- Consumer: aggregate course-sharing adoption and outcome analysis.

### Events and feature-owned payloads

| Event | Trigger | Feature-owned fields |
| --- | --- | --- |
| `course_share_click` | After the re-entry guard accepts the deliberate click and before URL resolution/native sharing | `shifu_bid`, `surface` |
| `course_share_result` | Once after the accepted interaction reaches a terminal outcome | `shifu_bid`, `surface`, `method`, `outcome` |

| Field | Type | Allowed values | Cardinality | Privacy class | Why required |
| --- | --- | --- | --- | --- | --- |
| `shifu_bid` | string | stable course bid | high | pseudonymous machine ID | group adoption by course |
| `surface` | string | `teacher_header`, `learner_desktop_header`, `learner_mobile_header`, `learner_mobile_fullscreen` | low | non-personal enum | compare entry points and infer actor context |
| `method` | string | `native`, `clipboard` | low | non-personal enum | compare completion paths |
| `outcome` | string | `success`, `failed`, `cancelled` | low | non-personal enum | measure terminal result without raw errors |

This table lists the fields owned by the sharing producers, not every field in
the payload currently delivered to Umami. The shared `useTracking` helper also
adds `user_type`, `user_id`, `device`, and the grandfathered localized
`timeStamp`. Those helper-added fields are inherited transport behavior, not a
positive part of this example and not approved as dependencies for new
consumers.

Every event contract must inventory both layers: the feature-owned allowlist
and the complete payload after shared-helper enrichment. Label inherited
legacy fields explicitly, audit them against the privacy rules, and do not
claim that the final schema is fully compliant until the relevant transport
debt is migrated. Removing or changing helper-added fields requires the same
compatibility review as any other consumed schema change.

The existing producer tests assert the exact feature-owned fields for native
success, clipboard success/failure, cancellation, and invalid input. They also
assert that course title, description, and URL never enter the producer
payload. Because those tests mock `useTracking`, they do not prove the final
helper-enriched payload; that missing low-level coverage remains tracked as
legacy debt.

## Verification

For every new or changed event, add focused tests that cover:

- exact event names, trigger order, and feature-owned payload keys, types, and
  enum values;
- every terminal result, including cancellation and failure when applicable;
- guest/member/teacher and preview inclusion or exclusion;
- re-render, retry, double-click, route-change, and deduplication behavior;
- absence of prohibited or incidental fields; and
- consumer calculations or fixtures when an existing query/dashboard changes.

The contract review must also record the complete helper-enriched payload,
including any explicitly grandfathered transport fields. A feature-level test
that mocks `useTracking` verifies only the producer boundary and must not be
presented as proof of the final delivered schema.

When changing the shared transport, also cover identify-before-drain ordering,
events emitted before script readiness, SPA pageview deduplication, sanitation
limits, and fail-open behavior. Local producer tests prove the code contract;
they do not prove that a production Umami site, filter, or dashboard is current.
Verify deployed analytics separately before reporting live coverage.

## Grandfathered Legacy Debt

The following existing behavior is tracked as non-blocking migration debt in
`docs/QUALITY_SCORE.md`:

- dynamic event names at legacy call sites;
- free-text or object-derived payload values;
- the localized `timeStamp` field added by `useTracking`;
- pageviews that include query strings;
- identify session metadata such as nickname, user state, and language; and
- missing focused tests for the low-level tracking transport.

These behaviors are not approved examples. New code must not copy them. When a
legacy event or the shared transport is changed, apply this contract and use a
dedicated compatibility migration when historical consumers or event meaning
would otherwise break.

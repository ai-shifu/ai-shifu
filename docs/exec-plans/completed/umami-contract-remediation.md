# Remediate Cook Web Umami contracts

## Purpose / Big Picture

Cook Web previously sent several Umami payloads that could contain
user-authored content, provider credentials, complete URLs, or direct identity
metadata. Important user journeys also had ambiguous click-only event names.
This remediation makes the shared transport privacy-safe, replaces incorrect
event contracts directly, and adds focused attempt/result coverage.

Umami remains best-effort and observational. No event, analytics callback, or
attribution helper controls payment, billing, authentication, navigation,
course creation, or another product workflow. Incorrect predecessor events are
deleted instead of dual-written, and the generic course visit event has no
replacement or analytics-backed business metric.

## Progress

- [x] 2026-08-30 11:15 CST: Audited production producers, shared transport,
      known consumers, payload privacy, and focused tests.
- [x] 2026-08-30 12:10 CST: Hardened identity queueing, manual pageviews, route
      sanitation, and flat-scalar payload delivery.
- [x] 2026-08-30 12:20 CST: Replaced high-risk publish, login, learner payment,
      creator billing, learning-mode, course-creation, profile-assistant, and
      authoring event contracts.
- [x] 2026-08-30 12:25 CST: Deleted the legacy generic `visit` producer without
      adding a replacement event, database model, synchronization path, or
      course metric.
- [x] 2026-08-31 05:18 CST: Re-audited the entire PR after review follow-ups
      exposed unrelated product-flow changes.
- [x] 2026-08-31 06:00 CST: Restored the `main` payment, billing,
      course-creation, learning-mode, and Stripe-return control flow; retained
      only fail-open analytics observation and context propagation.
- [x] 2026-08-31 06:20 CST: Passed 8 scope-sensitive suites / 113 tests, the
      then-current full frontend run, TypeScript, full frontend lint with no
      errors, and Prettier after the initial scope correction.
- [x] 2026-08-31 07:05 CST: After the final fail-open fixes and removal of the
      superseded payment-hook test, passed all 211 frontend suites / 1,884
      tests.
- [x] 2026-08-31 07:10 CST: Passed the repository harness, architecture
      boundaries, developer-tool verification, and the full pre-commit gate.

## Surprises & Discoveries

- The course settings event previously spread provider configuration that can
  include Dify and Coze API keys and Volcengine credentials. Truncation is not a
  privacy boundary; explicit allowlists are required.
- Automatic Umami pageviews being disabled did not disable every automatic
  browser listener. The reviewed manual producer therefore owns sanitized
  pathname pageviews and disables automatic tracking entirely.
- Identity replacement can race with queued event delivery. Losing
  best-effort events is safer than attributing one account's events to another.
- Review fixes had expanded into payment polling generations and deadlines,
  billing cache refreshes, duplicate course-create suppression, and new UI
  branches. Those changes were not required to emit Umami events and were
  removed.
- Precise payment-channel attribution sometimes requires call-scoped provider
  evidence. Passing that evidence is safe only when it never determines
  whether synchronization, navigation, a toast, or another business action
  runs.

## Decision Log

- Decision: analytics may observe existing business state but may not create or
  redefine that state.
  Rationale: Umami is best-effort telemetry and cannot be a correctness
  dependency.
- Decision: directly replace incorrect event names and schemas without
  compatibility dual-writing or historical backfill.
  Rationale: continuing the old contract would extend ambiguous and unsafe
  collection.
- Decision: remove the generic course visit event without replacement.
  Rationale: no current product decision requires this metric, and rebuilding
  it would preserve dead operational surface.
- Decision: use explicit payload allowlists of stable machine IDs, finite
  numbers, booleans, and bounded enums.
  Rationale: hashing or truncating free text, secrets, or identifiers does not
  make them safe analytics fields.
- Decision: accept less precise attribution when greater precision would
  require changing product behavior.
  Rationale: telemetry quality does not justify workflow changes.

## Outcomes & Retrospective

The shared transport now establishes pseudonymous identity separately, emits
sanitized manual pageviews, bounds pending queues, drops unsupported payload
types, and isolates tracking failures. Migrated producers no longer send
prompts, titles, descriptions, coupon values, credentials, complete URLs,
User-Agent strings, raw errors, or provider responses.

The remediation deletes generic `visit`, `creator_publish_click`,
`creator_publish_confirm`, `learner_login_success`, `learner_pay_cancel`,
`creator_billing_checkout_click`, `creator_shifu_create_click`, and
`creator_shifu_create_success`. Generic `visit` has no replacement. The other
families use their versioned attempt/result/status contracts documented in
`docs/product-specs/cook-web-umami-contract-remediation.md`.

Payment and billing analytics observe the existing product flow. They do not
add polling deadlines, synchronization requests, retries, cache refreshes,
terminal-state guards, redirects, or user-visible messages. Course-creation
analytics does not suppress duplicate requests, and learning-mode analytics
does not prevent the existing URL/store update when the current option is
selected.

Historical rows under deleted names are not read or backfilled. Canonical
series start at deployment, so initial rolling windows may be partial. No live
Umami dashboard or production deployment is modified by this repository-only
change.

Final frontend validation passed 211 Jest suites / 1,884 tests. TypeScript and
frontend lint completed without errors; the lint run retains existing
repository warnings. The final focused payment and Stripe-return rerun passed
3 suites / 34 tests before the repository-wide run. The repository harness,
architecture-boundary check, developer-tool verification, and full pre-commit
gate also passed.

## Context and Orientation

The canonical analytics rules live in
`docs/references/frontend-product-analytics.md`. Shared producer enrichment is
in `src/cook-web/src/c-common/hooks/useTracking.ts`; raw Umami identity,
queueing, pageview sanitation, and event delivery are in
`src/cook-web/src/c-common/tools/tracking.ts`; SPA pageview ownership is in
`src/cook-web/src/components/analytics/UmamiLoader.tsx`.

Feature-owned typed builders live near their producers or under
`src/cook-web/src/lib/`. High-risk producers include learner payment, creator
billing, publishing, authentication, course creation, learning-mode selection,
profile onboarding, and authoring settings.

## Plan of Work

First, make the centralized transport privacy-safe and race-safe. Own one
normalized manual pageview per pathname transition, keep identity replacement
generation-aware, and accept only reviewed flat scalar event data.

Second, migrate high-risk producers to explicit allowlists and versioned event
families. Delete unsafe fields and predecessor names rather than preserving
compatibility writes.

Third, verify every producer is fail-open. Compare touched business modules to
`origin/main` and remove any branch, guard, retry, cache mutation, toast,
navigation, or request change introduced solely to improve analytics.

Finally, update canonical documentation and focused regression tests, then run
frontend and repository verification.

## Concrete Steps

1. Test URL normalization, scalar sanitation, identity replacement, queue
   draining, and fail-open delivery.
2. Update `tracking.ts`, `useTracking.ts`, and `UmamiLoader.tsx` to satisfy that
   contract.
3. Replace broad producer payloads with explicit allowlists and delete unsafe
   predecessor events.
4. Add focused attempt/result/status builders and producer tests for the named
   product decisions.
5. Delete the legacy generic visit producer and retired course-visit plan.
6. Compare production hunks to `origin/main`, restore unrelated product
   behavior, and remove tests that attempted to make those changes contractual.
7. Run focused tests, the full frontend suite, type checking, lint, Prettier,
   repository harness, architecture boundaries, developer-tool verification,
   and the pre-commit gate.

## Validation and Acceptance

The change is accepted when:

- changed payloads cannot contain free text, credentials, raw errors, complete
  URLs, or unbounded identity metadata;
- route and identity races cannot leak one account's event into another;
- tracking throws or rejects without changing the business result;
- payment, billing, course creation, learning mode, and Stripe-return behavior
  match `origin/main` apart from analytics-only observation;
- the generic visit producer and any Umami-backed course metric are absent;
- focused and repository-wide checks pass; and
- an independent diff audit finds no remaining non-analytics product change.

## Idempotence and Recovery

Tracking calls are safe to lose and safe to retry from the business workflow's
perspective. Tests reset module-level transport state. Deleted event rows are
not replayed; recovery begins with the next accepted action under the canonical
producer. If an analytics helper fails, the original product operation
continues unchanged.

## Interfaces and Dependencies

- Umami browser API: centralized `identify` and `track` calls only.
- Cook Web `useTracking`: feature-facing best-effort event boundary.
- Existing product APIs and state machines remain unchanged.
- No new backend API, database schema, analytics reader, runtime dependency, or
  course-visit persistence path is introduced.

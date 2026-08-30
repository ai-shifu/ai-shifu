# Remediate Cook Web Umami contracts

## Purpose / Big Picture

Before this remediation, Cook Web sent several Umami payloads that could contain
user-authored content, provider credentials, complete URLs, and direct identity
metadata. Several important asynchronous workflows also recorded only a click or
an intermediate state, so product owners cannot distinguish accepted attempts
from terminal outcomes. This plan hardens the shared transport, migrates the
highest-risk producers, and restores decision-relevant funnel coverage without
letting analytics failure change a business result. Where an asynchronous
workflow already exposes a terminal state, its UI and analytics now agree on
the same observed business result.

After this work, analytics remains best-effort and fail-open. New and migrated
events have stable names, explicit flat scalar payloads, documented populations
and outcomes, and focused regression tests. Incorrect predecessor events and
their consumers are deleted instead of dual-written.

## Progress

- [x] 2026-08-30 11:15 CST: Re-audited production tracking invocation sites,
      shared transport behavior, product specifications, known consumers, and
      focused tests.
- [x] 2026-08-30 12:10 CST: Hardened identify, bounded queueing, manual
      pageviews, route sanitation, and the final flat-scalar payload shape.
- [x] 2026-08-30 12:15 CST: Removed prohibited payload fields from the migrated
      course authoring, navigation, reset, contact, login, payment, billing,
      publishing, profile-assistant, and course-creation producers.
- [x] 2026-08-30 12:20 CST: Added accepted-attempt and terminal-result contracts for revenue,
      publishing, authentication, onboarding-assistant, learning-mode, and course
      creation paths.
- [x] 2026-08-30 12:25 CST: Removed the legacy generic `visit` producer without
      adding a replacement event or analytics-backed business metric.
- [x] 2026-08-30 21:40 CST: Rebuilt the change from `origin/main` commit
      `33b3f836e` with a clean frontend-only analytics scope.
- [x] 2026-08-30 22:12 CST: Added focused producer and transport coverage and
      passed the initial full frontend suite: 211 Jest suites / 1,849 tests, plus
      TypeScript, frontend lint, Prettier, repository harness, architecture
      boundaries, dev-tool verification, and the full Lefthook pre-commit gate.
- [x] 2026-08-30 22:14 CST: Completed independent frontend/static and
      backend/consumer diff audits.
- [x] 2026-08-30 22:25 CST: A final payload audit found and fixed unverified
      return-page order IDs and an unbounded learner currency value before
      merge. The pre-rebase full frontend suite passed: 211 Jest suites / 1,855
      tests,
      with no remaining P0-P2 audit finding.
- [x] 2026-08-30 22:29 CST: Rebased the final two-commit change onto
      `origin/main` commit `e9b57d20d`, preserving the newly merged account
      session analytics contracts. The final full frontend suite passed: 212
      Jest suites / 1,880 tests.
- [x] 2026-08-30 22:29 CST: Moved this plan to
      `docs/exec-plans/completed/` after all acceptance checks passed.
- [x] 2026-08-30 23:54 CST: Addressed billing review feedback by keeping
      recoverable synchronization states non-terminal. Focused billing checks
      passed 2 Jest suites / 36 tests, followed by the full frontend suite at
      212 Jest suites / 1,882 tests, TypeScript, focused lint, and Prettier.
- [x] 2026-08-31 00:04 CST: Addressed direct-payment attribution review
      feedback by carrying call-scoped Stripe and WeChat confirmation evidence
      into the paid analytics callback without changing generic polling.
      Focused payment checks passed 2 Jest suites / 37 tests, followed by the
      full frontend suite at 212 Jest suites / 1,886 tests, TypeScript, focused
      lint, and Prettier.
- [x] 2026-08-31 00:29 CST: Closed follow-up attribution races by retaining
      order-, lifecycle-, and attempt-scoped Stripe and WeChat confirmation
      evidence until a paid observation or analytics reset. Focused checks
      passed 4 Jest suites / 54 tests, followed by the full frontend suite at
      212 Jest suites / 1,888 tests, TypeScript, full frontend lint with no
      errors, Prettier, repository harness, architecture boundaries, dev-tool
      verification, and the full Lefthook pre-commit gate.
- [x] 2026-08-31 00:42 CST: Kept learner payment modal dismissal non-terminal
      on desktop and mobile while preserving provider-confirmed cancellation.
      Focused payment checks passed 4 Jest suites / 54 tests, followed by the
      full frontend suite at 212 Jest suites / 1,888 tests, TypeScript, focused
      lint, and Prettier.
- [x] 2026-08-31 00:52 CST: Addressed post-push learner checkout feedback by
      keeping malformed payment snapshots fail-closed, classifying explicit
      Stripe cancellation separately from processing and provider failure, and
      isolating Stripe return query fixtures. Focused checks passed 5 Jest
      suites / 67 tests, followed by the full frontend suite at 212 Jest suites
      / 1,896 tests, TypeScript, focused lint, Prettier, repository harness,
      architecture boundaries, and the full Lefthook pre-commit gate.
- [x] 2026-08-31 01:12 CST: Preserved the paid terminal event when an in-flight
      Stripe synchronization is superseded by a newer same-channel attempt in
      the same order and modal lifecycle, while keeping other stale callbacks
      ineligible. Focused checks passed 2 Jest suites / 42 tests, followed by
      the full frontend suite at 212 Jest suites / 1,899 tests, TypeScript,
      focused lint, Prettier, repository harness, architecture boundaries, and
      the full Lefthook pre-commit gate, plus independent code and contract
      reviews.

## Surprises & Discoveries

- The course settings event spreads `ask_provider_config`; supported provider
  schemas include Dify and Coze API keys plus Volcengine AK/SK values. Transport
  truncation can drop later fields but cannot prevent a short credential from
  being delivered.
- The original identify implementation could finish an older identify request,
  drain queued events under that identity, and clear a newer pending identity.
- Initial focused tests encoded prohibited URL payloads. They were replaced
  because passing tests alone were not evidence of contract compliance.
- Umami's `data-auto-pageview="false"` disables only automatic pageviews; it
  can retain automatic click and history listeners. The privacy-controlled
  manual producer therefore requires `data-auto-track="false"`.
- A queued event did not carry an identity generation. During an in-flight
  account replacement, the old queue could be drained under the new account;
  the former test expectation accidentally preserved this attribution bug.
- Payment timeout state previously became terminal before the deadline's final
  provider query. A paid response at that boundary could be reported as failed
  and then have its success suppressed.
- Stripe return pages initially treated query-provided order IDs as analytics
  correlation IDs even when product APIs had not confirmed them, and learner
  modal currency accepted an unbounded runtime string. Final payload review
  required omitting unverified IDs and bounding currency to `CNY|USD|other`.
- Review also exposed that the learner Stripe cancel return was classified as
  pending analytics. The producer now records an attempt with
  `outcome=cancelled` after the product API confirms the order, without changing
  the pending order UI.
- The legacy `createOutline` producer read `parent_bid` after `replaceOutline`
  mutated its placeholder. Producer-level tests exposed the resulting empty
  parent ID and led to capturing it before mutation.

## Decision Log

- Decision: Keep analytics fully fail-open, and classify terminal events from
  the same observed result that drives the existing success, failure, retry, or
  timeout UI.
  Rationale: Umami is best-effort telemetry and must not control payment,
  publishing, login, navigation, or course authoring. Tightening guards and
  terminal-state handling prevents duplicate or contradictory UI and analytics
  outcomes.
- Decision: Remove direct identity metadata and keep only the stable
  pseudonymous distinct ID in the centralized identify call.
  Rationale: Nicknames are direct identifiers; user state and language have no
  current documented consumer.
- Decision: Directly replace incorrectly defined event contracts. Delete old
  producers and consumers in the same release; do not dual-write, merge, fall
  back to, or backfill their historical rows.
  Rationale: the old names encode incorrect semantics or payload contracts, so
  preserving them would extend rather than reduce analytics ambiguity.
- Decision: Retire the planned learner-entry metric and its active ExecPlan.
  Do not add a replacement event, database model, synchronization job, or
  operator metric.
  Rationale: the product no longer requires this metric, so rebuilding it would
  preserve unnecessary collection and dead operational surface.
- Decision: Do not invent events for every button. Migrate only paths with a
  named adoption, conversion, or reliability decision in this plan.
- Decision: Keep Umami automatic tracking fully disabled and own one sanitized
  pageview per pathname transition in `UmamiLoader`.
  Rationale: Automatic click/history context is not covered by reviewed
  producer allowlists and can restore sensitive browser context.
- Decision: Drop calls queued for a pending identity when that identity is
  replaced, and require a working `identify` capability before draining.
  Rationale: Losing best-effort telemetry during an identity race is preferable
  to attributing one account's activity to another.
- Decision: Treat learner payment pending/confirmation failures as non-success
  status where the provider can still settle. At the polling deadline, perform
  the final query and emit one non-terminal pending status whenever payment is
  not confirmed, including when that lookup fails or returns no snapshot.
  Rationale: Intermediate uncertainty must not create false success or
  duplicate failure-then-success terminal outcomes for one accepted attempt.

## Outcomes & Retrospective

The shared transport now delivers only reviewed flat scalar application data,
sanitized route context, and a separately established pseudonymous identity.
It is bounded, fail-open, race-safe across identity replacement, and manual
pageview-only. The migrated producer families cover course/outline settings and
creation, editor previews, learner navigation/reset/run/mode selection,
publishing, password/SMS/Google login, learner payment, creator billing,
course creation, support clicks, and profile-assistant routing.

The remediation deletes generic `visit`,
`creator_publish_click`, `creator_publish_confirm`, `learner_login_success`,
`learner_pay_cancel`, `creator_billing_checkout_click`,
`creator_shifu_create_click`, and `creator_shifu_create_success` from producers
and consumers. Generic `visit` has no replacement. The other canonical
replacements are `creator_publish_attempt`, `creator_publish_result`, `learner_login_attempt`,
`learner_login_result`, `learner_pay_modal_view`,
`learner_pay_modal_dismiss`, `learner_payment_attempt`,
`learner_payment_result`, `learner_payment_status`,
`creator_billing_checkout_attempt`, `creator_billing_checkout_result`,
`creator_billing_checkout_status`, `creator_course_create_attempt`,
`creator_course_create_result`, and `creator_course_create_cancel`.
`learner_last_learning_mode` and `learner_lesson_start` remain as independent
semantic contracts, not predecessor aliases.

The related workflow fixes keep terminal state monotonic: polling performs its
final provider check before timing out and reports unresolved confirmation as
pending, successful billing synchronization is shown as completed, synchronous
card-confirmation failures remain visible, and duplicate course-creation
submissions are rejected while one request is active. Learner payment attempts
retain their distinct unresolved channels. A product-confirmed paid result uses
direct Stripe or WeChat confirmation evidence only when one eligible channel
remains for that order. If a newer same-channel attempt supersedes an in-flight
confirmation in the current order and modal lifecycle, its paid result falls
back to generic attribution; callbacks from another order or lifecycle, or an
already-closed attempt, remain ineligible. Other explicit provider results close
only their matching channel, and a generic order-level result uses
`channel=other` instead of guessing when multiple channels remain unresolved.
Creator billing sync observations keep recoverable `failed`, `canceled`, and
`timeout` API states non-terminal so a later paid observation can emit the one
terminal success.

Validation completed with focused frontend checks and the final full 212 Jest
suites / 1,899 tests, TypeScript, frontend lint (no errors; existing repository
warnings), Prettier, the repository harness, architecture-boundary baseline,
dev-tool checks, the full Lefthook pre-commit gate, and independent
frontend/static diff reviews.

Historical rows under the deleted names are not read or backfilled, so canonical
series begin at production deployment and their first rolling windows may be
partial. Untouched event families still need full consumer inventories before
later contract changes. No live Umami site or dashboard was changed or verified
from this local implementation task.

## Context and Orientation

The canonical analytics rules live in
`docs/references/frontend-product-analytics.md`. Shared producer enrichment is
in `src/cook-web/src/c-common/hooks/useTracking.ts`; raw Umami identify,
queueing, pageview, sanitation, and event delivery are in
`src/cook-web/src/c-common/tools/tracking.ts`; SPA pageview ownership is in
`src/cook-web/src/components/analytics/UmamiLoader.tsx`.

High-risk producer call sites include course and outline settings under
`src/cook-web/src/components/`, learner payment under
`src/cook-web/src/app/c/[[...id]]/Components/Pay/`, creator billing under
`src/cook-web/src/components/billing/` and
`src/cook-web/src/app/admin/billing/`, publishing in
`src/cook-web/src/components/header/Header.tsx`, authentication in
`src/cook-web/src/components/auth/` and `src/cook-web/src/hooks/`, and course
creation in `src/cook-web/src/app/admin/page.tsx`.

## Plan of Work

First, make the centralized transport privacy-safe and race-safe. Pageview and
event URLs will use a bounded normalized route representation without query,
fragment, credentials, or sensitive dynamic values. Identify changes will be
serialized or generation-guarded so only the newest identity can mark the
transport ready and drain captured events. The final event schema will contain
only explicit scalar values; object and array fallback serialization will no
longer be an accepted producer path.

Second, migrate high-risk producer payloads to explicit allowlists. Remove
prompts, names, descriptions, coupon codes, URLs, User-Agent strings, provider
configuration, and other free-form content. Keep only required stable machine
IDs, finite numbers, booleans, and documented low-cardinality enums.

Third, define and implement event families for the workflows that require both
intent and outcome measurement. Each accepted attempt emits before the business
request; its producer invokes at most one terminal-result event, exactly once
when the application observes a terminal state, with a bounded outcome and
failure stage/category. Tracking failures are isolated from the workflow.
Existing consumed event names remain only when their meaning is unchanged;
otherwise delete their producers and consumers and use the new event family
from deployment forward.

Finally, update canonical documentation, consumer replacement notes, and focused
tests. Re-run the narrow suites first, then type checking, lint, architecture
checks, repository harness checks, and the pre-commit gate.

## Concrete Steps

1. Add low-level tests for URL normalization, scalar sanitation, identity
   replacement during an in-flight identify call, queue draining, and fail-open
   behavior.
2. Update `tracking.ts`, `useTracking.ts`, and `UmamiLoader.tsx` to satisfy the
   tested transport contract.
3. Replace broad or sensitive producer payloads with explicit allowlists and
   update their closest tests.
4. Add or migrate the creator billing, learner payment, publish, password
   login, onboarding-assistant route, learning-mode selection, and course
   creation event families. Document exact trigger, population, count unit,
   deduplication, payload schema, consumer, and replacement boundary.
5. Verify the aggregate diff contains no secrets, user-authored text, complete
   URLs, raw errors, or unstable display labels in changed event payloads.
6. Run the validation commands below, fix relevant failures, and record the
   outcome in this plan.

## Validation and Acceptance

The change is accepted when all of the following are observable:

- Course and outline settings cannot place prompts, provider credentials,
  titles, descriptions, or configuration objects into an Umami payload.
- Rapid identity replacement cannot drain events under an older user or discard
  the newest pending identity.
- Pageview and business-event context contains no query, fragment, credentials,
  full referrer, invite code, or other sensitive dynamic path value.
- Every migrated asynchronous attempt can invoke at most one terminal-result
  event, exactly once when the application observes a terminal state, including
  failure and cancellation semantics where applicable.
- Tracking failures do not change any user-visible success, failure,
  navigation, or API result.
- The legacy generic `visit` producer is deleted without a replacement course
  metric, backend consumer, or persistence path.
- Focused Jest suites pass, followed by:

      cd src/cook-web && npm run type-check
      cd src/cook-web && npm run lint
      python scripts/check_architecture_boundaries.py
      python scripts/check_repo_harness.py
      python scripts/check_dev_tools.py
      lefthook run pre-commit --all-files

## Idempotence and Recovery

All tracking calls remain safe to retry from the business workflow's
perspective. Tests reset module-level transport state between cases. Deleted
analytics events are not replayed: recovery uses the canonical producer from
the next accepted user action, while business operations remain independent and
fail-open.

## Interfaces and Dependencies

- Umami browser API: centralized `identify` and `track` calls only.
- Cook Web `useTracking`: feature-facing best-effort event boundary.
- Existing checkout, payment, publish, authentication, profile, learning-mode,
  and course-creation APIs remain unchanged.

# Correct the Umami remediation scope

## Purpose / Big Picture

PR #2716 must change only Cook Web Umami transport, event contracts,
producers, and their regression coverage. Review follow-ups had also changed
payment, billing, course-creation, and learning-mode business behavior to make
analytics outcomes easier to classify. This correction restores the `main`
business behavior while keeping analytics privacy-safe, fail-open, and
observational.

## Progress

- [x] 2026-08-31 05:18 CST: Rechecked the full PR against `origin/main` and
      confirmed business-flow changes outside the requested analytics scope.
- [x] 2026-08-31 06:00 CST: Restored business behavior and removed regression
      tests that asserted the out-of-scope behavior.
- [x] 2026-08-31 06:20 CST: Passed 8 focused suites / 113 tests, the
      then-current full frontend run, TypeScript, full frontend lint with no
      errors, and Prettier.
- [x] 2026-08-31 06:35 CST: Completed two independent production-diff audits;
      both found no remaining non-analytics behavior, backend/database change,
      Umami reader, or course-visit compatibility path.
- [x] 2026-08-31 06:40 CST: Passed the architecture-boundary check and prepared
      the generated repository harness documents for final validation.
- [x] 2026-08-31 07:05 CST: After the final fail-open fixes and removal of the
      superseded payment-hook test, passed all 211 frontend suites / 1,884
      tests.
- [x] 2026-08-31 07:10 CST: Passed the repository harness, developer-tool
      verification, and the full pre-commit gate.

## Surprises & Discoveries

- The payment hook had been rewritten with polling generations, wall-clock
  deadlines, completion guards, and stale-request handling even though Umami
  must not control payment state.
- Review follow-ups added billing-cache refresh, malformed-order handling, and
  duplicate course-creation suppression. These were product fixes, not
  analytics fixes.
- Analytics context carried through the shared payment hook expanded a business
  interface. Attribution now stays inside the modal producers instead.
- Several analytics callbacks occurred before provider calls or navigation.
  Wrapping only transport delivery was insufficient; the complete
  analytics-owned helper must be fail-open.

## Decision Log

- Decision: compare every production hunk to `origin/main`; retain only code
  whose side effect is tracking or isolating a tracking failure.
  Rationale: analytics may observe business state but must never redefine it.
- Decision: preserve removal of legacy incorrect event producers without
  compatibility dual-writing.
  Rationale: the old contracts are deliberately replaced rather than extended.
- Decision: accept less precise attribution when exact attribution would
  require changing a payment or billing interface.
  Rationale: best-effort telemetry cannot justify product-state changes.
- Decision: keep product-owned state separate from analytics eligibility state.
  Rationale: the learner Stripe return still needs its order ID for business
  retry bookkeeping, while an unconfirmed query value must remain absent from
  Umami.

## Outcomes & Retrospective

The product control flow matches `origin/main` in learner payment, creator
billing, course creation, learning-mode selection, and both Stripe return
paths. The shared payment hook has zero diff from `origin/main`. Analytics
attempt, result, pending, and attribution helpers are fail-open and cannot
block provider calls, synchronization, navigation, toasts, cache behavior, or
state transitions.

Two independent audits found no remaining non-analytics production change.
They also confirmed there is no backend, database, migration, Umami-reader,
course-visit metric, or compatibility dual-write in the PR.

## Context and Orientation

The canonical contract is
`docs/references/frontend-product-analytics.md`. Shared transport lives in
`src/web/src/c-common/tools/tracking.ts`; feature producers live in Cook
Web components and hooks. The highest-risk overreach was in learner payment,
creator billing, course creation, and learning-mode selection.

## Plan of Work

First restore exact `main` control flow in high-risk business modules while
leaving event calls fail-open. Then remove tests and documentation that claim
the reverted business fixes. Finally verify the full diff contains no backend,
database, Umami-reader, course-visit metric, or non-analytics product change.

## Concrete Steps

1. Restore payment polling, synchronization, toast, and error behavior.
2. Restore billing checkout branching and cache behavior.
3. Remove course-creation and learning-mode behavior guards.
4. Remove analytics context from the shared payment hook.
5. Keep privacy allowlists, event replacements, transport hardening, and the
   deletion of the generic visit producer.
6. Update analytics documentation and focused tests to match the narrower
   observational contract.

## Validation and Acceptance

- Production changes outside analytics helpers are limited to event calls,
  analytics-only state, or fail-open isolation.
- Payment, billing, login, navigation, and course-creation behavior matches
  `origin/main` when tracking succeeds, throws, rejects, or is unavailable.
- Focused producer/transport tests, TypeScript, lint, Prettier, repository
  harness, architecture boundaries, and the full frontend suite pass.
- The final PR is mergeable with no active in-scope review thread.

## Idempotence and Recovery

The correction is a new commit on top of the PR branch. Recovery compares an
affected file with both `origin/main` and the pre-correction PR head; unrelated
changes are not reset or discarded.

## Interfaces and Dependencies

No new runtime dependency, backend API, database schema, or Umami consumer is
introduced. Existing `useTracking`, tracking transport, and feature-owned typed
payload builders remain the only analytics interfaces.

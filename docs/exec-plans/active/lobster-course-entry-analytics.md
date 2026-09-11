# Lobster Course Entry Analytics

## Purpose / Big Picture

Measure whether eligible teachers actually see and choose the Lobster-assisted
course-creation entry on the admin course list. The immediate consumer is the
product decision about promoting that entry from a weak text link to the
recommended first-course CTA. This change must not claim that an external
handoff created a course; confirmed generation/import attribution requires a
later cross-system contract.

## Progress

- [x] 2026-09-11 13:20 CST: Audited the existing course-creation events and
  production data limitations.
- [x] 2026-09-11 13:35 CST: Added the entry impression/click contract and
  producers.
- [x] 2026-09-11 13:40 CST: Added focused eligibility, deduplication, payload,
  privacy, and failure-isolation tests.
- [x] 2026-09-11 13:45 CST: Ran 16 focused tests, TypeScript type-check,
  focused lint, developer-tool verification, and the repository harness.
- [x] 2026-09-11 14:05 CST: Gated entry rendering and impressions on resolved
  administrator access after review identified an ineligible-view window.

## Surprises & Discoveries

- Existing `creator_course_create_result` with `creation_path=ai_assistant`
  means that the browser accepted the external handoff. It is not evidence of
  course creation, generation, import, or publication.
- Existing admin pageviews overstate exposure because they do not prove that
  the configured entry rendered for the teacher.
- The configured URL resolves before administrator permission. Both rendering
  and impression production therefore need the same resolved-access gate.

## Decision Log

- 2026-09-11: Introduce a dedicated additive impression/click family and keep
  dual-writing the existing course-creation attempt/result events for
  historical dashboards.
- 2026-09-11: Use fixed `surface` and `presentation` enums. Do not send URLs,
  course content, contact information, or a duplicate user identifier.
- 2026-09-11: Treat one mounted eligible course-list visit as one impression.
  Route re-entry is a new exposure; React rerenders within the visit are not.

## Outcomes & Retrospective

The admin course list now reports a real eligible-view denominator and a
deliberate Lobster-entry click with a stable baseline presentation. Existing
course-creation events remain available for historical consumers. Confirmed
external generation/import attribution remains a separate cross-system task.

## Context and Orientation

The entry is rendered by `src/web/src/app/admin/page.tsx` when runtime config
provides `courseCreatorUrl`. Course-creation analytics builders live beside it
in `courseCreationAnalytics.ts`, and the page tests mock the shared tracking
hook. Business events must continue through `useTracking`; analytics failure
must not affect rendering or native navigation.

### Event family contract

- Business question: among teachers shown the Lobster entry on the admin
  course-list surface, what proportion deliberately choose it, and how does
  adoption differ when the presentation changes?
- Metric definition: distinct identified users emitting click divided by
  distinct identified users emitting impression, over the same time window,
  grouped by `surface` and `presentation`. Raw events are diagnostic only.
- Event names: `creator_ai_course_entry_impression`,
  `creator_ai_course_entry_click`.
- Actor and surface: authenticated teachers on `admin_course_list`.
- Trigger: impression after the configured entry is committed to the mounted
  page; click after the native anchor accepts a deliberate click and before
  navigation.
- Population: authenticated teachers for whom `courseCreatorUrl` is present.
  Missing-config pages and non-admin learner surfaces are excluded.
- Count unit: one mounted eligible route visit for impressions; one accepted
  user click for clicks.
- Deduplication: impressions once per component mount using an in-memory ref;
  clicks are not deduplicated because repeated deliberate handoffs are useful.
- Correlation: shared identified-user/session context only; no feature-owned
  stable identifier is necessary.
- Consumers: the Lobster entry promotion decision and subsequent A/B reports.
- Compatibility: additive events. Existing `creator_course_create_*` events
  remain unchanged and are dual-written on click.
- Verification: exact event names/payloads, missing-config exclusion,
  once-per-mount behavior across rerenders, privacy assertions, and fail-open
  behavior.

| Field | Type | Allowed values | Cardinality | Privacy class | Why required |
| --- | --- | --- | --- | --- | --- |
| `surface` | string | `admin_course_list` | low | non-personal | Fix the eligible UI surface. |
| `presentation` | string | `text_link` | low | non-personal | Baseline for a future promoted CTA comparison. |

## Plan of Work

Extend the feature-owned analytics helper with the new contract, emit one
impression from a guarded effect when the configured link is eligible, and
emit the click alongside existing compatibility events. Keep the implementation
independent from course loading and avoid inventing downstream success.

## Concrete Steps

1. Add typed event names and a fixed allowlisted payload builder.
2. Add an impression guard to the admin page lifecycle.
3. Add click dual-write at the real anchor handler.
4. Extend focused unit/component tests and run type/lint checks.

## Validation and Acceptance

- A configured entry emits exactly one impression during one mounted visit.
- Rerenders do not duplicate the impression.
- No configured entry means no impression.
- Each deliberate click emits the new click plus the historical attempt/result
  events, and native anchor behavior remains intact.
- Payloads contain only `surface` and `presentation`.
- Tracking errors do not hide the entry or prevent navigation.

## Idempotence and Recovery

The change is additive and can be reverted without data migration. Historical
events remain interpretable. Re-running tests and code generation is safe.

## Interfaces and Dependencies

No backend, database, or external Lobster change is required for this first
stage. Confirmed course-source attribution remains dependent on a future
external callback and server-owned persistence contract.

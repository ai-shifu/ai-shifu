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
- [x] 2026-09-14: Extended the entry contract for the recommended
      course-creation choice modal while preserving the established event family.

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
- 2026-09-14: Make prompt copying the primary in-product handoff. Keep the
  external guide optional and stop treating guide navigation as a confirmed
  course-creation attempt.

## Outcomes & Retrospective

The admin course list now reports a real eligible-view denominator and a
deliberate Lobster-entry click with a stable baseline presentation. Existing
course-creation events remain available for historical consumers. Confirmed
external generation/import attribution remains a separate cross-system task.

## Context and Orientation

The choice modal is rendered by `src/web/src/app/admin/page.tsx`; its AI prompt
copying remains available even when runtime config does not provide an optional
`courseCreatorUrl` guide. Course-creation analytics builders live beside it in
`courseCreationAnalytics.ts`, and the page tests mock the shared tracking hook.
Business events must continue through `useTracking`; analytics failure must not
affect copying, rendering, or native navigation.

### Event family contract

- Business question: among teachers shown the Lobster entry on the admin
  course-list surface, what proportion deliberately choose it, and how does
  adoption differ when the presentation changes?
- Metric definition: distinct identified users with a successful installation-instruction copy
  divided by distinct identified users emitting an impression, over the same
  time window, grouped by `surface` and `presentation`. Optional guide clicks
  are reported separately. Raw events are diagnostic only.
- Event names: `creator_ai_course_entry_impression`,
  `creator_ai_course_entry_click`, `creator_ai_skill_install_copy_attempt`,
  `creator_ai_skill_install_copy_result`.
- Actor and surface: authenticated teachers on `admin_course_list`.
- Trigger: impression after the choice modal opens for an authenticated
  teacher; entry click after the optional guide anchor accepts a deliberate
  click; installation-instruction-copy attempt immediately before clipboard work; one terminal
  installation-instruction-copy result after the clipboard promise settles.
- Population: authenticated teachers with resolved admin access. Missing guide
  configuration does not exclude the in-product copy path. Non-admin learner
  surfaces are excluded.
- Count unit: one mounted eligible route visit for impressions; one deliberate
  guide click or copy attempt; one terminal result per accepted copy attempt.
- Deduplication: impressions once per component mount using an in-memory ref;
  clicks are not deduplicated because repeated deliberate handoffs are useful.
- Correlation: shared identified-user/session context only; no feature-owned
  stable identifier is necessary.
- Consumers: the Lobster entry promotion decision and subsequent A/B reports.
- Compatibility: installation-instruction-copy events are additive. Existing
  `creator_course_create_*` events remain unchanged for actual course-creation
  operations and are no longer emitted for optional guide navigation.
- Verification: exact event names/payloads, missing-guide support,
  once-per-mount behavior across rerenders, both clipboard outcomes, privacy
  assertions, and fail-open analytics behavior.

| Field          | Type   | Allowed values                       | Cardinality | Privacy class | Why required                                                                |
| -------------- | ------ | ------------------------------------ | ----------- | ------------- | --------------------------------------------------------------------------- |
| `surface`      | string | `admin_course_list`                  | low         | non-personal  | Fix the eligible UI surface.                                                |
| `presentation` | string | `text_link`, `creation_choice_modal` | low         | non-personal  | Compare the former text-link baseline with the promoted modal presentation. |
| `outcome`      | string | `success`, `failed`                  | low         | non-personal  | Distinguish terminal installation-instruction-copy outcomes; result event only.               |

### Promoted choice-modal compatibility

The promoted course-creation modal keeps the existing impression and optional
guide-click names and uses `presentation=creation_choice_modal`. An impression
is emitted once per mounted eligible course-list visit when the modal actually
opens. Prompt copying uses its own attempt/result pair and never includes the
localized prompt in analytics. The manual path continues to use the existing
`creator_course_create_*` contract. Historical `text_link` events remain valid
and distinguishable.

## Plan of Work

Extend the feature-owned analytics helper with the new contract, emit one
impression from a guarded effect when the configured link is eligible, and
emit the click alongside existing compatibility events. Keep the implementation
independent from course loading and avoid inventing downstream success.

## Concrete Steps

1. Add typed event names and a fixed allowlisted payload builder.
2. Add an impression guard to the admin page lifecycle.
3. Add optional guide-click tracking and installation-instruction-copy attempt/result tracking.
4. Extend focused unit/component tests and run type/lint checks.

## Validation and Acceptance

- An opened eligible modal emits exactly one impression during one mounted
  visit, with or without an optional guide URL.
- Rerenders do not duplicate the impression.
- Each deliberate guide click emits the entry click and preserves native anchor
  behavior without claiming that course creation started.
- Each copy attempt emits exactly one bounded terminal result; prompt and
  clipboard error text are absent from every payload.
- Tracking errors do not hide the entry or prevent copying or navigation.

## Idempotence and Recovery

The change is additive and can be reverted without data migration. Historical
events remain interpretable. Re-running tests and code generation is safe.

## Interfaces and Dependencies

No backend, database, or external Lobster change is required for this first
stage. Confirmed course-source attribution remains dependent on a future
external callback and server-owned persistence contract.


## Two-step skill installation handoff (2026-09-15)

### Contract and compatibility

The modal now explains installation followed by asking the assistant to create a
course. The copied instruction only requests skill installation (or confirmation
that it is already installed). Copy success proves clipboard completion only,
not skill installation, course generation, import, or publication.

- Decision: measure whether eligible teachers use the installation handoff and
  whether clipboard failures prevent starting it.
- Metric: distinct identified teachers with a successful
  `creator_ai_skill_install_copy_result` divided by distinct eligible teachers
  with `creator_ai_course_entry_impression` in the same reporting window.
- Trigger: `creator_ai_skill_install_copy_attempt` immediately before clipboard
  work; exactly one `creator_ai_skill_install_copy_result` after settlement.
- Population: authenticated teachers with resolved admin access, including when
  the optional guide is absent; exclude guests and unresolved/denied access.
- Deduplication: ignore clicks while the copy promise is pending; each later
  deliberate retry is a new attempt. Close/reopen resets UI state, but settlement
  still records the outcome of the original attempt, without reviving stale UI.
- Payload: only `surface=admin_course_list`,
  `presentation=creation_choice_modal`, plus result-only `outcome=success|failed`.
  Never collect copied text, assistant names, raw errors, URLs, or course content.
- Consumers: product entry-adoption and clipboard-reliability reports. Repository
  search found only the adjacent helper, page producer, tests, and this document;
  no checked-in dashboard or query consumes the retired copy event names.
- Migration: stop emitting `creator_ai_course_prompt_copy_attempt` and
  `creator_ai_course_prompt_copy_result` from this button; do not dual-write or
  relabel historical data. Reports must separate legacy combined install/create
  prompt copies from new installation-only copies by event name, and use the
  deployment boundary for impression denominators. During mixed-version rollout,
  report copy outcome rates per family; do not claim a clean adoption comparison.
- Failure isolation: analytics remains best-effort; the displayed next-step hint
  depends only on clipboard success. No event is emitted merely for changing text.

### Implementation and acceptance

Use the existing component interface and guide/manual callbacks. Add a semantic
ordered list, persistent post-copy guidance, and translations in all five locales.
Remove the recommendation badge. Cover exact installation text, pending clicks,
retry, close/reopen races, eligible population, no retired events, privacy, and
tracking failures. Validate layout at desktop, mobile, long translations, and RTL.

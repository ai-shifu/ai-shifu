# Reading follow-up entry

## Purpose / Big Picture

Replace repeated reading-mode follow-up actions with one paragraph-end reading
boundary entry, using the approved local prototype as the visual target. Desktop
hover selects immediately. Mobile chooses the lowest complete visible end after
scrolling and accepts short taps to change the point. Questions expand inline,
retain drafts and history, and reuse the existing saved-element anchor and
follow-up context assembly. There is no fixed bottom entry or visible range explanation.

## Progress

- [x] 2026-11-02 UTC: Inspected the existing learner, store, streaming and backend context paths; created a feature branch from current origin/main.
- [x] 2026-11-02 UTC: Integrated the reading entry, keyboard access and inline question surface with shared state.
- [x] 2026-11-02 UTC: Verified analytics and desktop/mobile behavior with focused tests, production build, type-check, lint and repository checks.
- [x] 2026-11-02 UTC: Removed all proposed backend context changes at the user's request; inline and ordinary requests now send the same existing ASK payload.

## Surprises & Discoveries

- Rendering uses persistent engine elements, not arbitrary DOM paragraphs.
  Never fabricate element IDs or attribute an internal paragraph to a whole
  element: that can include subsequent content.
- Context behavior is outside this UI change. The existing history window and
  saved-element anchor remain authoritative; no full-lesson prefix is introduced.

## Decision Log

- Reuse finalized persistent content elements and existing store/request paths.
- Keep follow-up context unchanged, as explicitly requested by the user. Remove
  the proposed context scope, backend implementation and its tests from this PR.
- Preserve listen/classroom behavior; opt in to the new inline reading surface.
- Keep eligible-view tracking out of hover/scroll; measure deliberate accepted opens and dismissals.

## Outcomes & Retrospective

The implementation is limited to frontend entry and presentation. Frontend
focused suites cover the reading controller/tracker, inline AskBlock, real root
composition, eligibility, store/transport, and listening compatibility. The Node
22.23.4 production build, type-check, lint, architecture check and full pre-commit
gate passed. Pure text/visual metadata and disabled/legacy history compatibility
issues found in review were fixed and regression-tested. No runtime dependency
was added. No database migration or engine change is needed.

No local backend service or physical handset was available for an authenticated
full-stack browser acceptance run. The implementation is ready for review and
subsequent environment acceptance; no production deployment or main merge was
performed. The supported precise cutoff is a persisted element end, which can
contain multiple Markdown paragraphs. All follow-ups retain their existing
context assembly and history windows.

## Context and Orientation

Learner composition is in `src/web/src/app/c/[[...id]]/components/chat/`.
`LessonConversation` owns read-mode orchestration; `AskBlock` owns streaming and
input, and `useAskStateStore` owns lesson-scoped question/answer messages.
The backend follow-up context builder lives in `src/api/flaskr/service/learn/ask/`.
The approved source prototype lives outside the repository; its behavior and
constraints are restated here so this plan is independently understandable.

## Plan of Work

1. Add a testable candidate tracker respecting actual clipped scroll viewports.
2. Replace rendered repeated actions with stable reserved boundary markers,
   preserving audio/regeneration and finalize timing.
3. Opt reading AskBlock into an inline surface, retaining mounted state on close.
4. Preserve the existing ASK payload and backend context contract.
5. Add the analytics contract and focused regression coverage.

## Concrete Steps

Run focused Jest suites from `src/web`, type-check and lint. Run focused backend
compatibility tests and repository harness checks. Review the resulting diff, run the
required developer-tool gate before committing, and open a non-draft PR.

## Validation and Acceptance

Desktop hover is immediate and mobile taps never turn swipes or selections into
questions. Only one candidate is shown; incomplete/offscreen mobile ends are
excluded. Drafts, streaming and history survive collapse and mode switching.
Requests use the same real element anchors and payload as before; context
assembly and history-window behavior are unchanged.
Disabled follow-ups and non-reading modes retain their existing contracts.

## Idempotence and Recovery

Work is isolated on `sunner/reading-follow-up`. No production deployment or main
merge is part of this task. Existing state/API modules remain authoritative.

## Interfaces and Dependencies

No new runtime dependency is planned. New hooks and optional AskBlock props are
local to the learner feature and preserve existing consumers by default.

## Product analytics contract

Business question: how often learners deliberately open reading follow-ups and
whether they dismiss with close or continue. Weekly metrics count accepted opens
by surface and entry, and accepted dismissals by method; counts are aggregate,
not per-attempt conversion or proof of reading. No exposure denominator is claimed.

- `learner_read_follow_up_opened`: after accepting a closed/different anchor;
  payload `{surface: 'desktop'|'mobile', entry: 'boundary'|'history'}`.
- `learner_read_follow_up_closed`: after an open surface actually closes;
  payload `{surface: 'desktop'|'mobile', method: 'close'|'continue'}`.
- Eligible: published learner reading, including guests when the action is
  available. Preview, print, listen/classroom, disabled/stale targets and blocked
  activations are excluded. Global account exclusions remain transport-owned.
- Deduplication: one accepted open/close transition guarded by current local
  state. Rerenders do not emit. Separate deliberate opens count separately.
- Privacy: only the two documented low-cardinality enums. No content, anchor,
  IDs, titles, URLs, errors or pointer coordinates. Shared transport does not
  enrich the feature payload; its existing privacy tests remain the final gate.
- Consumers: weekly product follow-up adoption/dismissal reports in Umami.
  This additive family does not rename or change existing text submission or
  Live voice events; no repository-owned dashboard requires migration.
- Delivery: shared useTracking, best effort; synchronous/asynchronous failure
  cannot affect opening, closing, draft preservation or submission.
- Verification: exact payloads, eligibility, transitions/deduplication, sensitive
  field absence and fail-open tests, paired with shared transport regressions.

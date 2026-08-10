# Learner Profile Dialog Redesign

## Purpose / Big Picture

Turn the learner-profile onboarding into one stable, responsive three-step
task. The dialog keeps the same outer size while learners choose a method,
provide information, and confirm the result. Desktop uses a compact left step
rail; mobile uses a top step indicator. Both paths use benefit-first copy,
predictable back/next actions, and preserve entered content.

## Progress

- [x] 2026-08-07 00:00 CST: Audited the current routes, copy, layout, tests,
  and existing Dialog patterns; selected visual option 2 as the target.
- [x] 2026-08-07 06:10 CST: Implemented the responsive fixed-shell wizard and
  consistent route history.
- [x] 2026-08-07 06:25 CST: Updated learner-facing translations and focused
  interaction tests.
- [x] 2026-08-07 07:03 CST: Verified desktop and mobile behavior, completed the
  visual comparison, and passed the frontend checks.

## Surprises & Discoveries

- The existing modal sets only a maximum height, so each route changes the
  dialog's outer height.
- The paste path currently saves immediately while the guided path enters a
  review step, and every back action jumps to the initial choice.
- `DialogFooter` reverses mobile visual order by default; this wizard needs an
  explicit stable grid so visual, DOM, keyboard, and touch order agree.
- The guided conversation accumulates MarkdownFlow items without its own
  scrolling viewport, so new questions can appear below the visible area.
- Width alone is not a safe desktop breakpoint for a fixed dialog: a landscape
  phone can be wide enough for `md` while too short for the rail. The final
  layout requires both sufficient width and height.
- A stable outer shell still needs reflow-safe inner regions. The header keeps
  a stable slot but can scroll internally when translated or scaled text is
  unusually tall.

## Decision Log

- Decision: implement the second displayed Product Design option.
  Rationale: the step rail makes the three-stage task legible on desktop while
  collapsing naturally into a compact top indicator on mobile.
- Decision: both paste and guided paths end in the same review step.
  Rationale: saving must be one explicit final action regardless of how the
  information was collected.
- Decision: reuse the shared Radix Dialog, Button, theme tokens, Lucide icons,
  and Tailwind animation utilities.
  Rationale: the redesign should fit the existing product and add no UI or
  motion dependency.

## Outcomes & Retrospective

The learner now sees one stable three-step task instead of route-dependent
dialog sizes and save behavior. Both collection methods reach the same review
page, back navigation preserves the actual source and draft, and only the
explicit later/cancel action can bypass completion. Desktop, portrait mobile,
narrow French mobile, and landscape mobile visual checks passed. Focused tests,
type checking, linting, translation parity, repository harness checks, and the
pre-commit gate are recorded in the final change verification.

## Context and Orientation

The shell and route state live in
`src/cook-web/src/components/profile-onboarding/ProfileOnboardingModal.tsx`.
The MarkdownFlow session UI lives in sibling
`ProfileOnboardingConversation.tsx`. Learner-facing strings live in the three
`src/i18n/*/modules/profile-onboarding.json` files. Focused Jest tests sit next
to the two components.

## Plan of Work

Replace the route-dependent natural-height layout with one fixed three-zone
canvas. Add explicit route selection and forward/back navigation, send pasted
content through review, and preserve source-specific context. Give the guided
conversation its own scroll viewport and scroll to the newest item. Update all
supported locales to describe benefits and actions in plain learner language.

## Concrete Steps

1. Refactor the modal into a desktop step rail plus mobile top progress header.
2. Keep header, body, and footer dimensions stable and animate only the active
   body page with reduced-motion support.
3. Make route selection explicit, make paste advance to review, and make review
   return to the actual source page without losing the draft.
4. Reserve stable footer slots and lock navigation while saving or skipping.
5. Add internal conversation scrolling, status copy, and new-question anchoring.
6. Update Chinese, English, and French learner-facing strings and tests.
7. Capture desktop and mobile states, compare them with the selected design,
   fix P0-P2 differences, and record the result in `design-qa.md`.

## Validation and Acceptance

- The dialog outer dimensions do not change between choice, paste, guided,
  review, loading, and error states at desktop and mobile viewports.
- Desktop shows the left three-step rail; mobile shows a compact top indicator.
- Both collection paths reach review before the only final save action.
- Back returns to the immediately preceding meaningful page and retains input.
- Escape, outside interaction, and navigation cannot dismiss during submission;
  only the explicit later/cancel action can otherwise exit.
- New guided questions stay visible inside an internally scrolling body.
- Focus moves to each page heading and reduced-motion preferences are respected.
- Focused Jest, type checking, linting, translation checks, and visual QA pass.

## Idempotence and Recovery

All changes are local React, translation, test, and plan edits. Re-running tests
is safe. Pasted drafts remain scoped in session storage. If a guided session is
abandoned, its session identifier must not be attached to pasted content.

## Interfaces and Dependencies

No new runtime dependency or API contract is introduced. The implementation
continues to use the shared Dialog and Button primitives, `markdown-flow-ui`,
existing profile-onboarding APIs, current analytics events, and i18next files.

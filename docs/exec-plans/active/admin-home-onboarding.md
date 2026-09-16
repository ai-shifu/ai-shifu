# Admin Home Onboarding

## Purpose / Big Picture

Maintain the retained creator onboarding contract after the admin-home flow was
retired. The trial welcome dialog is the only first-entry surface on `/admin`,
while owner-only course-editor onboarding continues to guide eligible teachers.
Historical `admin_home_onboarding` backend records remain readable for
compatibility but no longer drive frontend UI, replay, completion writes, or
analytics events.

## Progress

- [x] 2026-06-17 13:10 CST: Added backend onboarding persistence model, service,
      route handlers, and focused pytest coverage.
- [x] 2026-06-17 13:25 CST: Added guide-course resolution plus `is_guide_course`
      flags on creator course list DTOs and coverage for the new list flag.
- [x] 2026-06-17 13:45 CST: Replaced admin layout trial dialog usage with the
      shared onboarding overlay, step builder, API wiring, and Umami event hooks.
- [x] 2026-06-17 14:05 CST: Finished PR1 runtime hardening, focused frontend
      coverage, and final verification before commit / PR.
- [x] 2026-06-17 14:40 CST: Added `creator_activated_at` so old users who
      become creators after rollout are still eligible for admin home onboarding.
- [x] 2026-06-17 22:20 CST: Added owner-only course editor onboarding for the
      first eligible owner editor entry and hardened the shared overlay for drawer
      targets, rounded highlight holes, edge padding, and toast/onboarding overlap.
- [x] 2026-06-18 10:30 CST: Updated the admin home onboarding to the new
      three-step flow: blank course creation, lobster AI course creation, and the
      full billing card with trial credit details.
- [x] 2026-09-16: Retired the admin-home creation and billing guidance so the
      retained trial welcome dialog is the only first-entry surface. Backend
      completion records remain readable for compatibility.

## Surprises & Discoveries

- Guide-course metadata remains available for course-list labeling even though
  the retired admin-home flow no longer consumes it.
- The shared onboarding hook also needs to close itself when the scene becomes
  disabled mid-session, otherwise route changes can leave the overlay mounted on
  unrelated admin pages.
- Existing user `created_at` is not enough for eligibility because operators can
  later grant creator ability through transfer-creator, course copy, or shared
  edit/publish permissions.
- Course editor settings live inside a Radix Sheet, so onboarding cannot rely on
  static target coordinates. Drawer steps need explicit open/close ownership,
  outside-click prevention, scroll-then-measure behavior, and short coordinate
  stabilization before rendering the overlay.
- Success toast and editor onboarding are both top-level feedback surfaces. They
  should be sequenced rather than stacked, otherwise the toast can visibly bleed
  through the onboarding overlay during route transition.

## Decision Log

Decisions before the 2026-09-16 retirement entry are retained as implementation
history. The final retirement decision overrides them for current behavior.

- Decision: Gate onboarding by creator eligibility, exclude operators, and use
  a backend rollout threshold config (`ADMIN_ONBOARDING_ENABLED_FROM`) so older
  users do not auto-enter the flow.
  - Why: product wants only new creator users to see the onboarding after
    rollout.
- Decision: Use `user_users.creator_activated_at` as the primary eligibility
  timestamp, falling back to `created_at` only when the creator activation time
  is absent.
  - Why: old regular users can become creators after rollout through admin
    login, operator transfer-creator, operator course copy, or shared
    edit/publish permissions.
- Decision: PR2 editor onboarding is owner-only for the first eligible owner
  editor entry, regardless of whether the user arrived from manual course
  creation, lobster course creation, the course list, or a direct editor link.
  Shared-permission users do not see the editor onboarding in PR2.
  - Why: external lobster entry points may not return a reliable source
    parameter, while the editor steps are still owner-oriented settings such as
    model, listen mode, pricing, preview, and publish.
- Decision: Keep a follow-up shared-permission onboarding variant as a later
  iteration instead of forcing shared users through the owner flow.
  - Why: shared collaborators usually need a lighter collaboration path focused
    on prompt editing, debugging, and preview, while owner-oriented settings and
    publish actions would add noise or mislead first-use expectations.
- Decision: Resolve the guide course from the existing zh/en demo-course config
  keys and expose `is_guide_course` through the creator course list.
  - Why: the UI must spotlight the real course card without adding a separate
    recommendation entry.
- Decision: Keep guide-course resolution in the backend/list DTOs, but remove
  the guide-course step from the admin home onboarding.
  - Why: the revised product flow should only introduce course creation,
    lobster-assisted course creation, and credit/package management.
- Decision: The lobster-assisted creation step can include an action link inside
  the onboarding card.
  - Why: the existing homepage link may be highlighted, but the card copy also
    needs a direct way to open the same external course-creator URL in a new
    tab without advancing the overlay.
- Decision: Keep the reusable onboarding overlay and target-resolution logic in
  shared frontend modules.
  - Why: PR2 will reuse the same flow mechanics for editor onboarding.
- Decision: Preserve the create-course success toast, but delay navigation to
  the editor until the short toast duration completes.
  - Why: product wants the success feedback to remain, while the editor
    onboarding must not visually overlap with a stale toast from the previous
    route.
- Decision: Use a shared rounded highlight implementation based on an outer
  shadow around the target instead of SVG or rectangular mask slices.
  - Why: it gives consistent rounded holes across admin home and editor targets,
    including targets near viewport edges and targets inside portal-based
    drawers.
- Decision: Stop producing admin-home onboarding UI and analytics events while
  retaining the backend scene contract and course-editor onboarding.
  - Why: the admin home is self-explanatory, and its overlay competed with the
    trial welcome dialog that product chose to retain.

## Outcomes & Retrospective

- The admin-home walkthrough, its target anchors, menu entry, localized copy,
  completion writes, and analytics producers are retired. The trial welcome
  dialog remains the only automatic first-entry surface on `/admin`.
- Deferred follow-up: add a shared-permission editor onboarding scene after the
  owner flow lands. The first candidate scope is a lightweight three-step path
  for prompt editing, debugging, and preview only, with course settings and
  publish intentionally excluded.
- PR2 owner editor onboarding now covers prompt editing, debug, adding a
  lesson, settings entry, model, listen mode, price, preview, and publish.
  Settings-drawer steps keep the drawer open during onboarding and close it
  once the flow leaves the settings panel. Direct editor entries are recorded
  with `trigger_source=editor_entry`; manual and lobster source parameters are
  still preserved when present.
- Follow-up: open a separate French i18n polish PR to normalize accented French
  across `src/i18n/fr-FR/**`. This PR only fixes onboarding strings to avoid
  mixing broad copy cleanup with the onboarding behavior change.
- The admin-home onboarding was retired on 2026-09-16. The trial welcome dialog
  remains active, the menu replay entry is hidden, and the underlying course
  editor replay state plus existing backend completion rows are intentionally
  left untouched.

## Context and Orientation

- Backend owner paths:
  - `src/api/flaskr/service/user/onboarding.py`
  - `src/api/flaskr/route/user.py`
  - `src/api/flaskr/service/user/models.py`
  - `src/api/flaskr/service/shifu/demo_courses.py`
  - `src/api/flaskr/service/shifu/dtos.py`
  - `src/api/flaskr/service/shifu/shifu_draft_funcs.py`
- Frontend owner paths:
  - `src/web/src/app/admin/layout.tsx`
  - `src/web/src/app/admin/page.tsx`
  - `src/web/src/components/onboarding/editorOnboardingSteps.ts`
  - `src/web/src/components/onboarding/OnboardingOverlay.tsx`
  - `src/web/src/components/shifu-edit/ShifuEdit.tsx`
  - `src/web/src/hooks/useOnboarding.ts`
  - `src/web/src/lib/onboardingTargets.ts`
  - `src/web/src/store/onboardingReplayStore.ts`

## Plan of Work

1. Keep the retired admin-home scene absent from frontend rendering, replay,
   completion, and analytics paths.
2. Preserve the trial welcome dialog and owner-only course-editor onboarding.
3. Keep historical backend scene records and response fields compatible while
   frontend consumers migrate independently.

## Concrete Steps

1. Verify `/admin` mounts the trial welcome dialog without starting an
   onboarding overlay or emitting admin-home onboarding events.
2. Verify the course editor still gates, renders, completes, and optionally
   replays its retained onboarding scene.
3. Keep `admin_home_onboarding` in backend-compatible types and stored records,
   but do not add new frontend consumers.
4. Run focused Jest coverage, type checking, translation checks, and the
   repository harness when this contract changes.

## Validation and Acceptance

- `/admin` does not render creation-button or billing-card onboarding.
- `/admin` continues to show the trial welcome dialog when its existing grant
  and acknowledgement rules are satisfied.
- The user menu does not expose the retired onboarding replay entry.
- No admin-home onboarding completion request or analytics event is produced.
- Historical `admin_home_onboarding` records and status fields remain readable.
- Editor settings steps keep the settings drawer open, prevent outside-click
  closure from onboarding clicks, and render only after drawer target
  coordinates stabilize.
- Manual course creation still shows a short success toast, then transitions to
  editor onboarding without overlapping visual layers.
- Completing or replaying course-editor onboarding only updates
  `course_editor_onboarding`.
- Focused frontend Jest/type-check, translation, and repository harness checks
  pass.

## Idempotence and Recovery

- Historical backend completion remains idempotent through the existing
  `(user_bid, scene_key, version)` constraint; no migration or record deletion
  is required for the retired scene.
- Old local-storage values containing `admin_home_onboarding` are ignored while
  the retained course-editor replay state remains readable.
- Course-editor target-missing steps must skip safely without dead-ending the
  retained flow.

## Shared-Permission Follow-up

- Scope this as a separate post-PR2 iteration rather than widening the owner
  rollout.
- Reuse the same overlay / target-resolution primitives, but store a separate
  scene key so owner completion and collaborator completion do not interfere.
- Candidate step set:
  - `prompt_edit`
  - `debug`
  - `preview`
- Exclude owner-heavy actions from the shared variant:
  - `course_settings`
  - `publish`
- Trigger once per eligible shared collaborator on their first entry to any
  shared course editor, not once per course.
- Open product question for the later iteration: if a shared collaborator also
  has publish permission, decide whether that still belongs in the lightweight
  collaborator flow or should remain owner-only.

## Interfaces and Dependencies

- API:
  - `GET /api/user/onboarding/status`
  - `POST /api/user/onboarding/complete`
- Config:
  - `ADMIN_ONBOARDING_ENABLED_FROM`
  - `DEMO_SHIFU_BID`
  - `DEMO_EN_SHIFU_BID`
- Tracking:
  - `creator_onboarding_started`
  - `creator_onboarding_step_viewed`
  - `creator_onboarding_completed`
  - These events are produced by retained course-editor onboarding only.

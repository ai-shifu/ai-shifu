# Admin Home Onboarding

## Purpose / Big Picture

Add creator-only admin home onboarding that replaces the old trial welcome
dialog, highlights the key billing and creation entry points, tracks progress
with Umami, and persists per-user completion so each scene shows at most once.

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
- [x] 2026-06-18 10:30 CST: Updated the admin home onboarding to the new
      three-step flow: blank course creation, lobster AI course creation, and the
      full billing card with trial credit details.

## Surprises & Discoveries

- The admin home flow no longer includes the guide-course card step. The guide
  course metadata remains available for course-list labeling, but the visible
  onboarding now focuses on creation and billing entry points.
- The shared onboarding hook also needs to close itself when the scene becomes
  disabled mid-session, otherwise route changes can leave the overlay mounted on
  unrelated admin pages.
- Existing user `created_at` is not enough for eligibility because operators can
  later grant creator ability through transfer-creator, course copy, or shared
  edit/publish permissions.

## Decision Log

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
- Decision: PR2 editor onboarding is owner-only for manual create / lobster
  create. Shared-permission users do not see the editor onboarding in PR2.
  - Why: the editor steps include owner-oriented settings such as model, listen
    mode, pricing, preview, and publish.
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

## Outcomes & Retrospective

- Pending completion. PR1 should leave the backend contract, admin home UI
  wiring, and shared onboarding primitives ready for reuse by PR2.
- Admin home onboarding now presents three product steps when billing is
  enabled: create a blank course, open lobster AI course creation, and review
  the billing card for trial credits and package purchases. If billing is
  disabled or a target is not present, missing steps skip safely.
- Follow-up: open a separate French i18n polish PR to normalize accented French
  across `src/i18n/fr-FR/**`. This PR only fixes onboarding strings to avoid
  mixing broad copy cleanup with the onboarding behavior change.

## Context and Orientation

- Backend owner paths:
  - `src/api/flaskr/service/user/onboarding.py`
  - `src/api/flaskr/route/user.py`
  - `src/api/flaskr/service/user/models.py`
  - `src/api/flaskr/service/shifu/demo_courses.py`
  - `src/api/flaskr/service/shifu/dtos.py`
  - `src/api/flaskr/service/shifu/shifu_draft_funcs.py`
- Frontend owner paths:
  - `src/cook-web/src/app/admin/layout.tsx`
  - `src/cook-web/src/app/admin/page.tsx`
  - `src/cook-web/src/components/onboarding/*`
  - `src/cook-web/src/hooks/useOnboarding.ts`
  - `src/cook-web/src/lib/onboardingTargets.ts`

## Plan of Work

1. Verify the current PR1 implementation against the product rules and local
   onboarding plan.
2. Fix runtime gaps in the reusable onboarding flow and add focused regression
   tests.
3. Run focused backend/frontend verification and capture remaining risks before
   commit / PR.

## Concrete Steps

1. Inspect the admin layout, course list page, onboarding hook, and new backend
   onboarding service for mismatch or missing edge-case handling.
2. Add/adjust tests for onboarding route behavior, guide-course list flags, and
   frontend hook flow control as needed.
3. Re-run the smallest relevant pytest / Jest / type-check commands.
4. Summarize residual risk, then prepare the branch for commit / PR once PR1 is
   stable.

## Validation and Acceptance

- Eligible creator users on `/admin` see the onboarding once.
- Old regular users who become creators after rollout are eligible based on
  `creator_activated_at`.
- Operators and old pre-rollout creators do not auto-see onboarding.
- The lobster and billing-card steps can silently skip if their targets are
  unavailable.
- The overlay does not stay mounted after leaving the eligible scene.
- Completing the final step persists `admin_home_onboarding` completion and
  prevents replay on refresh.
- Focused backend pytest and frontend Jest/type-check commands pass.

## Idempotence and Recovery

- Backend completion is idempotent via the unique
  `(user_bid, scene_key, version)` constraint.
- Frontend target-missing steps must skip safely and must not dead-end on the
  final step.
- Missing optional targets should continue through the next step without an
  error state.

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

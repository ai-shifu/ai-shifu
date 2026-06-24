# Existing Creator Onboarding Rollout

## Purpose / Big Picture

Extend the creator onboarding rollout to a targeted existing-creator cohort
 after `#1931` (admin home onboarding) and `#1933` (course editor onboarding)
 are already merged on `main`. The rollout must show the admin-home onboarding
 once on the first `/admin` entry and the editor onboarding once on the first
 owner editor entry, while keeping the old-user billing copy free of expired
 trial-credit messaging. The implementation must preserve the existing
 onboarding storage model and event names, and only widen eligibility and copy
 selection.

## Progress

- [x] 2026-06-23 14:45 CST: Confirmed `main` now includes `#1933` and aligned
      the old-user rollout scope with the merged admin-home and editor
      onboarding baseline.
- [x] 2026-06-23 14:55 CST: Finalize the backend eligibility contract for the
      existing-creator rollout segment and scene-level flags.
- [x] 2026-06-23 15:05 CST: Implement admin-home variant switching so old-user
      billing guidance uses generic balance/package copy instead of trial-credit
      copy.
- [x] 2026-06-23 15:15 CST: Wire editor onboarding to the new scene-level
      eligibility while keeping source parameters as tracking-only metadata.
- [x] 2026-06-23 15:25 CST: Add focused backend/frontend coverage and verify
      the expanded tracking payload.

## Surprises & Discoveries

- `#1933` already changed editor onboarding to support direct editor entry, so
  this rollout no longer needs course-count heuristics to make skills-created
  courses reachable.
- The current admin-home billing step always renders trial-credit messaging
  from `trial_offer`; that is incorrect for existing creators whose historical
  onboarding credits have already expired.
- Existing onboarding persistence is already scene-based and idempotent. The
  safest rollout path is to extend the status payload instead of adding a new
  completion table or bumping the onboarding version.

## Decision Log

- Decision: Keep onboarding completion on `version=v1` and use new eligibility
  metadata instead of introducing `v2`.
  - Why: a version bump would replay onboarding for users who already completed
    the new-creator flow, which is not the product intent.
- Decision: Model old-user rollout as a user-segment eligibility expansion, not
  as a course-count gate inside the editor page.
  - Why: skills can create multiple courses before the user first re-enters the
    admin/editor surfaces, so first-editor-entry should not depend on owning
    exactly one course.
- Decision: Keep current Umami event names and add `user_segment` while
  preserving `trigger_source`.
  - Why: existing dashboards keep working, while the rollout can still be
    split between `new_creator` and `existing_creator_rollout`.
- Decision: Keep old-user rollout scope configurable through dynamic config
  keys first, instead of hardcoding more audience rules into code.
  - Why: rollout scope is product policy, not a schema concern. Small changes
    such as new time windows, enable flags, or limited cohorts should be
    adjustable without migrations or redeploys.

## Outcomes & Retrospective

- Implemented the rollout contract without a version bump. Existing creators
  can now be targeted by config, while already-completed `v1` scenes remain
  untouched.
- The admin-home billing card now switches between trial-credit copy and a
  generic balance/package message based on backend-provided variant metadata.
- Both admin-home and editor onboarding tracking payloads now include
  `user_segment`, keeping existing event names intact for dashboards.

## Context and Orientation

- Backend owner paths:
  - `src/api/flaskr/service/user/onboarding.py`
  - `src/api/flaskr/route/user.py`
  - `src/api/tests/service/user/test_onboarding_routes.py`
- Frontend owner paths:
  - `src/cook-web/src/app/admin/layout.tsx`
  - `src/cook-web/src/components/onboarding/onboardingSteps.ts`
  - `src/cook-web/src/components/shifu-edit/ShifuEdit.tsx`
  - `src/cook-web/src/types/onboarding.ts`
- Translation owner paths:
  - `src/i18n/zh-CN/modules/onboarding.json`
  - `src/i18n/en-US/modules/onboarding.json`
  - `src/i18n/fr-FR/modules/onboarding.json`

## Plan of Work

1. Extend the onboarding status contract with segment-aware, scene-level
   eligibility and billing-copy variants for old creators.
2. Update admin-home and editor onboarding consumers to use the new contract,
   keeping source parameters only for tracking metadata.
3. Add rollout-aware tracking payload fields and focused backend/frontend
   verification.

## Concrete Steps

1. Backend contract
   - Add an existing-creator rollout config gate.
   - Return `user_segment` from onboarding status.
   - Return scene-level `eligible` flags for:
     - `admin_home_onboarding`
     - `course_editor_onboarding`
   - Return `admin_home_onboarding.variant` with:
     - `trial_credit`
     - `generic_billing`
2. Admin home rollout
   - Read scene-level eligibility in the admin layout instead of relying only on
     the top-level creator eligibility boolean.
   - Switch the billing-card copy by variant so the old-user rollout uses a
     generic “check balance / buy or upgrade packages” message.
   - Keep the blank-create and lobster steps unchanged.
3. Editor rollout
   - Gate editor onboarding with:
     - owner-only access
     - scene completion false
     - scene-level eligibility true
     - non-history editor view
   - Keep `manual_create`, `lobster_create`, `skills_create`, and
     `editor_entry` as `trigger_source` values only.
4. Tracking
   - Keep existing event names:
     - `creator_onboarding_started`
     - `creator_onboarding_step_viewed`
     - `creator_onboarding_completed`
     - `creator_onboarding_complete_failed`
   - Add `user_segment` to all onboarding event payloads.
   - Keep `trigger_source=admin_entry` for admin-home events.
5. Verification
   - Backend tests for new segment/scene/variant combinations.
   - Frontend tests for variant-based admin-home copy and editor eligibility
     gating.
   - Type-check and focused lint/test runs.

## Validation and Acceptance

- A rollout-eligible existing creator who has not completed admin-home
  onboarding sees it once on the first `/admin` entry.
- The admin-home billing step for existing creators does not claim new trial
  credits were granted.
- A rollout-eligible existing creator who has not completed editor onboarding
  sees it once on the first entry to any owner course editor.
- Skills-created courses can trigger editor onboarding on first editor entry
  even if more than one course already exists.
- Shared-permission users still do not see the owner editor onboarding.
- Existing event names remain unchanged and now include `user_segment`.
- Users who already completed either scene under `v1` do not replay that scene.

## Idempotence and Recovery

- Scene completion remains idempotent through the existing
  `(user_bid, scene_key, version)` uniqueness.
- If rollout config is disabled, scene-level eligibility must fall back to
  `false` without breaking the existing payload shape.
- If the variant field is absent or malformed on the frontend, admin-home
  billing copy should safely fall back to the current trial-credit behavior for
  new creators and never block rendering.

## Interfaces and Dependencies

- API:
  - `GET /api/user/onboarding/status`
  - `POST /api/user/onboarding/complete`
- Dynamic config:
  - `ADMIN_ONBOARDING_ENABLED_FROM`
  - `ADMIN_EXISTING_CREATOR_ONBOARDING_ENABLED_FROM`
- Tracking:
  - `creator_onboarding_started`
  - `creator_onboarding_step_viewed`
  - `creator_onboarding_completed`
  - `creator_onboarding_complete_failed`

## Follow-up Expansion Guidance

- Near-term audience expansion should continue through dynamic config, not
  migrations. Preferred examples:
  - enable/disable switch for existing-creator rollout
  - site or locale-specific rollout keys
  - whitelist or limited-cohort keys
  - percentage or staged rollout keys
- If old-user targeting rules grow beyond a few independent keys, consolidate
  them into one structured config payload rather than adding many parallel
  scalar keys.
- Only introduce a dedicated config table or admin management UI when rollout
  policy becomes high-frequency operational work with audit/history needs.

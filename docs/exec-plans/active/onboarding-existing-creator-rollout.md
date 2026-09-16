# Existing Creator Onboarding Rollout

## Purpose / Big Picture

Maintain the existing-creator rollout for the retained owner course-editor
onboarding. The admin-home flow and its billing-copy variants are retired for
all cohorts. Backend segment, scene, variant, and completion fields remain
compatible so historical records and older clients are not broken, but the
frontend no longer uses them to render or track admin-home onboarding.

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
- [x] 2026-09-16: Retired the admin-home onboarding surface for all creator
      segments while preserving the rollout fields for backend compatibility.

## Surprises & Discoveries

- `#1933` already changed editor onboarding to support direct editor entry, so
  this rollout no longer needs course-count heuristics to make skills-created
  courses reachable.
- Before retirement, the admin-home billing step rendered trial-credit
  messaging from `trial_offer`; that was incorrect for existing creators whose
  historical onboarding credits had already expired.
- Existing onboarding persistence is already scene-based and idempotent. The
  safest rollout path is to extend the status payload instead of adding a new
  completion table or bumping the onboarding version.

## Decision Log

Decisions about admin-home variants below are retained as rollout history. The
2026-09-16 retirement decision overrides them for current frontend behavior.

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
- Before retirement, the admin-home billing card switched between trial-credit
  and generic balance/package copy using backend variant metadata. Those fields
  now remain for compatibility only.
- Historical admin-home and retained editor events include `user_segment`, so
  existing dashboards can distinguish their original rollout cohorts.
- From 2026-09-16 onward, frontend onboarding events are produced only by the
  retained course-editor scene; historical admin-home events remain valid and
  must not be reinterpreted.

## Context and Orientation

- Backend owner paths:
  - `src/api/flaskr/service/user/onboarding.py`
  - `src/api/flaskr/route/user.py`
  - `src/api/tests/service/user/test_onboarding_routes.py`
- Frontend owner paths:
  - `src/web/src/app/admin/layout.tsx`
  - `src/web/src/components/shifu-edit/ShifuEdit.tsx`
  - `src/web/src/components/onboarding/editorOnboardingSteps.ts`
  - `src/web/src/store/onboardingReplayStore.ts`
  - `src/web/src/types/onboarding.ts`
- Translation owner paths:
  - `src/i18n/zh-CN/modules/onboarding.json`
  - `src/i18n/en-US/modules/onboarding.json`
  - `src/i18n/fr-FR/modules/onboarding.json`

## Plan of Work

1. Preserve the backend rollout payload and historical completion records for
   compatibility without restoring admin-home consumers.
2. Apply scene-level eligibility only to the retained owner course-editor
   onboarding.
3. Keep editor analytics segment-aware and verify that no admin-home producer
   remains.

## Concrete Steps

1. Backend compatibility
   - Keep `user_segment` and scene-level fields stable for existing clients.
   - Preserve stored `admin_home_onboarding` completions and retired variant
     values without adding new frontend behavior.
2. Editor rollout
   - Gate editor onboarding with:
     - owner-only access
     - scene completion false
     - scene-level eligibility true
     - non-history editor view
   - Keep `manual_create`, `lobster_create`, `skills_create`, and
     `editor_entry` as `trigger_source` values only.
3. Tracking
   - Keep existing event names:
     - `creator_onboarding_started`
     - `creator_onboarding_step_viewed`
     - `creator_onboarding_completed`
     - `creator_onboarding_complete_failed`
   - Keep `user_segment` on retained editor event payloads.
   - Do not emit these events with `scene_key=admin_home_onboarding`.
4. Verification
   - Backend compatibility tests for stored scene data and status payloads.
   - Frontend tests for editor eligibility and absence of admin-home UI.
   - Type-check and focused lint/test runs.

## Validation and Acceptance

- Existing creators do not see admin-home onboarding or its retired billing
  copy, regardless of historical eligibility or completion state.
- A rollout-eligible existing creator who has not completed editor onboarding
  sees it once on the first entry to any owner course editor.
- Skills-created courses can trigger editor onboarding on first editor entry
  even if more than one course already exists.
- Shared-permission users still do not see the owner editor onboarding.
- Retained editor event names remain unchanged and include `user_segment`.
- Users who already completed course-editor onboarding under `v1` do not replay
  that scene automatically.
- Historical admin-home completions remain readable but do not affect current
  frontend behavior.

## Idempotence and Recovery

- Scene completion remains idempotent through the existing
  `(user_bid, scene_key, version)` uniqueness.
- If rollout config is disabled, scene-level eligibility must fall back to
  `false` without breaking the existing payload shape.
- Retired admin-home variant fields may remain in responses for compatibility;
  the frontend ignores them and does not need a display fallback.
- Old local replay state for `admin_home_onboarding` is ignored without
  affecting `course_editor_onboarding`.

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
  - These events are produced by retained course-editor onboarding only.

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

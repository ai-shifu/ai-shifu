# Canonical Background And Onboarding Contract

## Purpose / Big Picture

Make `user_users.learner_profile` the only read authority for the historical
`sys_user_background` system variable. Course MarkdownFlow assignments and the
generic profile update endpoint must update the canonical profile and append a
matching `VariableValue` row in one transaction, while all reads ignore old
background variable rows. At the same time, retire the temporary learner and
admin onboarding compatibility protocol so the application has one direct
profile-v2 contract before later collection methods are introduced.

No database migration is required. Historical background and sentinel rows
remain stored, but no longer affect runtime behavior.

## Progress

- [x] 2026-08-25 10:00 CST: Audited canonical profile, generic system-variable,
      course runtime, sign-in merge, onboarding, admin, and frontend consumers.
- [x] 2026-08-25 10:45 CST: Bound `sys_user_background` reads and writes to the
      canonical learner profile with transactional regression coverage.
- [x] 2026-08-25 10:55 CST: Removed learner legacy projection/sentinel handling
      and published one direct profile-v2 status and completion contract.
- [x] 2026-08-25 11:00 CST: Removed admin compatibility fields and aligned
      frontend APIs, gate state, dialog prefill, translations, and tests.
- [x] 2026-08-25 11:20 CST: Regenerated repository artifacts, passed focused,
      full, and repository gates, documented outcomes, and archived this plan.

## Surprises & Discoveries

- The course MarkdownFlow assignment path already converges on
  `save_user_profiles`, so binding the system field there covers normal course
  interactions without adding profile-v2 state writes.
- Phone and email guest-to-account flows run the canonical sign-in merge and
  then migrate generic profile labels. Once background becomes a mapped label,
  that second phase must explicitly exclude it so target-cleared-wins remains
  owned by the canonical merge helper.
- The temporary compatibility surface spans both learner response wrapping and
  admin revision aliases; removing only the learner wrapper would leave stale
  frontend fallbacks and ambiguous tests.
- Canonical override must be explicit even when a defensive read cannot load a
  user aggregate; otherwise a historical variable row can reappear through the
  fallback branch despite normal users being unaffected.
- Removing the legacy route-owned commit reduced the grandfathered direct
  commit count, so the UoW baseline correctly ratcheted from 157 to 156 sites.
- The branch baseline contains migration `d8c4f6a1b2e3`, while its unchanged
  single-head test still expects `c7b9e1a2d4f6`. This contract change does not
  touch migrations; all other backend tests pass when that stale assertion is
  excluded.

## Decision Log

- Decision: canonical reads never fall back to a historical
  `sys_user_background` row, including when `learner_profile` is empty.
  - Why: an explicit canonical clear must not resurrect older variable data.
- Decision: generic background writes append a `VariableValue` row and update
  the locked user aggregate in the same outer transaction, but do not create a
  profile-v2 onboarding state.
  - Why: existing variable-history consumers retain an audit-compatible row,
    while onboarding completion remains derived from canonical profile/state.
- Decision: keep historical rows and database columns untouched.
  - Why: the contract can be retired without a risky data migration.
- Decision: ignore old onboarding sentinels completely.
  - Why: users without a canonical profile or profile-v2 state must now follow
    the current blocking collection flow.
- Decision: retain the string `profile-v2` contract/state version, but remove
  only the temporary admin numeric `version` alias and revision fallback.
  - Why: the canonical protocol identity is still active; the numeric field was
    only a deployment bridge.

## Outcomes & Retrospective

`sys_user_background` is now a compatibility alias whose runtime, label, and
course-variable reads are always supplied by `user_users.learner_profile`.
Both generic write paths validate and moderate before writing, lock the user,
update the canonical field and UTC timestamp semantics, and append matching
global variable history in the caller-owned transaction. Explicit clears
append an empty latest row while canonical empty remains authoritative.

Learner onboarding now returns one direct profile-v2 status and accepts only
the canonical completion payload. Old sentinel rows and background rows remain
stored but cannot affect eligibility, draft prefill, or runtime variables. The
admin contract exposes only its current fields and `config_revision`; the
frontend rejects wrapped, non-blocking, and other retired responses fail-open.

Verification passed 203 focused backend tests, 3251 backend tests with 15
skipped and 46 subtests after excluding the unchanged migration-head baseline,
and 169 frontend suites / 1352 tests. TypeScript, ESLint, Prettier, repository-
pinned Ruff, translations, architecture (133 baseline, 0 new), repository
harness, dev-tool validation, UoW ratchet, diff checks, and all-files lefthook
passed. A separate proxy-free run passed all seven LangFuse semantics tests.

## Context and Orientation

- Canonical learner profile:
  - `src/api/flaskr/service/profile/learner_profile.py`
  - `src/api/flaskr/service/profile/models.py`
- Generic system-variable reads and writes:
  - `src/api/flaskr/service/profile/constants.py`
  - `src/api/flaskr/service/profile/funcs.py`
- Learner onboarding contract and routes:
  - `src/api/flaskr/service/profile/onboarding.py`
  - `src/api/flaskr/service/profile/legacy_onboarding.py`
  - `src/api/flaskr/service/common/profile_onboarding.py`
  - `src/api/flaskr/route/profile.py`
- Admin onboarding contract:
  - `src/api/flaskr/route/admin_profile_onboarding.py`
- Frontend API, gate, dialog, and admin consumers:
  - `src/cook-web/src/api/learnerProfile.ts`
  - `src/cook-web/src/components/profile-onboarding/`
  - `src/cook-web/src/app/c/[courseId]/useCourseProfileOnboardingGate.ts`
  - `src/cook-web/src/app/admin/operations/profile-onboarding/`

## Plan of Work

1. Add `learner_profile` to the aggregate system-field mapping and centralize
   canonical background validation/application so both generic write paths lock
   the user, enforce the 1000-codepoint and moderation contract, update the UTC
   timestamp, and append variable history atomically.
2. Exclude background from legacy prefill and generic sign-in label migration;
   keep legacy nickname/style behavior and canonical sign-in merge semantics.
3. Delete legacy onboarding projection and sentinel code. Return direct
   profile-v2 status, accept only the modern completion payload, and remove the
   non-blocking legacy presentation.
4. Remove admin compatibility fields and revision fallback, then align all
   frontend types, API owners, gate logic, dialog prefill, admin state, i18n, and
   tests with the direct contract.
5. Regenerate generated knowledge/i18n artifacts and run focused tests before
   repository-wide static and harness checks.

## Concrete Steps

1. Update profile constants, aggregate field mapping, canonical write helpers,
   and user/profile services. Add tests for read authority, dual write, clear,
   moderation, length, rollback, course substitution, and sign-in ownership.
2. Replace dual-protocol status/complete route parsing and remove
   `legacy_onboarding.py`. Update learner route tests to assert direct profile-v2
   output and strict rejection of old, mixed, empty, and unknown payloads.
3. Normalize admin config only from `revision`, expose only
   `config_revision`, and update real preview callers and tests.
4. Simplify frontend learner/admin API types and callers, remove background
   prefill copy, and delete dead API-map entries.
5. Run formatting, lint, type, translation, architecture, knowledge, harness,
   diff, and lefthook checks; record exact results below.

## Validation and Acceptance

- `%{{sys_user_background}}` always resolves from canonical
  `learner_profile`, including an explicit empty value.
- Generic background writes and clears atomically update the canonical field,
  timestamp, and latest variable row; failed moderation or persistence leaves
  both unchanged.
- Course Teaching, Ask, preview, and variable replacement observe the new
  canonical value after a course interaction assignment.
- Guest-to-account login keeps the existing canonical source/target/clear
  precedence for phone, email, Google, and password paths.
- Learner onboarding GET returns one direct profile-v2 contract with only
  `blocking` or `hidden`; old sentinel-only users are fresh.
- Completion accepts only the modern payload and never writes legacy state.
- Admin responses contain `config_revision` but no `allowed_variable_keys` or
  numeric `version`, and stored version-only data is not treated as a revision.
- Frontend incompatible responses fail open, existing dialog behavior remains
  unchanged, and no legacy background copy appears.
- Focused backend/frontend tests and all required repository gates pass.

## Idempotence and Recovery

- Re-running a changed canonical background write creates a normal latest-value
  history row while keeping canonical reads deterministic.
- An explicit clear remains authoritative even when historical variable rows
  contain non-empty values.
- Database errors roll back both the user aggregate and variable row through the
  existing unit-of-work boundary.
- Redis session cleanup remains best-effort only after durable profile-v2
  completion or skip; this refactor does not change session keys or TTLs.
- If the frontend receives a cached legacy response, it fails open and requires
  a refresh rather than attempting to unwrap or reinterpret it.

## Interfaces and Dependencies

- Learner APIs:
  - `GET /api/user/learner-profile`
  - `PUT /api/user/learner-profile`
  - `GET /api/user/profile-onboarding`
  - `POST /api/user/profile-onboarding/complete`
  - `POST /api/user/profile-onboarding/skip`
- Admin APIs:
  - `GET /api/shifu/admin/operations/profile-onboarding`
  - `POST /api/shifu/admin/operations/profile-onboarding`
  - preview create/run endpoints under the same resource.
- Persistent fields:
  - `user_users.learner_profile`
  - `user_users.learner_profile_updated_at`
  - existing `VariableValue` history rows
  - existing profile-v2 state rows
- Shared validation:
  - `LEARNER_PROFILE_MAX_LENGTH`
  - canonical content moderation
  - existing profile unit-of-work and row locking
- Explicitly unchanged:
  - database schema and migrations
  - Redis keys, lock order, TTL, replay, and cleanup
  - MarkdownFlow summary generation and guided UX
  - PR3 collection-method surfaces

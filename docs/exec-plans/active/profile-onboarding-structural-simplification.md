# Profile Onboarding Structural Simplification

## Purpose / Big Picture

PR #2308 already provides the intended learner-profile collection and editing
experience. This plan reduces the implementation's concentration of state and
responsibilities without changing any learner-visible behavior, HTTP or SSE
wire contract, Redis lifecycle, persistence semantics, analytics payload, or
rolling legacy compatibility.

The green implementation at commit `499cb2db846f7847666731107bb89865f349f2b0`
is the behavioral baseline. Existing focused and integration tests remain the
characterization suite while responsibilities move behind stable public
facades.

## Progress

- [x] 2026-08-24 CST: Confirmed a clean worktree at the green PR head, reviewed
      the frontend and backend hotspots, and selected an in-PR deep refactor.
- [ ] Split the profile-research runtime behind its existing public API.
- [ ] Isolate legacy onboarding projection and learner/admin route registration.
- [ ] Replace dialog and conversation boolean clusters with explicit state
      models and controller hooks.
- [ ] Extract the course gate and admin configuration controllers.
- [ ] Reorganize tests and reconcile the completed feature plans.
- [ ] Pass focused, static, repository, visual, and GitHub CI gates.

## Surprises & Discoveries

- The implementation is behaviorally well covered; the main risk is illegal
  combinations of independently managed state rather than missing tests.
- Private runtime tests patch implementation paths directly. Those patches may
  move with internal modules, while `flaskr.service.profile_research.api`
  remains the supported boundary.
- The active learner-profile plan already records the direct-to-editor
  completion contract but remains active only because PR #2308 has not merged.

## Decision Log

- Preserve the current HTTP paths, Flask endpoint names, common response
  envelope, SSE event order and payloads, Redis keys and lock order, TTL,
  replay identity, transaction ownership, and best-effort cleanup timing.
- Preserve `LearnerProfileDialog`, `ProfileOnboardingConversation`, the modern
  learner-profile frontend API, and the backend profile-research API module as
  stable facades.
- Use discriminated unions and reducers for UI lifecycle state. Derive dirty,
  fallback, pending, and save eligibility rather than storing parallel flags.
- Keep one dialog instance per account scope. Account scope and open epoch are
  the only boundaries that invalidate async work.
- Keep legacy top-level onboarding fields, old completion, admin aliases,
  revision fallback, dormant `pasted` completion, and legacy `sys_*`
  persistence isolated but intact.
- Do not add a migration, browser draft store, collector chooser, familiar-AI
  UI, paste route, or new analytics event.

## Outcomes & Retrospective

This section will be updated after the refactor and verification complete.

## Context and Orientation

Frontend orchestration currently lives in the profile-onboarding dialog and
conversation components, with course gating embedded in the catch-all course
page. Backend orchestration lives in `service/profile_research/runtime.py`,
while compatibility and V2 state share `service/profile/onboarding.py`; learner
and operator endpoints are embedded in two large route registrars.

## Plan of Work

First preserve the runtime facade while extracting Redis sessions, document
validation, event replay, and provider concerns. Then isolate legacy protocol
code and route registration. Refactor the frontend from the inside out:
conversation model/controller, dialog reducer/controller/views, and finally
host-page controllers. Keep characterization tests green after each layer,
then split test files and fixtures without dropping cases.

## Concrete Steps

1. Add backend internal modules and re-export the existing runtime surface.
2. Break the run path into admission/replay, block execution, and durable
   finalization while retaining the exact lock and error boundaries.
3. Move legacy projection and persistence out of the V2 onboarding module.
4. Register learner and operator profile routes through focused modules.
5. Extract conversation pure adapters and one session-state controller.
6. Add the dialog reducer, selectors, async controller, and presentation views.
7. Extract the course gate and operator configuration/preview controller.
8. Split oversized tests by behavior, reconcile the feature plans, regenerate
   repository docs, and run every required gate.

## Validation and Acceptance

- Existing learner/admin API and SSE contract tests pass without expectation
  changes other than private patch paths and fixture ownership.
- Redis owner/purpose isolation, lock order, TTL refresh, cursor/replay,
  interrupted-stream cleanup, and session deletion behavior remain unchanged.
- Legacy and V2 completion remain strictly separated and retain zero
  cross-protocol writes.
- Dialog loading, collection, explicit review handoff, optimization, save,
  discard, defer, retry, and account-switch races render exactly as before.
- Course blocking, non-blocking, hidden, fail-open, and guided-unavailable gates
  preserve runtime mount behavior and one stable dialog instance.
- Focused pytest and Jest suites, TypeScript, ESLint, Prettier, Ruff check and
  format, translations, architecture, repository harness, diff checks,
  dev-tool validation, and all-files lefthook pass.
- Browser QA at 1280x720, 390x844, 320x568 French, and 844x390 confirms no
  layout, copy, focus, or scrolling change.

## Idempotence and Recovery

Each responsibility move is committed independently after its focused tests
pass. Reverting one refactor commit restores the previous internal layout
without data recovery or migration. No production state is mutated by the
refactor itself.

## Interfaces and Dependencies

- `flaskr.service.profile_research.api` remains the backend public facade.
- `src/cook-web/src/api/learnerProfile.ts` remains the frontend request owner;
  legacy `c-api/user.ts` remains an adapter only.
- Existing Dialog and Conversation props and named exports remain compatible.
- Shared Redis, official MarkdownFlow, MarkdownFlow UI, profile-v2 persistence,
  and the optimizer keep their current versions and responsibilities.

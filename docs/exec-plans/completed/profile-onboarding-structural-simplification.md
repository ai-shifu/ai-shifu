# Profile Onboarding Structural Simplification

## Superseded Compatibility Note (2026-08-25)

The module boundaries produced by this refactor remain current. Its preserved
rolling protocol is no longer current: the isolated legacy projection was
deleted after the rollout window, learner onboarding now uses one direct
profile onboarding contract, and admin revision aliases were removed. See
`canonical-background-onboarding-contract.md` for the replacement contract.

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
- [x] 2026-08-24 CST: Split the profile-research runtime behind its existing
      public API.
- [x] 2026-08-24 CST: Isolated legacy onboarding projection and learner/admin
      route registration.
- [x] 2026-08-24 CST: Replaced dialog and conversation boolean clusters with
      explicit state
      models and controller hooks.
- [x] 2026-08-24 CST: Extracted the course gate and admin configuration
      controllers.
- [x] 2026-08-25 CST: Added pure reducer/model suites while retaining the
      characterization suites, and reconciled the completed dialog plan.
- [x] 2026-08-25 CST: Passed focused, static, repository, visual, and GitHub
      CI gates after rebasing onto `origin/main` at `440bd1244`.

## Surprises & Discoveries

- The implementation is behaviorally well covered; the main risk is illegal
  combinations of independently managed state rather than missing tests.
- Private runtime tests patch implementation paths directly. Those patches may
  move with internal modules, while `flaskr.service.profile_research.api`
  remains the supported boundary.
- The learner-profile dialog plan already recorded the direct-to-editor
  completion contract and was complete independently of the PR merge, so it
  was reconciled and archived during this refactor.
- The oversized characterization suites are valuable behavioral anchors. They
  remain intact instead of being mechanically moved; the new reducer and model
  suites now own pure transition coverage without duplicating integration
  setup.
- Browser viewport overrides recreate the responsive course shell in the local
  harness. Visual checks therefore opened each target state after applying its
  viewport rather than treating the override as an in-session resize test.

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

The refactor separated the profile-research runtime, legacy protocol, learner
and operator routes, guided conversation lifecycle, learner-profile dialog,
course gate, and operator configuration flow behind their existing public
facades. No user-facing copy, layout, interaction, wire contract, persistence,
Redis lifecycle, analytics payload, or deployment behavior changed.

The preserved characterization suites and new pure model suites passed after a
conflict-free rebase onto the latest `main`. Focused backend verification
reported 370 passing tests, focused frontend verification reported 99 passing
tests, and the complete frontend Jest suite reported 1,351 passing tests. Ruff,
TypeScript, ESLint, Prettier, translations, architecture, repository harness,
development-tool, and lefthook gates passed. GitHub backend, frontend, static,
runtime-harness, security, formatting, and review checks were green.

Browser regression covered desktop, mobile portrait, narrow French, and short
landscape layouts across collection, explicit completion handoff, save,
retryable error, and blocking footer states. The dialog retained one scroll
region, fixed shell geometry, full French header text, and the existing focus
and exit behavior.

The main maintenance benefit is explicit ownership: state transitions and
transport lifecycles can now be tested independently while the stable facades
continue to protect callers. Keeping the large characterization suites intact
was preferable to combining test movement with production refactoring; future
changes can split those fixtures incrementally without weakening coverage.

## Context and Orientation

Frontend orchestration now lives behind dialog, conversation, course-gate, and
operator controller hooks, while the public components remain stable facades.
Backend orchestration remains exposed by `service.profile_research.api`, with
Redis sessions, documents, events, providers, legacy projection, and focused
route registration separated behind that boundary.

## Plan of Work

First preserve the runtime facade while extracting Redis sessions, document
validation, event replay, and provider concerns. Then isolate legacy protocol
code and route registration. Refactor the frontend from the inside out:
conversation model/controller, dialog reducer/controller/views, and finally
host-page controllers. Keep characterization tests green after each layer,
then add focused model suites and reconcile the existing feature plans without
dropping characterization cases.

## Concrete Steps

1. Add backend internal modules and re-export the existing runtime surface.
2. Break the run path into admission/replay, block execution, and durable
   finalization while retaining the exact lock and error boundaries.
3. Move legacy projection and persistence out of the current onboarding module.
4. Register learner and operator profile routes through focused modules.
5. Extract conversation pure adapters and one session-state controller.
6. Add the dialog reducer, selectors, async controller, and presentation views.
7. Extract the course gate and operator configuration/preview controller.
8. Add focused reducer/model tests, retain the behavioral characterization
   suites, reconcile the feature plans, regenerate repository docs, and run
   every required gate.

## Validation and Acceptance

- Existing learner/admin API and SSE contract tests pass without expectation
  changes other than private patch paths and fixture ownership.
- Redis owner/purpose isolation, lock order, TTL refresh, cursor/replay,
  interrupted-stream cleanup, and session deletion behavior remain unchanged.
- Retired legacy and canonical completion remain strictly separated and retain zero
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
- Shared Redis, official MarkdownFlow, MarkdownFlow UI, profile onboarding persistence,
  and the optimizer keep their current versions and responsibilities.

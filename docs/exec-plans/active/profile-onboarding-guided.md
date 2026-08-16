# Profile onboarding guided questions (PR2)

## Purpose / Big Picture

Deliver the second learner-profile PR on `sunner/profile-onboarding-guided`. PR1 has merged, so the final publication base is `main` at merge commit `020f0392138e8c1cc9c619add1896a39b86b50fd`. Learners answer the teacher's MarkdownFlow questions, review the generated plain-text learner profile, and can defer only through an explicit low-emphasis action. The release preserves the established legacy onboarding protocol during backend-first rollout.

## Progress

- [x] 2026-08-10 12:20 CST: Confirmed clean PR1 starting commit and created the PR2 branch.
- [x] 2026-08-10 12:25 CST: Audited the split-source delta and identified independent service/UI additions plus mixed compatibility files.
- [x] 2026-08-10 12:55 CST: Rebased the in-progress projection onto PR1 head `f4d963d05`, including the password sign-in canonical merge fix.
- [x] 2026-08-10 13:00 CST: Added the standalone Redis-backed MarkdownFlow runtime and passed its 29 focused tests.
- [x] 2026-08-10 14:05 CST: Projected course gating, the two-step modal, settings rerun, admin preview, i18n, and the rolling dual protocol without reverting PR1 fixes.
- [x] 2026-08-10 14:30 CST: Passed focused backend/frontend regressions, static gates, repository harness checks, and four-viewport browser QA; fixed short-height interaction clipping and the 320-pixel French mobile header found by visual inspection.
- [x] 2026-08-10 14:50 CST: Rebased the independent implementation and review-fix commits onto final PR1 head `34b6260c6`, then verified ancestry and PR1 sign-in/profile-state preservation.
- [x] 2026-08-10 15:05 CST: Pushed ready stacked PR #2308, passed all GitHub checks including the runtime smoke harness, and confirmed the natural review window produced no actionable threads.
- [x] 2026-08-16 13:15 CST: Rebased the seven PR2 commits onto rewritten PR1 head `bffec9712`, preserving the latest nickname, optimizer, password handoff, identity refresh, and shared learner-profile dialog behavior.
- [x] 2026-08-16 14:20 CST: Closed the three naturally reported review findings in independent commits: rejected unanswerable interactions before save/session creation, recovered expired Redis sessions through a fresh guided session, and kept legacy clients compatible with arbitrary official MarkdownFlow variables while persisting only historical `sys_*` fields.
- [x] 2026-08-16 14:25 CST: Passed 374 backend tests (4 skipped), 125 focused frontend tests, TypeScript, ESLint, Prettier, Ruff, translations, architecture, repository harness, `git diff --check`, and the complete lefthook pre-commit gate.
- [x] 2026-08-16 14:28 CST: Re-ran browser QA at 1280x720, 390x844, 320x568 in French, and 844x390 for guided, review, and retryable-error states; retained five screenshots under `/private/tmp/profile-onboarding-pr2-visual/` and removed every temporary harness route and browser cache.
- [x] 2026-08-16 14:43 CST: Rebased all 15 PR2 commits without patch drift onto the rewritten PR1 head `7ea970ae4`, then passed 264 backend regression tests, all 125 focused frontend tests, TypeScript, changed-file lint/format, translations, architecture, repository harness, and the full pre-commit gate on that base.
- [x] 2026-08-16 15:30 CST: Closed the next natural-review group in independent commits: shortened abandoned run locks, classified interrupted SSE database sessions, bounded preview payloads by the publish limit, projected variable-free legacy interactions, made settings refresh best-effort after durable completion, and enforced one shared-Redis active session per owner and purpose.
- [x] 2026-08-16 15:40 CST: Rebased all 22 PR2 commits without patch drift from the final PR1 head onto merged `main` commit `020f0392138e8c1cc9c619add1896a39b86b50fd`; verified exact ancestry and a clean worktree before the final review fixes.
- [x] 2026-08-16 15:50 CST: Closed the three post-merge review findings as independent changes: projected legacy-incompatible official variable markers, serialized skip with canonical completion locks, and protected unsaved profile/nickname edits before a settings rerun.
- [x] 2026-08-16 16:00 CST: Passed 426 backend regressions (4 skipped), 10 frontend suites / 131 tests, TypeScript, changed-file ESLint/Prettier, Ruff/format, translations, architecture, repository harness, `git diff --check`, and the complete all-files lefthook gate on the merged-main base.
- [ ] 2026-08-16: Force-push the rebased ready PR with a lease, close the verified review threads, pass fresh CI, and complete the organic feedback window.

## Surprises & Discoveries

- The provided split source is not descended from the PR1 commit, so copying whole mixed files would regress PR1 and current-main work. Projection must be hunk-based except for independent additions.
- The main checkout and this worktree have identical frontend lockfiles, so its installed `node_modules` can be reused safely for local validation.

## Decision Log

- Use `331a54f531` only as implementation source, never as a wholesale tree replacement.
- Preserve the modern `service/profile/api.py`, `api/learnerProfile.ts`, and shared `ProfileDraftEditor` from PR1.
- Keep the PR2 frontend limited to guided/settings onboarding; preserve the canonical backend's dormant `pasted` completion trigger so PR3 can add import UX without another wire-contract change.
- Preserve the required fresh legacy `should_show=true` contract by projecting only the legacy top-level MarkdownFlow response; persisted/admin/V2 documents remain the official original.
- Treat one active Redis session per owner and purpose as a session-lifecycle invariant, not as a dedicated rate-limit or cohort subsystem.

## Outcomes & Retrospective

PR1 is merged and the complete PR2 commit series now sits directly on the resulting `main` commit without patch drift. Natural review findings have been handled in independent fixes while retaining the dual protocol, official MarkdownFlow source, Redis isolation, PR1 learner-profile/sign-in safeguards, and guided-only frontend. Browser QA and final local gates are complete; publication of the rebased head, fresh CI, and the last organic feedback window remain.

## Context and Orientation

The legacy profile onboarding service lives at `src/api/flaskr/service/profile/onboarding.py`. New MarkdownFlow orchestration is isolated in `src/api/flaskr/service/profile_research/`. HTTP routes and admin configuration are cross-service boundaries. Frontend course gating is in `src/cook-web/src/app/c/[[...id]]`, while reusable dialog UI belongs in `src/cook-web/src/components/profile-onboarding`.

## Plan of Work

1. Copy only standalone source additions and compare every mixed file with PR1 before extracting behavior.
2. Introduce the V2 nested contract and strict complete/skip routing while keeping legacy fields and persistence separate.
3. Replace the local flow parser with MarkdownFlow rendering and a two-step guided/review dialog, then wire course and settings entry points.
4. Validate protocol isolation, runtime session behavior, frontend gates, translations, and build quality.

## Concrete Steps

1. Diff `dd715813e` and `331a54f531` file-by-file; reject source-only unrelated refactors/deletions.
2. Add `profile_research` runtime and summary prompt, route/config hooks, and focused pytest cases.
3. Apply V2 onboarding route/UI hunks, retaining PR1 API and direct editor code.
4. Run focused tests, format/type/lint/harness checks, then commit and publish the stacked PR.

## Validation and Acceptance

- Backend V2 and legacy payloads coexist and do not write each other's state.
- Guided config unavailable/broken is hidden and fail-open.
- Course dialog is guided/review only, has an explicit defer action, and does not close implicitly.
- `profile_research` has no `service.learn` import and uses shared Redis session behavior.
- Focused pytest/Jest plus type/lint and repository checks pass or have recorded environment blockers.

## Idempotence and Recovery

Changes are isolated to this branch. Re-running tests and generators is safe. If a source hunk conflicts with PR1 behavior, retain PR1 and manually apply only the V2 intent after inspecting call sites. No migration is generated or applied.

## Interfaces and Dependencies

- Existing legacy learner endpoints retain top-level `enabled`, `should_show`, `markdownflow`, `allowed_variable_keys`, and `current_values`.
- V2 is nested under `profile_v2` with a contract version and guided/settings actions.
- Redis sessions are scoped by owner and purpose, with one active-session pointer per scope; MarkdownFlow runtime/parser is the authoritative interaction engine.
- Deploy backend before frontend so old clients continue operating during rollout.

# Profile onboarding guided questions (PR2)

## Superseded Contract Note (2026-08-25)

This plan records the backend-first rolling compatibility contract that was
required when guided onboarding first shipped. That release bridge has now
been retired by `canonical-background-onboarding-contract.md`: learner status
is a direct profile onboarding response, legacy completion and sentinel projection are
gone, and the admin API exposes only `config_revision`. The historical details
below remain accurate for the original delivery, not for the current contract.

## Purpose / Big Picture

Deliver the second learner-profile PR on `sunner/profile-onboarding-guided`. PR1 merged at `020f0392138e8c1cc9c619add1896a39b86b50fd`; the branch is synchronized with current `main` at `e65aa770ac19c611233d710d622fa58fddf8f58f`. Learners answer the teacher's MarkdownFlow questions, review the generated plain-text learner profile, and can defer only through an explicit low-emphasis action. The release preserves the established legacy onboarding protocol during backend-first rollout.

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
- [x] 2026-08-16 16:07 CST: Force-pushed with an exact lease, replied to and resolved every verified thread, passed all fresh GitHub checks including backend and runtime harnesses, and observed the final application head for more than seven minutes with no new finding.
- [x] 2026-08-16 16:48 CST: Replayed all 28 PR2 commits onto current `main` at `f86e0cbd7` with a 28/28 equal range-diff, retained the new account-menu and shared profile focus styles, and passed 285 backend regressions, 131 PR2 frontend tests, 32 account-menu tests, TypeScript, lint, format, translations, architecture, and diff checks.
- [x] 2026-08-16 17:15 CST: Closed nine post-sync review findings as independent changes: preserved exact official button values in current, projected label/value choices safely for legacy clients, centralized learner/admin run validation, preserved the original legacy wire layout, normalized completion payloads, aligned the French teacher term, restored virgin admin defaults, kept optional settings status from blocking edits, and rejected oversized answers before making an interaction read-only.
- [x] 2026-08-16 17:22 CST: Passed 305 focused backend regressions, 10 focused frontend suites / 139 tests, TypeScript, changed-file ESLint/Prettier, Ruff/format, three-language translation checks, architecture, repository harness, `git diff --check`, and the complete all-files lefthook gate on `f86e0cbd7`.
- [x] 2026-08-16 17:45 CST: Closed the final post-push Unicode review finding in its own commit by matching the retiring web parser's exact ECMAScript trim set, preserving U+0085 in legacy button values, and passing all 21 dual-protocol regressions plus Ruff, format, dev-tool, and diff checks.
- [x] 2026-08-20 CST: Rebased the complete guided-profile and unified-dialog series onto current `main` at `e65aa770a`, preserving the new absolute backend import layout and current lint rules.
- [x] 2026-08-20 CST: Closed the remaining natural review findings in isolated commits covering fenced legacy projection fallback, answerable configuration limits, durable-save refresh ordering, incomplete SSE recovery, replay TTL renewal, and defer/session-creation races.

## Surprises & Discoveries

- The provided split source is not descended from the PR1 commit, so copying whole mixed files would regress PR1 and current-main work. Projection must be hunk-based except for independent additions.
- The main checkout and this worktree have identical frontend lockfiles, so its installed `node_modules` can be reused safely for local validation.

## Decision Log

- Use `331a54f531` only as implementation source, never as a wholesale tree replacement.
- Preserve the modern `service/profile/api.py`, `api/learnerProfile.ts`, and shared `ProfileDraftEditor` from PR1.
- Keep the PR2 frontend limited to guided/settings onboarding; preserve the canonical backend's dormant `pasted` completion trigger so PR3 can add import UX without another wire-contract change.
- Preserve the required fresh legacy `should_show=true` contract by projecting only the legacy top-level MarkdownFlow response; persisted/admin/current documents remain the official original.
- Treat one active Redis session per owner and purpose as a session-lifecycle invariant, not as a dedicated rate-limit or cohort subsystem.

## Outcomes & Retrospective

PR1 is merged and the complete PR2 commit series sits directly on current `main` without patch drift. Ready PR #2308 passed its full release gates and review window, then synchronized with the subsequent account-menu and profile-focus fixes from `main` without reverting either. Post-sync review hardening keeps exact official button values on the modern wire, matches the retiring parser's ECMAScript whitespace semantics on the legacy wire, prevents lossy legacy persistence, and preserves direct profile editing when optional guided services are unavailable. The delivered behavior retains the rolling dual protocol, official MarkdownFlow source, Redis isolation, PR1 learner-profile/sign-in safeguards, guided-only frontend, and the documented browser QA evidence without adding a migration.

## Context and Orientation

The legacy profile onboarding service lives at `src/api/flaskr/service/profile/onboarding.py`. New MarkdownFlow orchestration is isolated in `src/api/flaskr/service/profile_research/`. HTTP routes and admin configuration are cross-service boundaries. Frontend course gating is in `src/cook-web/src/app/c/[[...id]]`, while reusable dialog UI belongs in `src/cook-web/src/components/profile-onboarding`.

## Plan of Work

1. Copy only standalone source additions and compare every mixed file with PR1 before extracting behavior.
2. Introduce the current nested contract and strict complete/skip routing while keeping legacy fields and persistence separate.
3. Replace the local flow parser with MarkdownFlow rendering and a two-step guided/review dialog, then wire course and settings entry points.
4. Validate protocol isolation, runtime session behavior, frontend gates, translations, and build quality.

## Concrete Steps

1. Diff `dd715813e` and `331a54f531` file-by-file; reject source-only unrelated refactors/deletions.
2. Add `profile_research` runtime and summary prompt, route/config hooks, and focused pytest cases.
3. Apply current onboarding route/UI hunks, retaining PR1 API and direct editor code.
4. Run focused tests, format/type/lint/harness checks, then commit and publish the stacked PR.

## Validation and Acceptance

- Backend current and legacy payloads coexist and do not write each other's state.
- Guided config unavailable/broken is hidden and fail-open.
- Course dialog is guided/review only, has an explicit defer action, and does not close implicitly.
- `profile_research` has no `service.learn` import and uses shared Redis session behavior.
- Focused pytest/Jest plus type/lint and repository checks pass or have recorded environment blockers.

## Idempotence and Recovery

Changes are isolated to this branch. Re-running tests and generators is safe. If a source hunk conflicts with PR1 behavior, retain PR1 and manually apply only the current intent after inspecting call sites. No migration is generated or applied.

## Interfaces and Dependencies

- Existing legacy learner endpoints retain top-level `enabled`, `should_show`, `markdownflow`, `allowed_variable_keys`, and `current_values`.
- current is nested under `wrapped profile status` with a contract version and guided/settings actions.
- Redis sessions are scoped by owner and purpose, with one active-session pointer per scope; MarkdownFlow runtime/parser is the authoritative interaction engine.
- Deploy backend before frontend so old clients continue operating during rollout.

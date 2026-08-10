# Profile onboarding guided questions (PR2)

## Purpose / Big Picture

Deliver the second stacked learner-profile PR on `sunner/profile-onboarding-guided`, based on the final PR1 branch. Learners answer the teacher's MarkdownFlow questions, review the generated plain-text learner profile, and can defer only through an explicit low-emphasis action. The release preserves the established legacy onboarding protocol during backend-first rollout.

## Progress

- [x] 2026-08-10 12:20 CST: Confirmed clean PR1 starting commit and created the PR2 branch.
- [x] 2026-08-10 12:25 CST: Audited the split-source delta and identified independent service/UI additions plus mixed compatibility files.
- [x] 2026-08-10 12:55 CST: Rebased the in-progress projection onto PR1 head `f4d963d05`, including the password sign-in canonical merge fix.
- [x] 2026-08-10 13:00 CST: Added the standalone Redis-backed MarkdownFlow runtime and passed its 29 focused tests.
- [x] 2026-08-10 14:05 CST: Projected course gating, the two-step modal, settings rerun, admin preview, i18n, and the rolling dual protocol without reverting PR1 fixes.
- [x] 2026-08-10 14:30 CST: Passed focused backend/frontend regressions, static gates, repository harness checks, and four-viewport browser QA; fixed short-height interaction clipping and the 320-pixel French mobile header found by visual inspection.
- [x] 2026-08-10 14:50 CST: Rebased the independent implementation and review-fix commits onto final PR1 head `34b6260c6`, then verified ancestry and PR1 sign-in/profile-state preservation.
- [x] 2026-08-10 15:05 CST: Pushed ready stacked PR #2308, passed all GitHub checks including the runtime smoke harness, and confirmed the natural review window produced no actionable threads.

## Surprises & Discoveries

- The provided split source is not descended from the PR1 commit, so copying whole mixed files would regress PR1 and current-main work. Projection must be hunk-based except for independent additions.
- The main checkout and this worktree have identical frontend lockfiles, so its installed `node_modules` can be reused safely for local validation.

## Decision Log

- Use `331a54f531` only as implementation source, never as a wholesale tree replacement.
- Preserve the modern `service/profile/api.py`, `api/learnerProfile.ts`, and shared `ProfileDraftEditor` from PR1.
- Keep the PR2 frontend limited to guided/settings onboarding; preserve the canonical backend's dormant `pasted` completion trigger so PR3 can add import UX without another wire-contract change.

## Outcomes & Retrospective

Implementation, publication, and verification are complete in ready stacked PR #2308. The final stack preserves the legacy learner/admin protocol while adding a nested V2 contract, a direct Redis-backed official MarkdownFlow runtime, and guided/review entry points in courses, settings, and admin preview. Rebase verification passed 262 focused backend tests with 4 skips, 103 focused frontend tests, 61 PR1 regression tests, TypeScript, targeted lint/format, translation parity and usage, architecture with zero new violations, the repository harness, and diff checks. Browser QA covered desktop, portrait mobile, narrow French error, and landscape guided/review states; temporary harness routes stayed outside the committed tree. GitHub backend, contract, lint, Prettier, translation, repository, security, and runtime-harness checks passed, and the organic review-thread audit found no actionable feedback.

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
- Redis sessions are scoped by owner and purpose; MarkdownFlow runtime/parser is the authoritative interaction engine.
- Deploy backend before frontend so old clients continue operating during rollout.

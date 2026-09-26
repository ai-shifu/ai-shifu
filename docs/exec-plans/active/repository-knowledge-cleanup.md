# Repository Knowledge Cleanup

## Purpose / Big Picture

Make repository guidance accurate, discoverable, and economical for coding
agents and new contributors. Repair contradictory current instructions, keep
execution state separate from durable contracts, and add focused checks after
the content is corrected. Deliver separate ready pull requests per problem.

## Progress

- [x] 2026-09-26 00:37 UTC: Rebased the audit on `43e13cdf5` after fetching main.
  PR #2963 already corrects manual startup, Celery processes, frontend API setup,
  and the engineering UTC example. PR #2952 corrects README locale navigation.
- [x] 2026-09-26 00:37 UTC: Verified the local development toolchain and preserved
  local environment files in the managed worktree without exposing their values.
- [x] 2026-09-26 00:37 UTC: Corrected runtime configuration ownership and added local job verification.
- [x] 2026-09-26 00:37 UTC: Corrected the remaining billing UTC specification and serialization reference.
- [x] 2026-09-26 00:37 UTC: Reconciled dashboard routes, DTO fields, scope, UTC filtering, and query guidance.
- [x] 2026-09-26T00:54:50Z: Published the session contract with UTC monthly, disjoint user cohorts.
- [x] 2026-09-26T00:56:37Z: Reconciled chat Skills with the shared ask store, mode-specific audio, and current timeout constants.
- [ ] 2026-09-26 00:37 UTC: Audit current plans and debt, separate snapshots and follow-ups.
- [ ] 2026-09-26 00:37 UTC: Simplify skill routing and inherited module instructions.
- [ ] 2026-09-26 00:37 UTC: Place flat topic documents under their owning knowledge categories.
- [ ] 2026-09-26 00:37 UTC: Extend inventory, skill discovery, lifecycle checks, and health reports.
- [ ] 2026-09-26 00:37 UTC: Record pull requests, verification, and external follow-ups.

- [x] 2026-09-26 04:33 UTC: Recorded concrete audit findings, source paths, delivery links,
  and completion criteria so this plan can be followed without the audit chat.

- [x] 2026-09-26 12:13 UTC: Rebased the runtime configuration delivery on main
  `ae49a0724`, retaining the downstream billing PR ancestry. The existing
  five-file patch was unchanged; seven configuration tests, documentation
  validation, and the full pre-commit gate passed.

## Surprises & Discoveries

The original audit used `fd9f56fa6`; main advanced by 26 commits before execution.
Installation and README findings were already partly fixed. The active-plan
population also grew beyond the original 40; audit the current population,
including those new plans, rather than closing plans from the old counts.

## Decision Log

- 2026-09-26: The user selected distinct users for session-revocation cohorts.
  Use UTC calendar months and disjoint single-only, bulk-only, and both cohorts.
  Preserve existing event payloads and pseudonymous identity.
- 2026-09-26: Keep content repair separate from validation tooling. Use a small
  dependent PR stack when generated indexes or moved references overlap; each
  branch has one reviewable problem and names its parent dependency.
- 2026-09-26: Preserve the layered AGENTS tree and focused skills. Do not add
  alternate instruction routers or automatically archive plans from checkboxes.
- 2026-09-26: Historical records retain historical facts. Current guidance must
  point to a single effective contract; incomplete external acceptance stays open.

## Outcomes & Retrospective

Tracker: https://github.com/ai-shifu/ai-shifu/pull/2964.

In progress. Delivery evidence and unresolved external acceptance will be
recorded here before handoff; code already merged on main is credited rather
than reimplemented.

## Context and Orientation

`AGENTS.md`, `PLANS.md`, and `docs/engineering-baseline.md` own shared guidance.
Backend and frontend skill entry points route to focused procedures. Knowledge
indexes and hygiene checks live under `scripts/`. The initial audit identified
contradictory chat skills, stale dashboard and configuration contracts, mixed
plan/document types, partial inventory coverage, and undated health snapshots.

### Concrete findings and completion criteria

These findings belong to the audit baseline `43e13cdf5`. Paths below are
repository-relative. A delivery PR is evidence of proposed work, not evidence
that it has landed: check its current state before implementing the same fix.
Merged #2963 already corrected startup ports, worker/beat commands and the main
UTC example; merged #2952 repaired the README i18n navigation. Preserve those
fixes, and use `src/i18n/locales.json` for the actual supported language list.

| Work item and delivery | Observed problem and source evidence | Completion criteria |
| --- | --- | --- |
| Runtime configuration — [#2965](https://github.com/ai-shifu/ai-shifu/pull/2965) | `src/web/src/config/ENVIRONMENT_CONFIG.md` mixes runtime settings with `NEXT_PUBLIC_*` build-time examples; it and `src/web/.env.example` still advertise inactive frontend Stripe switches. Compare `src/web/src/config/environment.ts`, `src/web/src/lib/initializeEnvData.ts`, `src/web/src/app/api/config/route.ts`, and `src/api/flaskr/route/config.py`. | State the owning process and build/runtime timing for each supported setting. Distinguish the web `/api/config` address response from backend `/api/runtime-config`, including backend-owned payment capabilities and bootstrap mapping. Keep `INSTALL_MANUAL.md` worker/beat instructions and add acceptance that checks task delivery plus persisted results; a worker ping alone is insufficient. Run the existing environment/route and Celery configuration/entrypoint tests, and identify any untested mapping. |
| Billing timestamps — [#2966](https://github.com/ai-shifu/ai-shifu/pull/2966) | `docs/billing-subscription-design.md` still proposes `default=func.now()` and `onupdate=func.now()`. The implemented contract is `src/api/flaskr/util/datetime.py` plus the `fmt()` sink in `src/api/flaskr/route/common.py`. | Use callable `now_utc` model defaults and updates, without adding SQL-local clock defaults. Document raw DTO datetimes, UTC `Z` serialization and `null` for absent times, with a link to the engineering timestamp contract. Application models are outside this documentation correction. |
| Dashboard contracts — [#2967](https://github.com/ai-shifu/ai-shifu/pull/2967) | `docs/product-specs/teacher-analytics-dashboard.md` imposes a blanket JOIN prohibition that conflicts with current `src/api/flaskr/service/dashboard/funcs.py`. Reconcile it and `docs/product-specs/dashboard-entry-page.md` against dashboard `routes.py`, `dtos.py`, and the web dashboard page/row components. | List the actual entry/detail/learners/follow-up/ratings routes and DTO fields. Describe authorization scope, ordering, bounds and the implemented source-status filtering exception. Match learning-history semantics and actual row actions. Remove the blanket JOIN rule; cite existing tests accurately without turning pagination-parameter checks into a claim of page-slicing coverage. |
| Account-session metrics — [#2968](https://github.com/ai-shifu/ai-shifu/pull/2968) | `docs/exec-plans/active/account-session-analytics.md` describes the single/bulk split as users in one paragraph and events in another; it also carries a distinct adoption denominator. Producers and tests are `src/web/src/components/Settings/SessionManagerModal.tsx`, its test, and `src/web/src/lib/tracking.ts`. | Keep adoption separate from the selected split: UTC calendar month, distinct users with successful revocations as denominator, and disjoint single-only, bulk-only and both groups. Both requires both event kinds. Reuse existing anonymous identity, document loss before identification, and add no event fields. Move the durable contract to product specs and update `device-auth-skill-analytics.md` references. |
| Chat state and playback — [#2969](https://github.com/ai-shifu/ai-shifu/pull/2969) | `src/web/skills/chat-actionbar-ask-placement/SKILL.md`, `chat-element-streaming/SKILL.md`, and `listen-mode-audio-streaming/SKILL.md` retain superseded state/projection/audio instructions. Source owners under `src/web/src/app/c/[[...id]]/Components/ChatUi/` are `useAskStateStore.ts`, `chatUiModeProjection.ts`, `useChatLogicHook.tsx`, and the adjacent `NewChatComp` implementation. | Explain the shared ask store and optional lesson-scope write guard without claiming a stronger hydration-freshness guarantee. Name the active `projectReadModeItems` projection. Separate reading-mode manual playback from the listen-mode backfill queue owned by `NewChatComp`. Document desktop/mobile run-idle limits of 15/60 seconds and the 120-second TTS limit; tie each claim to its actual test and retain coverage gaps explicitly. |
| Plan lifecycle and debt — [#2970](https://github.com/ai-shifu/ai-shifu/pull/2970) | The audited baseline has 46 active documents, beyond the original count of 40. `docs/exec-plans/active/learner-listen-playback-stability.md` mixes playback acceptance and timeline follow-up; account analytics and backend inventory mix durable contracts or snapshots with execution. `docs/exec-plans/tech-debt-tracker.md` still presents the dated 213-commit-site census as current debt. Check merged PR evidence, adjacent tests, and `scripts/check_uow_commit_sites.py` with its committed baseline. | Record a disposition and evidence for every baseline active document. Archive only completed original scope with acceptance; keep external verification or paused work open with a dependency and destination. Split timeline follow-up; put snapshots and superseded journals in history, and durable contracts in specifications. Remove only debt proved eliminated, retaining dated completion evidence. Preserve genuine pending checks when shortening long plans. |
| Skill routing and local rules — [#2971](https://github.com/ai-shifu/ai-shifu/pull/2971) | `src/web/SKILL.md` is a long procedure collection while focused skills and their `README.md` catalogs duplicate discovery data. Subtree `AGENTS.md` files repeat general rules; error fallbacks need a narrow local exception to the shared i18n requirement. Compare the root rules, focused skill frontmatter, and `src/web/src/components/error/`. | Make the frontend entry a scenario router and complete focused skill metadata. Preserve shared producer/consumer coordination in the parent before removing duplicates. Keep local constraints, entry points and validation requirements. Confine static fallback labels to the shared error component; preserve user-visible copy and stable IDs. Catalog automation belongs to the separate tooling PR, so intermediate catalog instructions must describe their actual manual state. |
| Knowledge layout — [#2972](https://github.com/ai-shifu/ai-shifu/pull/2972) | Flat topics such as `docs/billing-subscription-design.md` and `docs/billing-credit-notifications.md` mix technical and product guidance outside their owning directories. Existing discovery uses selected directories and fixed records rather than every tracked Markdown/MDX file. | Move topics to design/product/reference directories by purpose, updating all tracked references together. Classify instructions, skills, current specifications, plans, history, generated content and compatibility aliases separately. Do not assign a new review date merely because a file was moved or one link was repaired. |
| Validation and reports — [#2981](https://github.com/ai-shifu/ai-shifu/pull/2981), [#2974](https://github.com/ai-shifu/ai-shifu/pull/2974) | `scripts/build_repo_knowledge_index.py` contains fixed review dates and creates a tracked health snapshot; existing harness checks do not fully enforce focused-skill discovery, document links or plan lifecycle. Read it together with `scripts/check_repo_harness.py`, `scripts/run_harness_gardening.py`, and existing script tests. | Land blank-review-date compatibility before content starts recording unknown dates. Generate catalogs from focused metadata and cover tracked Markdown/MDX, aliases, local links, required plan sections, archived pending work and deterministic output. Empty active work lists trigger review, not automatic archival. Historical implementation references are exempt from current runtime contracts; document navigation remains checked. Health/gardening output is ignored local/CI evidence with UTC time and HEAD. Tests cover valid input, missing fields/index entries, broken links, historical exceptions and repeated generation. |
| Final evidence — [#2980](https://github.com/ai-shifu/ai-shifu/pull/2980) | Completion cannot be inferred from a merged code PR, an unchecked environment, or a passing test that exercises only a helper. The total plan must retain delivery and verification evidence beyond the chat. | Publish the dependency-ordered PR ledger, actual test/check results, plan dispositions and explicit external acceptance list. Run the tool doctor, documentation harness and full pre-commit gate for each commit-sized change, plus focused behavior tests where documentation describes existing behavior. Repeated index generation must leave no diff. Keep content corrections and validator changes in their owning PRs. |

The external acceptance list must name the required environment, action and
observable result. This documentation task does not itself authorize deployment,
real payments, production account changes, or release of another repository.
When a finding has already been corrected by a merged commit, record that commit
and verify the current source instead of recreating its patch.

## Plan of Work

First correct live operational and behavioral guidance against code and tests.
Then audit plans with source and merge evidence, extract durable contracts and
historical snapshots, simplify instruction routing, and relocate topic docs.
Finally extend the existing generator/checker with regression coverage. Keep
production application behavior outside this documentation-maintenance scope.

## Concrete Steps

1. Use the managed worktree based on current main; preserve source .env files.
2. For each problem, inspect owning instructions and implementation, edit the
   smallest coherent set, update this progress log, and regenerate indexes.
3. Run focused checks and the full pre-commit gate, commit with Changed/Benefit,
   push a task branch, and open a ready PR with its dependency and validation.
4. Run the new metadata/link/lifecycle fixtures and deterministic generation.
5. Publish the final delivery ledger and state CI or external verification limits.

## Validation and Acceptance

The repository harness passes for each batch. Changed documentation agrees
with current code, configuration, and existing tests. Skill discovery lists
all focused skills once. Every tracked Markdown/MDX document is classified;
compatibility symlinks are aliases. Completed plans have no unexplained pending
work. Active plans without pending work produce a review warning, not closure.
Generated committed indexes are deterministic. Health reports identify their
UTC generation time and commit and are not permanent canonical records.
Tooling changes cover valid and invalid metadata, missing links, omitted skills,
plan structure, history exceptions, and repeat generation. Run the tool doctor
and `lefthook run pre-commit --all-files` before each commit-sized delivery.

## Idempotence and Recovery

Regeneration must produce no second diff. Preserve customized local env files.
Move documents with references updated together. Revert a focused PR to undo
that change; dependent PRs must be rebased if their parent is removed. Never
infer deployment completion from a merged PR or a checked progress item.

## Interfaces and Dependencies

Application APIs and analytics event schemas remain unchanged. The session
analytics reporting contract clarifies cohort semantics. Documentation tooling
uses the existing Python, Git, and CommonMark parser dependencies. Generated
metadata describes observed sources rather than inventing review timestamps.

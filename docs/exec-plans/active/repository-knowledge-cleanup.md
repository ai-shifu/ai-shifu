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
- [x] 2026-09-26: Published the session contract with UTC monthly, disjoint user cohorts.
- [ ] 2026-09-26 00:37 UTC: Reconcile chat state, audio, and timeout skills.
- [ ] 2026-09-26 00:37 UTC: Audit current plans and debt, separate snapshots and follow-ups.
- [ ] 2026-09-26 00:37 UTC: Simplify skill routing and inherited module instructions.
- [ ] 2026-09-26 00:37 UTC: Place flat topic documents under their owning knowledge categories.
- [ ] 2026-09-26 00:37 UTC: Extend inventory, skill discovery, lifecycle checks, and health reports.
- [ ] 2026-09-26 00:37 UTC: Record pull requests, verification, and external follow-ups.

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

---
title: Explicit same-owner course memory reads
status: active
owner_surface: learner
last_reviewed: 2026-10-07
---

# Explicit same-owner course memory reads

## Purpose / Big Picture

After merged PRs 3032 and 3033, implement the first complete cross-course memory increment:
an author names a source course and key, and both runtimes read only that
learner's value when both courses have the same owner. The accepted product
boundary is explicit sharing within one owner. The durable contract is
[Explicit Course Memory References](../../references/course-memory-references.md).

## Progress

- [x] 2026-10-07 14:40 UTC: Inspect profile resolution, source storage, publishing,
  ownership, deletion and both runtime readers; verify the installed parser
  supports qualified names and excludes fences/comments.
- [x] 2026-10-07 17:00 UTC: Implement the published-author allowlist, source
  authorization, read-only namespace and resumed-session refresh for both runtimes.
- [x] 2026-10-07 17:00 UTC: Verify actual SQLite reads/writes/deletion, engine
  behavior, source revocation and brief edits: 2,579 learning/profile tests pass
  (one skipped, four subtests); all repository gates pass.
- [x] 2026-10-07 17:08 UTC: Open [PR 3034](https://github.com/ai-shifu/ai-shifu/pull/3034)
  and synchronize sim `b45245c07` (build 369 / Drone 5160). API 2/2 and web 1/1
  are ready; both API replicas pass 19 isolated SQLite/tool checks and match all
  11 runtime module hashes. A fresh internal-course guest completes read, audio
  backfill (1.68 seconds) and listen flows with an unchanged canonical profile.
- [ ] 2026-10-07 17:08 UTC: Evaluate and reply to every independent AI opinion;
  confirm final CI and synchronize any resulting runtime changes to sim.
- [ ] 2026-10-07 17:08 UTC: Wait for the user's main merge, then verify the
  resulting production rollout. Never merge main automatically.

## Surprises & Discoveries

- Variable definitions can be registered by draft content before publication;
  they cannot alone authorize a cross-course read.
- Source values append versions. Deletion markers and current ownership must
  take precedence over old rows and old author revisions.
- A loaded session still contains the original rendered first prompt, even
  after the host reloads current user memory. Brief edits must keep that initial
  section aligned, otherwise a later revocation could leave its old value behind.
- Ordinary courses have no reference-specific database queries. Portable hosts
  retain an empty read-only-prefix default; the app enables the reserved prefix.

## Decision Log

- 2026-10-07: The user accepted proceeding after the recommendation to restrict
  explicitly shared variables to courses with the same owner.
- 2026-10-07: Deliver explicit, qualified read-only source references first;
  preserve source storage and existing learner deletion controls. A shared
  writer and owner-scoped storage are a later PR, not implicit key-name merging.
- 2026-10-07: Use existing tables and parser, with no migration, frontend
  protocol, dependency or environment change. Production remains on 1.0.

## Outcomes & Retrospective

Implementation, local verification and sim acceptance pass. PR 3034 remains open;
AI review, final CI and the user's main merge are pending. This read-only increment does not complete shared writing or the entire
memory milestone.

## Context and Orientation

`profile/funcs.py` resolves values for both runtime memory facades. Variable
definitions are in `var_variables`; values are in `var_variable_values`.
`profile/course_memory.py` owns learner deletion generations. `shifu` draft and
published rows retain revisions and owner business IDs. `learn/agent/run_agent.py`
loads sessions and current values; `deleted_memory.py` can rebuild known initial
author sections without rewriting learner conversation. Portable engine hosts
must retain their existing defaults.

## Plan of Work

Add a profile-owned qualified-reference resolver with a published-author
allowlist, current owner checks and exact newest-row lookup. Reserve the
namespace against all profile writers and local shadowing. Refresh qualified
values and initial substitutions before resumed agent turns. Add opt-in
read-only prefixes to the portable engine and enable them in the app factory.
Use existing source-course learner controls for viewing/deleting originals.

## Concrete Steps

1. Create `profile/course_references.py` and integrate with profile reads/writes.
2. Add agent refresh and read-only engine support, preserving portable defaults.
3. Add actual SQLite, FunctionModel and runtime formatting regressions, including
   denied reads and writes, source deletion and changed ownership.
4. Run tests in conda `ai-shifu`, then dev-tool check and all pre-commit gates.
5. Commit with repository identity, push GitHub origin, open a non-draft PR,
   merge the feature into sim and verify isolated deployed behavior with fresh
   internal-course learners. Reply to all independent AI opinions.

## Validation and Acceptance

Only explicitly published same-owner references yield the requesting learner's
latest exact value. Local same-name keys, global rows and another learner's
values never substitute for the named source. Removal, deletion, ownership
change and failed authorization remove the initial request copy on resume.
Attempts to store a qualified key never change source or destination storage.
Ordinary courses retain their existing behavior. All local gates and final CI
must pass, and sim remains 2.0 while production remains 1.0.

## Idempotence and Recovery

Reads create no rows. Reference removal does not delete source values. Repeated
denied writes are no-ops. Tests use owned temporary SQLite data; deployment
acceptance uses fresh internal-course learners. No real learner reset, production
configuration write or shared database migration is needed.

## Interfaces and Dependencies

Keep existing profile DTOs, memory facade and SSE envelopes. Add only optional
engine read-only-prefix configuration with an empty portable default. Reuse
the installed MarkdownFlow parser, SQLAlchemy and current gateway. No dependency
or database migration is introduced.

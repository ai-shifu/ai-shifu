---
title: Keep custom learner variables within their course
status: active
owner_surface: learner
last_reviewed: 2026-10-08
---

# Keep custom learner variables within their course

## Purpose / Big Picture

Apply the user's revised policy: system-recognized profile fields may follow a
learner between courses; ordinary variables cannot. Remove the explicit read and
named-answer exceptions introduced by #3034 and #3042. The durable contract is
[Variable scopes](../../references/course-variable-scopes.md).

## Progress

- [x] 2026-10-08 06:03 UTC: Verify #3042 manual merge and both regional deployments;
  135 isolated checks / 26 hashes per sampled new replica; production remains 1.0.
- [x] 2026-10-08: User explicitly cancels cross-course custom-variable sharing,
  including teacher-declared exceptions. Stop the proposed shared model-note work.
- [x] 2026-10-08: Remove cross-course resolvers, source writer and engine answer
  grants. Reject retired aliases, remove custom-global fallback and discard saved
  cross-course snapshots while keeping pending answers/history.
- [x] 2026-10-08 07:36 UTC: Full learning/profile suite: 2,718 passed, 1 skipped,
  4 subtests. Retired sharing feature tests were replaced with isolation and
  compatibility assertions. Isolated deployed-module probe: 109 checks / 22 hashes,
  zero provider calls/shared-database writes. Negative mutations restoring global
  fallback, skipping saved-snapshot cleanup and allowing alias profile writes fail
  3 / 8 / 5 cases; original source bytes restored. Developer tools, architecture,
  transaction sites and every repository pre-commit gate pass.
- [ ] 2026-10-08: Publish one non-draft PR, synchronize exact source tree to sim,
  verify replicas/live classroom, reply to every AI opinion and verify final CI.

## Surprises & Discoveries

Removing qualified syntax alone is insufficient: the legacy value helper falls
back from a missing course key to a same-named global custom value. Scope matching
must be exact. Old saved sessions can also retain aliases in their initial
structured prompt after current memory has changed; clear those snapshots too.

## Decision Log

- 2026-10-08: Global scope is selected by the existing profile-label registry,
  not by a name prefix or a model-selected scope. Keep canonical profile mappings.
- 2026-10-08: Delete cross-course read/write implementations and engine grants;
  keep namespace refusal and old pending-answer compatibility. No feature flag.
- 2026-10-08: Preserve original answers, later classroom history and existing
  source values; do not rewrite earlier shared writes or delete learner data.
- 2026-10-08: Diagnostic multi-course storage inventory is not runtime permission;
  normal lessons and follow-ups use the supported scoped facade only.

## Outcomes & Retrospective

Local implementation, full regression, negative checks and repository gates pass.
Publication and deployed acceptance are pending; the PR acceptance discussion will
record final CI and sim evidence before handoff. Shared model notes and owner-wide custom memory
are cancelled by product decision, rather than remaining milestone requirements.
Semantic summaries and full memory quality/cache/cost acceptance remain separate.

## Context and Orientation

`profile/funcs.py` resolves registered global fields and exact course values.
`profile/course_references.py` now only reserves retired names. The shared-answer
resolver/writer is removed. `run_agent.py` no longer grants cross-course answers;
its compatibility cleanup uses `agent/course_references.py` and the existing
initial-prompt refresh helper. Engine defaults and SSE shape are unchanged.

## Plan of Work

Verify both runtimes' reads, supplements, settings/profile/memory writes, model
notes and named answers, follow-ups and template formatting. Cover same-owner
courses, same-name local values, global-custom absence, canonical system fields,
saved aliases and old pending answers. Publish, deploy sim and audit AI/CI.

## Concrete Steps

Use conda ai-shifu for backend tests. Run targeted scope and host tests, then all
learning/profile tests including vendored engine tests. Negatively restore a
scope bypass and skip saved-snapshot cleanup to prove regressions. Stage source
and documentation before generating knowledge indexes and running developer-tool,
architecture, transaction-site and full pre-commit gates.

## Validation and Acceptance

Course B cannot obtain course A's custom value from declarations, same-name keys,
model tools, supplements or follow-ups. Registered nickname/language and global
system labels still work; ordinary answers/notes still persist within their own
course. Missing custom values do not fall back globally. Old pending answers
remain exact without a source or local-alias write. No migration or provider call
is needed to enforce scope. Sim is 2.0, both production regions remain 1.0.

## Idempotence and Recovery

Retired-name filtering and saved-prompt cleanup are idempotent. Historical values
remain in their original courses. Retrying rejected shared writes never creates
aliases. Do not roll back to a sharing-enabled version without a product decision.
Main merge remains manual after the independently validated sim deployment.

## Interfaces and Dependencies

Remove `memory_answer_keys` from the internal engine run/deps contract and update
all producers/consumers. Preserve the `reference_text` reader argument temporarily
for call-site compatibility; it grants no storage scope. No schema, new dependency,
environment variable or frontend/SSE contract changes.

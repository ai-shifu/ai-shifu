---
title: Recall authorized learner memory on demand
status: completed
owner_surface: learner
last_reviewed: 2026-10-08
---

# Recall authorized learner memory on demand

## Purpose / Big Picture

Let 2.0 teaching recover relevant stored facts omitted from the initial memory budget.
Read only the host-authorized current snapshot, preserve complete values and keep the
existing admission, deletion, course-reference and finish boundaries. The durable contract
is [MarkdownFlow Memory Recall](../../references/markdownflow-memory-recall.md).

## Progress

- [x] 2026-10-08 02:57 UTC: Inspect engine tools, prompt projection, host snapshot refresh,
  deletion and read-only course references. Verify PR 3038 merged and production stayed 1.0.
- [x] 2026-10-08 02:57 UTC: Add bounded key discovery/exact reads and explicit host opt-in.
- [x] 2026-10-08 02:57 UTC: Verify real engine/SQLite lifecycle, scope and byte boundaries.
  Focused suite passes 74 tests before the final admission regression. Removing result bounds,
  collected-key exclusion and host opt-in fails 2 / 2 / 3 cases; restore exact source bytes.
- [x] 2026-10-08 03:00 UTC: Complete learning/profile regression, including all vendored
  engine tests: 2681 passed, 1 skipped, 4 subtests passed. Add an explicit admission
  regression and verify real GatewayModel total budgeting after recall.
- [x] 2026-10-08 03:00 UTC: Developer-tool check and all repository gates passed.
  Publish source d858ebc4a as non-draft PR 3039.
- [x] 2026-10-08 03:05 UTC: Synchronize exact PR tree to sim 5c782816a. Build 382
  and deployments 1872/1873 succeeded; API 2/2 and web 1/1 Ready. Both API pods
  passed 72 isolated checks and 21 hashes. A separate real Ark model discovered,
  read and used an omitted exact fact; original memory unchanged, isolated SQLite only.
  Real HTTP read/backfill/listen/repeated Ask and browser current-answer echo passed.
- [x] 2026-10-08 03:19 UTC: Push review clarification 22848a80b and reply to every
  independent opinion. Final technical CI passed. Final sim 8af9e7c3e and merged main
  2ac1c9a42 have the exact reviewed tree. Builds 383/384 and CN/US/sim deployments
  succeeded; both sim pods and one new production pod per region passed 72 isolated
  checks and 21 hashes. Production remains 1.0; sim remains deployment-wide 2.0.

## Surprises & Discoveries

The initial memory section deliberately omits whole entries. Exact author substitutions
remain complete, so recall must not be presented as automatic input-budget recovery.
The host refreshes deleted keys and cross-course authorization before each turn; a tool
must not query persistence itself or expose the main script's re-collected old answers.

## Decision Log

- 2026-10-08: Opt in only at the AI-Shifu 2.0 factory; preserve portable defaults.
- 2026-10-08: One tool lists keys in pages of at most 20 or reads one exact key.
  Limit the entire result to 8192 compact UTF-8 JSON bytes; refuse oversized values whole.
- 2026-10-08: Use live turn-owned scope dictionaries, with session values winning.
  Retain host refresh and the existing total-input/request/tool-call backstops.

## Outcomes & Retrospective

Implementation and local acceptance pass. New coverage adds 29 cases across actual
engine calls, host SQLite lifecycle and real gateway budget enforcement. Mutation
checks fail 2 / 2 / 3 cases when result bounds, exclusions or host opt-in are removed.
Deployed sim acceptance passed, including an actual provider call with synthetic data.
Devin found no issues. CodeRabbit's publication-time clarification and separate progress
finding are accepted; its docstring percentage warning does not override the repository's
behavior-test exemption. Every independent opinion received a disposition reply; final technical CI and
post-merge verification passed. The first
runtime-harness attempt failed at Docker Hub image metadata HTTP 502, before application
tests; the failed job was rerun. Semantic retrieval, history compression,
shared writes, token-budget policy and human course acceptance remain separate increments.

## Context and Orientation

`Engine` offers built-in tools with turn-owned `Deps`. `run_agent._load_or_start` refreshes
the learner/course snapshot, tombstones and read-only references before a turn. The single
factory in `lesson_entry` enables the capability for learners and previews. Existing host
event handling keeps tool results out of classroom text and persists only memory updates.

## Plan of Work

Implement exact reads and bounded key discovery, add opt-in instructions, cover actual
model requests and storage isolation, then publish and verify the deployed sim version.
Keep raw answers, original history, database schema, configuration and providers intact.

## Concrete Steps

Run new engine and SQLite cases, then the complete vendored engine and learning/profile
suite. Mutate the enabled factory/registration to prove coverage. Run developer-tool and
all pre-commit checks, commit/push, create a non-draft PR, attach it and synchronize sim.
Audit review bodies, inline and issue comments and reply in the original discussion.

## Validation and Acceptance

Recover an omitted permitted fact without writes or truncation. Page keys without repeats;
handle Unicode/escaping, exact limits, oversized values/names and invalid offsets. Exclude
re-collected answers and unavailable keys. Respect finish, refreshed deletions/references,
learner/course isolation, preview opt-in and portable defaults. Verify result bytes and
deployed source identity; do not claim recall solves overall long-history input exhaustion.

## Idempotence and Recovery

The tool is read-only and introduces no migration. Reverting the opt-in removes the tool
from future requests; stored tool history and complete original memory remain compatible.
Use isolated SQLite for deployment probes, never shared production database writes.

## Interfaces and Dependencies

Add `Engine(memory_recall=False)`, turn-only excluded keys and a `recall` function tool.
Keep `Session` storage and the SSE contract unchanged. No new dependency or environment key.

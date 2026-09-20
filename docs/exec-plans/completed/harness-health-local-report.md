---
title: Keep harness health reports out of pull request conflicts
---

## Purpose / Big Picture

Stop unrelated pull requests from conflicting over repository-wide health
counts. Keep the report available locally and in CI without committing it.

## Progress

- [x] 2026-09-20 UTC: Verify report producers, consumers and conflict history.
- [x] 2026-09-20 UTC: Separate the optional report from tracked knowledge docs.
- [x] 2026-09-20 UTC: Update CI publication and local usage documentation.
- [x] 2026-09-20 UTC: Pass six focused report regressions, 28 instruction tests,
  real missing/stale-report checks, architecture checks and the UOW ratchet.
- [x] 2026-09-20 UTC: Complete `lefthook run pre-commit --all-files` with
  all checks passing; archive this implementation plan.

## Surprises & Discoveries

Two branches can make the same count change and merge without a text conflict,
yet leave an incorrect total. Merge strategies cannot calculate the report.
The checker currently requires both report existence and exact generated text.

## Decision Log

- 2026-09-20: Ignore only the health report; keep architecture and transaction
  baselines under version control because they are inputs to policy checks.
- 2026-09-20: Keep the existing generator's default outputs and add
  `--health-only` to refresh the report without rewriting tracked indexes.
- 2026-09-20: Show the report in CI summaries and artifacts. Local checks read
  source files directly and accept a missing or stale report.

## Outcomes & Retrospective

The report can be missing or stale without weakening source validation.
`--health-only` updates the snapshot without rewriting or creating indexes;
default generation still refreshes both. Local Git ignores the report while
retaining both policy baselines. Workflow YAML validation passes and both CI
workflows publish the report; remote workflow execution follows PR creation.

## Context and Orientation

`scripts/build_repo_knowledge_index.py` owns the report and indexes;
`scripts/check_repo_harness.py` checks tracked documents and source assets.
Static Checks and Harness Gardening run the generator in GitHub Actions.

## Plan of Work

Separate tracked outputs from the optional health snapshot. Remove report
tracking and inventory requirements, document its snapshot semantics, and
publish the current CI report without weakening underlying checks.

## Concrete Steps

1. Update the generator, checker and exact report ignore rule.
2. Update workflow summaries/artifacts and repository navigation.
3. Add focused regressions, regenerate indexes and run repository checks.

## Validation and Acceptance

A checkout with no report passes the harness. A stale report does not affect
checks, but missing required assets and stale tracked indexes still fail.
`--health-only` reflects changed source counts and leaves indexes untouched.
The report is ignored by Git; both JSON baselines remain tracked. Both affected
workflows publish the report and run the required repository checks.

## Idempotence and Recovery

Report generation can be repeated and the ignored output can be deleted at any
time. Existing branches may need one modify/delete conflict resolution when
they adopt the change. Restore the generator/checker/tracking contract together
if reverting; do not refresh policy baselines as part of this change.

## Interfaces and Dependencies

Use the standard-library generator CLI. Reuse the existing GitHub Actions
artifact action and job summary file. No runtime application dependencies or
business behavior change.

---
title: Environment-wide MarkdownFlow 2.0
status: active
owner_surface: learner
last_reviewed: 2026-10-07
---

# Environment-wide MarkdownFlow 2.0

## Purpose / Big Picture

Enable every sim course with an environment switch while production retains
1.0. The durable contract is [runtime selection](../../references/markdownflow-runtime-selection.md).
The user requested this insertion after PR #3030 merged.

## Progress

- [x] 2026-10-07 CST: Verify #3030 merged and inspect runtime/configuration owners.
- [x] 2026-10-07 CST: Replace course membership with a default-off deployment flag.
- [x] 2026-10-07 CST: Pass 129 routing/configuration tests, 2617 learning/profile
  tests (one skipped, four subtests), and repository gates.
- [x] 2026-10-07 CST: Open application PR #3031 and deploy-config PR #36.
- [x] 2026-10-07 CST: Roll out sim-283fde4, remove the old list and verify both
  API replicas route every identified course to 2.0. Six Chinese and two US
  production replicas still select 1.0 in raw and initialized registry paths.
- [x] 2026-10-07 CST: Pass fresh-guest reading, audio backfill (1.59 seconds),
  listen-mode completion and unchanged canonical profile checks.
- [x] 2026-10-07 CST: Reply to the available Devin opinion with the existing
  explicit-Reset transition contract; retain deployment-wide routing.
- [x] 2026-10-07 CST: Accept the CodeRabbit stale-comment correction, update
  adjacent runtime documentation and reply after pushing validation.
- [ ] 2026-10-07 CST: Complete external CI checks and human main merges.

## Surprises & Discoveries

The registry returns raw strings before startup and typed booleans afterwards.
The sim Deployment consumes production's shared ConfigMap and Secret. Its
pipeline-managed image can differ from the versioned manifest; applying the
whole manifest could overwrite unrelated live state.

## Decision Log

- 2026-10-07: Use `FLOW_ENGINE_V2_ENABLED`, default false; remove allowlist routing.
- 2026-10-07: Configure sim on its own Deployment, without shared database writes.
- 2026-10-07: Preserve the Ask side path and existing runtime session handling.
- 2026-10-07: Stage the flag before the binary upgrade and remove the old list afterwards.

## Outcomes & Retrospective

Local validation and sim acceptance passed; production remains on 1.0.
Both sim replicas match all three changed runtime module hashes. The two-phase
configuration patch preserved the live image and model-list drift. Existing
pre-checkpoint history still requires explicit Reset before regeneration or
earlier-answer changes, as the existing localized error and rewind tests specify.
External CI/review completion is tracked on PR #3031; human main merges remain
outside this agent's authority.

## Context and Orientation

`src/api/flaskr/service/learn/agent/routing.py` selects the lesson runtime;
`flaskr/common/config.py` owns environment declarations. `runscript_v2.py`
excludes Ask from 2.0. The deployment-config repository owns
`k8s/cn/sim/sim-api-deployment.yaml` and must carry the sim-only override.

## Plan of Work

Replace the registry declaration and routing predicate, regenerate Docker env
examples, and test startup/initialized paths and all-course admission. Validate
the companion sim configuration and apply only its changed environment entries
after comparing live drift. Integrate the reviewed source into sim, verify both
replicas and production defaults, then record acceptance.

## Concrete Steps

Activate conda `ai-shifu`. Run focused routing/configuration tests, full
learning/profile tests, dev-tool checks and `lefthook run pre-commit --all-files`.
Stage new docs before `python scripts/build_repo_knowledge_index.py`. Open
focused PRs; do not merge them automatically. Integrate source into `origin/sim`
and wait for its build and rollout. Validate Kubernetes dry runs and diff before
applying a minimal repository-derived environment patch.

## Validation and Acceptance

With the flag true, old, unlisted and new course identifiers select 2.0. With
the flag unset/false/malformed they select 1.0, regardless of the old list.
Reading/listening and regeneration retain existing dispatch; Ask stays 1.0.
Both sim API replicas must have matching source and the true flag. Chinese and
US production must remain disabled. Live read/listen acceptance uses only a
fresh temporary learner in the fixed internal course, preserving its profile.
Every actionable AI review opinion receives a reply in its original thread.

## Idempotence and Recovery

The environment patch is idempotent; no schema or shared data migration is
needed. Roll back with the documented deployment flag. Restore the old list
only when also rolling back the binary to the allowlist implementation.

## Interfaces and Dependencies

Keep `uses_agent_engine(shifu_bid)` compatible with existing callers. The only
new operator interface is the registered bool `FLOW_ENGINE_V2_ENABLED`; it
replaces the retired list variable. No dependency versions change.

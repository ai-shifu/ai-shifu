# Docker Engineering Rules

This file owns engineering rules for the Docker surface under `docker/`,
including compose files, local entry scripts, nginx configs, and deploy-facing
environment examples.

## Scope

- Apply this file to `docker/`, especially `docker-compose*.yml`,
  `dev_in_docker.sh`, nginx configs, and `docker/.env.example.full`.

- Docker engineering conventions live in the
  [engineering baseline](../docs/engineering-baseline.md), especially:
  [Architecture](../docs/engineering-baseline.md#architecture),
  [CI/CD And Release Workflow](../docs/engineering-baseline.md#cicd-and-release-workflow),
  [Environment Configuration](../docs/engineering-baseline.md#environment-configuration),
  and [Troubleshooting](../docs/engineering-baseline.md#troubleshooting).

- This directory defines three distinct container modes: local dev with mounted
  source, freshest published images, and pinned release deployments.

- Docker changes often affect backend and frontend boot assumptions together,
  so treat them as cross-surface changes when service wiring or image semantics
  move.

## Do

- Inspect the affected compose files, entry scripts, and related app boot
  assumptions together before changing Docker behavior.

- Keep `docker-compose.dev.yml`, `docker-compose.latest.yml`, and
  `docker-compose.yml` semantically distinct: local-mounted dev, freshest
  published images, and pinned release deployment.

- Preserve image names, tag semantics, env-file expectations, and service boot
  ordering unless the corresponding release or app configuration model also
  changes.

- Keep `docker/.env.example.full` aligned with backend config changes and the
  environment-variable guidance documented elsewhere in the repo.

- Validate compose changes with `docker compose ... config` and cross-check
  release-facing image behavior against GitHub build and release workflows.

## Avoid

- Do not bake secrets or environment-specific credentials into compose files
  or Docker helper scripts.

- Do not collapse dev, latest, and pinned compose roles into one file unless
  the deployment model itself changes.

- Do not change container image tags, service names, or startup semantics
  without checking the corresponding GitHub release and build workflows.

- Do not move backend or frontend boot assumptions in Docker without
  coordinated app-surface updates and verification.

## Commands

- `cd docker && docker compose -f docker-compose.dev.yml config` validates the
  local-dev compose file after edits.

- `cd docker && docker compose -f docker-compose.dev.yml up -d` should bring up
  the default app plus observability stack together for Phase 2 harness work.

- For parallel worktrees, set a stable compose project name and override host
  ports before starting the dev stack. Use the pattern
  `ai-shifu-<worktree-slug>` for the project name; CI uses
  `ai-shifu-runtime-harness`. For example:
  `cd docker && docker compose -p ai-shifu-$(basename "$(git rev-parse --show-toplevel)" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9_-' '-') -f docker-compose.dev.yml up -d`.
  Override ports with `AI_SHIFU_WEB_PORT`, `AI_SHIFU_API_PORT`,
  `AI_SHIFU_MYSQL_PORT`, `AI_SHIFU_REDIS_PORT`, `AI_SHIFU_GRAFANA_PORT`,
  `AI_SHIFU_LOKI_PORT`, `AI_SHIFU_TEMPO_PORT`,
  `AI_SHIFU_TEMPO_OTLP_HTTP_PORT`, `AI_SHIFU_OTEL_GRPC_PORT`, and
  `AI_SHIFU_PROMETHEUS_PORT`.

- `cd docker && docker compose -f docker-compose.latest.yml config` validates
  the freshest-published-image compose file after edits.

- `cd docker && docker compose -f docker-compose.yml config` validates the
  pinned-release compose file after edits.

- `cd src/api && python scripts/generate_env_examples.py` refreshes
  `docker/.env.example.full` after backend config changes that alter Docker
  env expectations.

## Tests

- Run `docker compose ... config` for each touched compose file and review the
  rendered output for service names, env files, and image references.

- When image or release semantics change, cross-check the compose references
  against GitHub build and release workflows before closing the task.

- When startup commands, entrypoints, or mounts change, review the affected
  backend and frontend boot assumptions and note any runtime smoke checks that
  were not exercised locally.
- When observability services change, verify Grafana, Loki, Tempo, Prometheus,
  and the OTEL collector all stay internally reachable from the dev stack.

- When only Docker-side docs or AI instructions change, run
  `python scripts/check_repo_harness.py` and note that containers were not
  started.

## Related Skills

- `SKILL.md` is the repository-level skill routing index.

- `src/api/SKILL.md` and `src/cook-web/SKILL.md` remain the right entry points
  when Docker changes are tightly coupled to backend or frontend behavior.

- Keep durable Docker rules here; move repeated deployment or release
  runbooks into focused skills only when they become a recurring workflow.

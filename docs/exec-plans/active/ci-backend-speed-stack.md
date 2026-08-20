# Speed Up Backend Pull Request Feedback

## Purpose / Big Picture

Backend-facing pull requests currently wait on two avoidable sources of repeated
work: the Runtime Harness writes both Docker image caches into one GitHub
Actions cache scope, and the Backend Tests workflow keeps one immutable
pytest-testmon cache for the lifetime of a branch. This stacked change makes
each cache advance independently so later CI runs can reuse the work completed
by earlier runs. It also keeps frontend dependency installation reusable when
only frontend source files change.

The observable outcome is that a warm Runtime Harness run restores separate API
and Cook Web image caches, while a later commit on the same pull request restores
the most recently completed testmon state instead of the first cache written for
that branch.

## Progress

- [x] 2026-08-20 12:00 CST: Inspected current main workflows and recent GitHub
  Actions step timings.
- [x] 2026-08-20 12:10 CST: Confirmed both runtime image builds use the same
  default GitHub Actions cache scope and import the same cache manifest.
- [x] 2026-08-20 12:15 CST: Gave the API and Cook Web image builds independent
  cache scopes.
- [ ] 2026-08-20 12:20 CST: Reorder the Cook Web development image so dependency
  installation precedes source copying.
- [ ] 2026-08-20 12:25 CST: Make each Backend Tests run save a new testmon cache
  and restore the newest compatible cache.
- [ ] 2026-08-20 12:30 CST: Validate and publish the three-PR stack.

## Surprises & Discoveries

- The runtime workflow already uses the Docker GHA cache backend, but both bake
  targets inherit its default `buildkit` scope. Docker documents that multiple
  images writing the same scope overwrite one another.
- Recent runtime logs show both image targets importing the same cache manifest,
  followed by dependency installation work instead of cache hits.
- The branch-level testmon cache key is immutable. GitHub Actions does not update
  an existing cache entry, so later commits keep restoring the state saved by the
  first completed run on that branch.
- The local worktree does not have a Docker CLI, so the bake definition cannot be
  expanded locally. Workflow parsing and repository checks are the local gate;
  the first pull request's Runtime Harness run is the live cache-scope gate.

## Decision Log

- Decision: deliver three narrow stacked pull requests instead of one workflow
  rewrite. Rationale: each cache correction has a distinct rollback boundary and
  can be measured independently in GitHub Actions.
- Decision: do not add pytest-xdist in this stack. Rationale: parallelizing the
  suite also changes test isolation and coverage aggregation, so it needs its own
  compatibility investigation after these cache fixes land.
- Decision: keep `mode=min` for the Docker caches. Rationale: the confirmed defect
  is scope collision; changing cache breadth at the same time would make the
  result harder to attribute and may increase cache storage pressure.

## Outcomes & Retrospective

Implementation is in progress. Record measured CI outcomes here after each pull
request runs.

## Context and Orientation

`.github/workflows/runtime-harness.yml` builds `ai-shifu-api-dev` and
`ai-shifu-cook-web-dev` with `docker/bake-action`. The services are defined in
`docker/docker-compose.dev.yml`. The API image uses `src/api/Dockerfile`; the
Cook Web development image uses `src/cook-web/Dockerfile_DEV`.

`.github/workflows/backend-tests.yml` restores `src/api/.testmondata` and
`src/api/.pytest_cache`, installs the backend dependencies, and uses
pytest-testmon for pull request selection. GitHub Actions caches are immutable:
a successful run must write a unique key if its updated testmon state is to be
available to a later run.

## Plan of Work

First, replace the wildcard Docker cache settings with target-specific settings
whose scopes identify the API and Cook Web images. Verify the resolved bake
definition contains two different `cache-from` and `cache-to` scopes.

Second, move Cook Web's dependency installation immediately after copying its
package manifests and use the lockfile-enforcing install command. Verify a
source-only edit leaves the dependency layer cache key unchanged.

Third, suffix the exact testmon cache key with the run commit SHA and add restore
prefixes ordered from the current pull request to main and then the generic
Python cache. Verify two different SHAs produce different exact keys while
sharing the same restore prefix.

## Concrete Steps

1. Edit `.github/workflows/runtime-harness.yml` on
   `sunner/ci-runtime-cache-scopes` and validate the bake definition.
2. Stack `sunner/ci-runtime-web-dependency-layer` on the first branch, edit
   `src/cook-web/Dockerfile_DEV`, and validate the Dockerfile and repository
   harness.
3. Stack `sunner/ci-testmon-rolling-cache` on the second branch, edit
   `.github/workflows/backend-tests.yml`, and validate the cache expressions and
   repository harness.
4. Run `python scripts/check_dev_tools.py`, the relevant harness checks, and
   `lefthook run pre-commit --all-files` before publishing.
5. Push all three branches and create ready pull requests whose bases form the
   same order as the branch stack.

## Validation and Acceptance

- `docker buildx bake --file docker/docker-compose.dev.yml --print` with the
  workflow's target-specific overrides shows distinct scopes for both images.
- `src/cook-web/Dockerfile_DEV` copies package manifests and installs with
  `npm ci --ignore-scripts` before copying application source.
- The Backend Tests exact cache key includes the current commit SHA, and its
  first restore prefix selects the newest cache for the current PR plus the same
  dependency hash.
- Workflow YAML parses, `git diff --check` passes, repository harness validation
  passes, and the three ready pull requests have the intended stacked bases.

## Idempotence and Recovery

The workflow edits are declarative and safe to rerun. If a Docker cache scope is
misspelled, no product artifact is corrupted; the next CI run merely rebuilds
that image. Reverting the first pull request restores the previous shared scope.
If a testmon restore prefix is wrong, pytest still runs from an empty or older
cache and remains correct, only slower. Each concern is isolated in its own
commit and pull request so the stack can be rolled back from the top.

## Interfaces and Dependencies

The stack depends on GitHub Actions cache semantics, Docker Buildx's `gha` cache
backend, `docker/bake-action@v7`, `actions/cache@v4`, pytest, and pytest-testmon.
It does not change application runtime APIs, environment variables, database
schemas, or release image publication.

# API capacity observability

## Purpose / Big Picture

Measure complete SSE lifetimes and aggregate all Gunicorn workers before testing a reduction from six API replicas. Existing request timing stops at response headers, and the default Prometheus registry exposes only the worker serving a scrape. Neither measurement supports a replica decision.

## Progress

- [x] 2026-10-13 17:02 CST: Inspected production worker configuration, metrics, lifecycle tests, and the deployment Dockerfile.
- [x] 2026-10-13 17:05 CST: Implement isolated Gunicorn multiprocess storage and complete SSE lifecycle metrics.
- [x] 2026-10-13 17:08 CST: Verify fork aggregation, cleanup, cancellation, and existing runtime contracts.
- [x] 2026-10-13 17:15 CST: Published ready PR #3129 and recorded production acceptance separately.
- [x] 2026-10-13 17:19 CST: Removed route-parameter reflection from a test-only route after CodeQL review.
- [ ] 2026-10-13 17:02 CST: After merge, verify production metrics and connect continuous collection before replica changes.

## Surprises & Discoveries

The production Dockerfile copies `flaskr/` and `gunicorn.conf.py`, but does not copy arbitrary top-level Python modules. The bootstrap therefore lives in `flaskr/metrics_runtime.py`; importing `flaskr` has no application initialization side effects. Preload and the existing gthread/gevent guard must remain intact. Metrics Server provides instantaneous resources, while historical cloud monitoring access is still unconfirmed.

## Decision Log

- Use a private temporary directory per Gunicorn master by default, prepared before importing prometheus_client. Separate master generations during USR2 upgrades; remove only directories owned by the exiting master.
- The generated template comments out an empty multiprocess assignment because the Prometheus client tests presence, including empty strings. Explicit `PROMETHEUS_MULTIPROC_DIR` must be dedicated, writable, and free of stale database files. Do not delete operator-owned data. Fail startup if Prometheus was imported before the bootstrap, rather than publish misleading single-worker statistics.
- Preserve existing response-header HTTP timing and tracing. Add separate active-request, SSE-active, first-chunk, stream-duration, and bounded-outcome metrics. First chunk is not first model token.
- Wrap only streamed `text/event-stream` bodies, without buffering or altering chunks. Close/cancel/error accounting must finish exactly once and preserve response close callbacks. Exclude scrape/observability-health endpoints from new capacity gauges.
- Use route templates and a constant unmatched label; never put request IDs, content, identity, or raw unmatched paths in new metrics.

## Outcomes & Retrospective

Implementation is complete; 527 common/lifecycle/fork/runtime and learner SSE cleanup/golden tests pass from `src/api`. An initial broad run from the repository root failed because existing app fixtures resolve plugin paths relative to the API working directory; rerunning from the documented API directory passed. All 20 repository pre-commit gates passed; [PR #3129](https://github.com/ai-shifu/ai-shifu/pull/3129) is Open/Ready; remote checks and production acceptance remain separate. The initial lefthook run selected macOS Python 3.9 for `python3`; explicitly prefixing the conda environment bin directory corrects the tool resolution. This source change has not been deployed and has not changed production replicas, resource requests, or worker counts. Production acceptance follows the existing reviewed release workflow.

## Context and Orientation

`src/api/flaskr/common/observability.py` registers request hooks and `/internal/metrics`. `src/api/gunicorn.conf.py` preloads the app and resets database/exporter resources in workers. Prometheus chooses its storage implementation at import time, so setting an environment variable inside Flask initialization is too late. `src/api/tests/common/` contains isolated observability contracts; fresh subprocess tests are required to validate import ordering and forked writers without contaminating pytest's registry.

## Plan of Work

Add a stdlib-only bootstrap under `flaskr/`, call it before Gunicorn preload, and add worker-exit/master-exit hooks. Scrape a fresh multiprocess CollectorRegistry when the environment is enabled. Add a small lifecycle module used by existing request hooks; keep stream state independent of Flask's context after headers. Register the optional environment variable and regenerate examples. Document measurement meaning and the separate production collection/replica acceptance requirements.

## Concrete Steps

In the conda `ai-shifu` environment, run targeted pytest for lifecycle, multiprocess, and existing observability/Gunicorn contracts. Regenerate `src/api/scripts/generate_env_examples.py` and `scripts/build_repo_knowledge_index.py`. Run the repository harness, architecture checker, development tool check, and `lefthook run pre-commit --all-files`. Review the final diff and publish an Open/Ready PR to GitHub origin without merging it.

## Validation and Acceptance

Two worker processes must contribute counters and histograms to the same scrape. A dead worker's live gauges must disappear without deleting historical counters. A fresh master must not reuse old counters. SSE success, close before first iteration, partial close, generator error, and repeated close must account once, retain original chunks/exceptions, and close the original iterable and response callbacks. Scraping and health checks must not inflate the new capacity gauges. Existing Gunicorn resource resets and HTTP span behavior must still pass. Production acceptance remains open until all worker metrics and active SSE can be scraped safely and collected across peak periods; tests do not certify four replicas.

## Idempotence and Recovery

The default directory is unique per master and cleaned only by that master after shutdown. Explicit directories are never cleared automatically. Restarting a failed startup is safe after correcting a stale explicit directory; use a fresh dedicated directory rather than deleting unknown files. Revert the application commit to roll back metrics without changing business replicas or requests. Existing config and tracing behavior remain compatible.

## Interfaces and Dependencies

The measurement contract is maintained in [API capacity metrics](../../references/api-capacity-metrics.md). Use existing `prometheus_client`, Flask, and Gunicorn dependencies; no new package or network service. The standard `PROMETHEUS_MULTIPROC_DIR` applies to Gunicorn workers in one Pod, not across Pods. A collector must scrape each Pod independently and sum replicas. Existing internal metrics access controls must be verified before exposing a scrape endpoint; this change creates no new public route.

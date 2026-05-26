# Observability Artifacts, Consistency Probes, and Frontend Trace IDs

This ExecPlan is a living document and must stay aligned with `PLANS.md`.

## Purpose / Big Picture

Close the first practical observability gaps identified while comparing this
repository with `ai-video-studio`: durable harness run artifacts, read-only data
consistency probes, and end-to-end frontend request correlation.

The goal is not to replace the existing Loki/Tempo/Prometheus/Langfuse stack.
The goal is to make browser failures, backend request diagnostics, and likely
data-drift checks easy to collect under one stable run id.

## Progress

- [x] 2026-05-26 16:10 CST: Inspected existing request diagnostics,
  Playwright smoke artifacts, billing/metering tables, and frontend request/SSE
  paths.
- [x] 2026-05-26 16:35 CST: Added a repo-level `trace-run.json` collector
  under `artifacts/runs/`.
- [x] 2026-05-26 16:50 CST: Added a read-only consistency probe CLI for
  billing, wallet, model, SMS,
  and notification-template drift.
- [x] 2026-05-26 17:00 CST: Added shared frontend trace headers and propagated
  request ids through request errors, SSE business fallbacks, upload paths, and
  the Playwright smoke harness.
- [x] 2026-05-26 17:05 CST: Ran focused validation and updated this plan with
  outcomes.

## Surprises & Discoveries

- Observation: backend request diagnostics already query logs plus
  Loki/Tempo/Prometheus, but the output is terminal-only and not tied to a
  stable harness run directory.
  Evidence: `src/api/scripts/harness_diagnostics.py`.
- Observation: the Playwright smoke suite already writes
  `harness-diagnostics.json` on failure, but only into the Playwright output
  directory and only with a per-test request id.
  Evidence: `src/cook-web/e2e/smoke.spec.ts`.
- Observation: most frontend API calls go through `src/lib/request.ts`, but
  several SSE and upload paths construct `X-Request-ID` by hand.
  Evidence: `src/cook-web/src/c-api/studyV2.ts`,
  `src/cook-web/src/components/lesson-preview/usePreviewChat.tsx`,
  `src/cook-web/src/components/shifu-setting/ShifuSetting.tsx`, and
  `src/cook-web/src/lib/file.ts`.

## Decision Log

- Decision: use `X-Harness-Run-ID` as the run-level correlation header while
  preserving `X-Request-ID` as the request-level key.
  Rationale: the backend, logs, and diagnostics already center on request ids;
  a separate run id can group many requests without changing that contract.
  Date/Author: 2026-05-26 / Codex
- Decision: make consistency probes read-only and default to JSON output with
  opt-in nonzero exit status.
  Rationale: these probes are suitable for nightly monitoring and local
  investigation, but should not surprise developers by mutating or blocking
  data flows unless explicitly configured.
  Date/Author: 2026-05-26 / Codex

## Outcomes & Retrospective

Implemented the first observability follow-up slice:

- `scripts/harness/trace_run.py` writes
  `artifacts/runs/<run_id>/trace-run.json` from request ids, Playwright
  `harness-diagnostics.json`, and optional backend diagnostics.
- `src/api/scripts/observability_consistency_probes.py` runs read-only JSON
  probes for usage-ledger links, wallet/bucket drift, bucket expiration state,
  published model overrides, SMS send failures, and notification template sync.
- `src/cook-web/src/lib/request-trace.ts` centralizes `X-Request-ID` and
  `X-Harness-Run-ID`; request, SSE, upload, proxy, and smoke harness paths now
  share it.
- `ErrorWithCode` and SSE business fallbacks now carry request/run metadata so
  UI and harness failures can point back to backend diagnostics.

Validation completed:

- `python -m py_compile scripts/harness/trace_run.py src/api/scripts/observability_consistency_probes.py`
- `python scripts/harness/trace_run.py --help`
- `cd src/api && python scripts/observability_consistency_probes.py --help`
- `python scripts/harness/trace_run.py --run-id codex-observability-smoke --request-id codex-test-request --skip-scan --skip-backend-diagnostics`
- `cd src/api && python scripts/observability_consistency_probes.py --limit 1 --window-hours 1`
- `cd src/cook-web && npm test -- --runTestsByPath src/lib/request.test.ts`
- `cd src/cook-web && npm run type-check`
- `python scripts/build_repo_knowledge_index.py`
- `python scripts/check_repo_harness.py`
- `git diff --check`

The local all-probe run found existing wallet/bucket drift for one sampled
wallet: wallet available credits were `50.0000000000`, while active bucket
available credits were `0E-10`; the sampled bucket had status `7443` with
future `effective_to`. That confirms the probe is catching the intended class
of consistency issue.

## Context and Orientation

Existing observability strengths:

- local dev stack with Loki, Tempo, Prometheus, Grafana, and OTEL;
- backend request-scoped logs, metrics, and trace ids;
- Langfuse helpers for LLM-specific traces;
- Playwright failure diagnostics with console/network/screenshot output.

Remaining gaps for this scope:

- no stable `artifacts/runs/<run_id>/trace-run.json` handoff;
- no one-command data drift probe for the billing/metering/wallet surfaces;
- frontend trace header generation is duplicated across request, SSE, and
  upload paths.

## Plan of Work

1. Add a repo-level harness collector that merges browser diagnostics,
   request ids, and backend diagnostics into `trace-run.json`.
2. Add a read-only backend probe script using Flask app/database context and
   raw `SELECT` queries.
3. Add a frontend trace-header helper and update request, SSE, upload, and
   smoke harness surfaces to use it.
4. Add focused unit coverage where the behavior can be tested without a live
   backend.
5. Run repo harness checks plus focused frontend/backend smoke validations.

## Concrete Steps

1. Add `scripts/harness/trace_run.py`.
2. Add `src/api/scripts/observability_consistency_probes.py`.
3. Add `src/cook-web/src/lib/request-trace.ts`.
4. Update `src/cook-web/src/lib/request.ts`, `src/cook-web/src/lib/api.ts`,
   `src/cook-web/src/lib/file.ts`, the hand-written SSE call sites, and the
   smoke harness.
5. Extend focused frontend tests for trace metadata and SSE fallback behavior.

## Validation and Acceptance

- `python scripts/harness/trace_run.py --help`
- `cd src/api && python scripts/observability_consistency_probes.py --help`
- `cd src/cook-web && npm test -- --runTestsByPath src/lib/request.test.ts`
- `cd src/cook-web && npm run type-check`
- `python scripts/check_repo_harness.py`

Acceptance criteria:

- a failed or manually supplied request id can be collected into
  `artifacts/runs/<run_id>/trace-run.json`;
- probes return structured JSON and never write to the database;
- frontend request/SSE/upload paths preserve caller-supplied request ids,
  attach a generated request id when missing, and attach the harness run id
  when available;
- business and HTTP errors expose request id metadata for UI and harness
  debugging.

## Idempotence and Recovery

The trace-run collector overwrites only the target run's `trace-run.json`.
Consistency probes are read-only. Frontend header helpers preserve existing
headers, so callers that already provide a request id remain stable.

If a local backend, database, or observability service is unavailable, scripts
should capture that as structured diagnostic state rather than hiding the
artifact or mutating state.

## Interfaces and Dependencies

- `artifacts/runs/<run_id>/trace-run.json` becomes the durable harness artifact
  envelope.
- `X-Harness-Run-ID` becomes the optional run-level correlation header.
- `X-Request-ID` remains the per-request correlation header.
- `src/api/scripts/observability_consistency_probes.py` depends on the normal
  Flask app/database configuration and uses read-only SQL.

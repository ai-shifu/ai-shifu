# Backend Overhaul Master Plan: Inventory, Optimization, Go Migration

## Purpose / Big Picture

The Python backend (`src/api`, Flask 3 + SQLAlchemy 2 + MySQL/Redis) has
accumulated two years of AI-assisted iteration: ~107K LOC across 250 files in
`flaskr/service/`, redundant and dead code, unclear layering, and scattered
transaction boundaries (213 `db.session.commit()` calls across 70+ files, some
hidden deep inside helpers). The core `/run` SSE lesson-execution chain is the
most tangled surface (`flaskr/service/learn/context_v2.py`, 3,728 lines, 20
mid-flow flushes).

This umbrella plan drives three strictly ordered goals:

1. **Inventory** — produce an evidence-backed dead-code and debt inventory.
2. **Optimization** — batched, aggressive refactoring of the Python backend
   (layering, unit-of-work transaction boundaries, `/run` chain rewrite) while
   keeping the frontend-facing API contract byte-compatible.
3. **Go migration** — a complete strangler-style migration to a new standalone
   Go repository built on the igo framework, cutting over module by module
   behind a reverse proxy, sharing the same MySQL/Redis until Flask retires.

Child ExecPlans and batch PRs reference this document. Detailed findings live
in `docs/exec-plans/active/backend-inventory-2026-07.md` (Phase 1 deliverable).

## Progress

- [x] 2026-07-03 11:31 CST: Master plan created; exploration and design
  completed (three read-only exploration passes over `src/api`, igo/mk_igo
  scaffolds, and the debt surface; phased design reviewed and approved).
- [ ] Phase 0: golden recording harness (`src/api/tests/golden/`).
- [ ] Phase 1: inventory doc `backend-inventory-2026-07.md`.
- [ ] Phase 2: batches B1–B7 (each its own PR; see Plan of Work).
- [ ] Phase 3: Go migration waves 1–5 (starts only after Phase 2 completes).

## Surprises & Discoveries

- `listen_element_legacy.py` and `legacy_record_builder.py` are NOT dead: they
  are actively imported by `learn_funcs.py`, `listen_elements.py`, and
  `listen_element_history.py`. They are compatibility paths that Phase 1 must
  adjudicate explicitly; do not delete on sight.
- A Go implementation of MarkdownFlow already exists
  (`markdown-flow-agent-go`, sibling repo), removing the largest Go-migration
  dependency risk. It still requires a dual-parser diff harness over all
  published shifu documents before Wave 4/5 rely on it.
- Auth is directly shareable between Python and Go: HS256 JWT
  (`flaskr/service/user/utils.py:132`) + `UserToken` DB table as source of
  truth + Redis `ai-shifu:user:<token>` sliding TTL
  (`flaskr/service/user/token_store.py`). Same secret + same table + same
  Redis keys = zero-impact dual-stack operation.
- Celery is much bigger than TTS: `billing/tasks.py` has ~18 `shared_task`s
  plus a beat schedule (`flaskr/common/celery_app.py:85`) covering renewals,
  wallet expiry, order expiry, reconciliation, notifications, aggregation.
- The response envelope is `{"code": ..., "message": ..., "data": ...}`
  (`flaskr/route/common.py:123`, always HTTP 200); igo's stock `res` package
  uses `msg`, so the Go side needs a customized envelope writer.

## Decision Log

- Optimization risk level: aggressive; rewriting the `/run` chain structure is
  in scope. API behavior toward the frontend stays compatible; SSE event
  names/payloads are frozen (see `flaskr/service/learn/AGENTS.md`).
- Go migration ships as a complete plan but executes strictly after Phases
  0–2. Strangler behind a reverse proxy, not big-bang.
- The Go project lives in a standalone new repository generated with
  `igo new ai-shifu-go --non-interactive --defaults --frontend=none`; the
  Next.js `cook-web` frontend is copied into that repository unchanged and
  pointed at the proxy via its API base URL.
- MarkdownFlow in Go: use the existing `markdown-flow-agent-go` library (no
  Python sidecar), gated on a dual-parser alignment harness.
- LLM access from Go: adopt a mature multi-provider open-source Go library
  (candidates: cloudwego/eino, langchaingo, OpenAI-compatible clients); a
  one-time selection spike happens before Wave 1.
- Async jobs in Go: asynq (Redis-backed, includes cron scheduler) replaces
  Celery tasks and the beat schedule; task names kept 1:1; per-task exclusive
  switchover, never double-running.
- Schema ownership: alembic keeps exclusive ownership for the entire
  migration. The Go service never runs XORM `Sync2`; structs are generated
  read-only via `xorm reverse` and hand-tuned. Handover to golang-migrate only
  after the last Flask module retires.
- No schema migrations in any Phase 2 batch, so every batch reverts cleanly.

## Outcomes & Retrospective

(To be filled as phases complete.)

## Context and Orientation

Key call chain for `/run`
(`PUT /api/learn/shifu/<shifu_bid>/run/<outline_bid>`):

    flaskr/service/learn/routes.py:294  run_outline_item_api
      -> flaskr/service/learn/runscript_v2.py:507  run_script
         (Redis mutex / ask counting semaphore via Lua; producer thread owns
          app context + DB session; SimpleQueue -> consumer yields SSE)
      -> flaskr/service/learn/runscript_v2.py:224  run_script_inner
      -> flaskr/service/learn/context_v2.py        RunScriptContextV2
      -> flaskr/service/learn/listen_element_run_stream.py

SSE contract: `RunElementSSEMessageDTO`; event renames require coordinated
frontend changes and are out of scope.

Worst transaction offenders: `billing/renewal.py` (25 commits),
`billing/credit_notifications.py` (20), `order/funs.py` (13, including a
hidden commit inside `is_order_has_timeout` at line 261).

Confirmed-empty service dirs (no `.py`, no routes): `service/study`,
`lesson`, `question`, `rag`, `scenario`, `tag`, `active`.

Duplication: pagination helpers in `referral/admin.py`,
`referral/campaign_admin.py`, `billing/queries.py`; 40+ hand-written
`__json__()` DTOs; 25 direct `os.environ` reads bypassing
`flaskr/common/config.py`; dual ask-provider registries
(`shifu/ask_provider_registry.py` vs
`learn/ask_provider_adapters/registry.py`).

Giant files: `shifu/admin_operations/courses.py` (5,757 lines),
`shifu/admin.py` (4,495), `learn/context_v2.py` (3,728).

Verification environment: the local task workspace provides
`start-dev.sh` / `reset-db.sh` / `stop.sh` for a full stack; backend tests run
with `cd src/api && pytest` (189 files / 1,818 tests).

## Plan of Work

### Phase 0 — Regression safety net (1 PR, prerequisite for all changes)

Golden recording harness under `src/api/tests/golden/` plus a recording
script under `src/api/scripts/`:

- Inject a deterministic fake LLM at the `flaskr/api/llm/` wrapper boundary
  (replays canned completions).
- Reset the dev DB, seed a fixed shifu, call `/run`, and capture the raw SSE
  byte stream. Normalize volatile fields (record ids, timestamps, request
  ids) with a documented normalizer; store transcripts as fixtures.
- Scenarios: fresh lesson start, continue, interaction input, ask flow
  (semaphore path), mid-stream error, resume after interruption.
- Also record golden JSON for the top ~30 non-SSE endpoints (auth, shifu
  detail, order create/query, profile) — reused as the Phase 3 contract-test
  corpus.

### Phase 1 — Inventory (doc-only PRs)

Method (read-only; tools run outside the repo):

1. Static pass: `vulture flaskr/ --min-confidence 80` + `deadcode`, after
   whitelisting four false-positive classes: `@inject` plugin-loaded routes,
   `__json__()` reflection serializers, celery string-invoked tasks,
   `migrations/`.
2. Import-graph pass rooted at `app.py`, `celery_app.py`,
   `route/__init__.py`, plugin scan targets, and `scripts/`; unreachable
   modules = Category A (provably dead). Explicitly adjudicate the two legacy
   learn files and the empty service dirs.
3. Runtime coverage: pytest coverage plus a second run with the dev server
   while exercising cook-web smoke flows; zero coverage under both =
   Category B (suspected dead, needs human sign-off).
4. Scripted grep audits: commit sites ranked per file, `os.environ` reads,
   pagination duplicates, dual registries, hand-written `__json__` DTOs, and
   a route inventory cross-referenced against cook-web API calls to find
   frontend-orphaned endpoints.
5. Hotspot ranking (git churn x file size) to order Phase 2 batches.

Deliverable: `docs/exec-plans/active/backend-inventory-2026-07.md` — one table
row per finding: file/symbol, category, evidence command, confidence,
disposition, consuming Phase 2 batch. Summary rows go to
`tech-debt-tracker.md`; regenerate `index.md` via
`python scripts/build_repo_knowledge_index.py`.

### Phase 2 — Python optimization (7 batches, each an independent PR)

- **B1 Dead code deletion**: Category A findings only (empty dirs,
  frontend-orphaned endpoints, provably unreachable symbols). Expect
  -5–10K LOC.
- **B2 Config consolidation**: migrate the 25 scattered `os.environ` reads to
  declared keys in `flaskr/common/config.py`; verify by diffing effective
  config dumps before/after.
- **B3 Shared helpers**: one pagination helper; a serialization base that
  generates `__json__` (incremental adoption, byte-identical JSON asserted by
  golden fixtures); unify ask-provider registries (learn side canonical,
  shifu path re-exports during a deprecation window).
- **B4 Unit-of-work abstraction**: new `flaskr/dao/uow.py` context manager
  (nested calls join the outer transaction; helpers must not commit).
  Sub-batches: (a) `order/funs.py` — lift the hidden commit in
  `is_order_has_timeout` to callers explicitly; (b) `billing/renewal.py`;
  (c) `billing/credit_notifications.py`. Each PR carries a per-function map
  of old commit points to new boundaries, mid-flow-failure tests, and a
  concurrent order-creation check in the dev env. Afterwards add a CI lint
  banning new `db.session.commit()` outside `dao/`; remaining call sites
  migrate opportunistically.
- **B5 Giant file splits**: mechanical decomposition of
  `shifu/admin_operations/courses.py`, `shifu/admin.py`, and
  `shifu/admin_dtos.py` into cohesive submodules with re-export shims at the
  old paths for one release cycle.
- **B6 /run chain rewrite** (2–3 PRs): decompose `context_v2.py` into
  `learn/run/state.py` (pure state machine, no DB/Flask/MDF),
  `learn/run/recorder.py` (one `unit_of_work()` per step; eliminates the
  flush-then-fail dirty-row class), `learn/run/emitter.py` (sole constructor
  of SSE DTOs; events frozen), and `learn/run/orchestrator.py`. The
  thread/queue/Redis-lock mechanics in `runscript_v2.py` stay untouched in
  this phase (they are rewritten once, in Go). Strategy: new path behind a
  config flag, golden transcripts diffed across both paths, flip default,
  delete `RunScriptContextV2` in a follow-up PR. B6's design doubles as the
  Go port's specification.
- **B7 Tail cleanups**: `.query()` modernization in touched modules, update
  `docs/QUALITY_SCORE.md`, archive completed child plans.

### Phase 3 — Go migration (standalone repo, strangler cutover)

- Bootstrap: generate the repo with mk_igo (`--frontend=none`); copy
  `cook-web` in unchanged; customized envelope writer emitting
  `{code, message, data}`; auth middleware sharing SECRET_KEY, `user_token`
  table, and Redis token keys (cross-stack contract tests both directions);
  LLM library selection spike; Langfuse Go SDK; dual-parser MDF alignment
  harness over all published shifu documents.
- Reverse proxy routes by path prefix: unmigrated -> Flask, migrated -> Go.
- Waves (each: models port -> service port -> contract tests -> proxy cutover
  -> 1–2 weeks shadow -> Flask freeze for that module):
  1. health/config/dict, feedback, check_risk, dashboard, creator_analytics
  2. user/auth flows, profile (except MDF variable extraction)
  3. order, billing, promo, referral, metering + Celery->asynq (18 tasks +
     beat, names 1:1, per-task exclusive switch; WeChat pay verified in
     sandbox; mutating endpoints verified by DB-state diff, not just
     response diff)
  4. shifu authoring + tts + gen_mdf (gated on MDF alignment)
  5. learn `/run` SSE: Gin flusher (`X-Accel-Buffering: no`), producer
     goroutine + buffered channel replacing thread + SimpleQueue, identical
     Redis Lua scripts via go-redis (same keys, so Python and Go instances
     mutually exclude during shadow), one transaction per step via `BeginTx`
     mirroring the B6 recorder. Shadow first, then percentage rollout,
     rollback = routing flip.
- Long tail: alembic migrations, `scripts/` tooling, and possibly `gen_mdf`
  stay in Python until the end. Flask retires after 30 days of zero proxied
  traffic; then schema ownership handover.

## Concrete Steps

1. Land this master plan (doc-only PR; run
   `python scripts/check_repo_harness.py` and
   `python scripts/build_repo_knowledge_index.py`).
2. Build the Phase 0 harness (test-only PR); prove determinism by running the
   recorder twice with identical output.
3. Execute Phase 1; land the inventory doc.
4. Execute Phase 2 batches B1–B7 in order, one PR each (B4 and B6 split into
   sub-PRs as described).
5. Execute Phase 3 bootstrap, then waves 1–5.

## Validation and Acceptance

- Every code batch: full `cd src/api && pytest` plus the touched module's
  suite; local full-stack smoke (learner flow, authoring flow, order flow)
  via the task workspace scripts; golden SSE/JSON diff must be clean.
- B4/B6 extras: mid-flow-failure path tests, concurrent order creation,
  manual abort/resume of a running lesson.
- Doc-only batches: `python scripts/check_repo_harness.py`.
- Before any commit: `python scripts/check_dev_tools.py`; lefthook must be
  active.
- Phase 3 acceptance per wave: contract-test corpus replayed against both
  stacks with structural diff clean; for mutating endpoints, DB-state
  snapshots diffed; `/run` accepted only on byte-identical normalized SSE
  transcripts.

## Idempotence and Recovery

- Phases 0–2 make no schema changes; every batch is a single PR whose revert
  restores the previous state completely.
- B6 ships behind a config flag; rollback is a flag flip before it is a
  revert.
- Phase 3 cutovers are proxy routing changes; rollback is flipping a route
  back to Flask. Both stacks share one DB, so no data migration is involved
  in a rollback.
- The recorder and inventory scripts are re-runnable and produce
  deterministic output; re-running them after an interruption is safe.

## Interfaces and Dependencies

- Frontend contract: response envelope `{code, message, data}` (always HTTP
  200) and the `RunElementSSEMessageDTO` SSE event set — both frozen.
- Auth: HS256 JWT + `user_token` table + Redis `ai-shifu:user:<token>`
  sliding TTL, shared verbatim by the Go stack.
- igo framework (Gin + XORM + Viper + Zap + go-redis) and the mk_igo
  generator produce the Go skeleton; `res` envelope is customized;
  transactions use `BeginTx`.
- `markdown-flow-agent-go` supplies MDF parsing/orchestration in Go, subject
  to the alignment harness.
- Two sibling repos serve as working Go reference implementations for Phase 3
  (both igo + markdown-flow-agent-go): `mini-mdf-play` (Gin SSE streaming of
  MDF block processing — `api/sse.go`, `api/handler.go`) and `playground_go`
  (module `contentflow`; larger app structure with JWT auth and swagger).
- asynq replaces Celery tasks and the beat schedule.
- Alembic owns the schema until Flask retirement.

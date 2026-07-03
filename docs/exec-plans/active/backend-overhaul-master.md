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
- [x] 2026-07-03 12:30 CST: Phase 0 golden harness landed
  (`src/api/tests/golden/`): 4 SSE transcripts + 7 JSON endpoint fixtures,
  deterministic across fresh processes, verified under markdown-flow 0.2.84.
  TODO scenarios: mid-stream error, resume after interruption (need
  fault-injection seams).
- [x] 2026-07-03 12:45 CST: Phase 1 static inventory landed
  (`backend-inventory-2026-07.md` + re-runnable scripts under
  `src/api/scripts/inventory/`). Runtime-coverage step still pending.
- [x] 2026-07-03 13:10 CST: Phase 1 step 3 runtime coverage done (1,862
  tests, 76% total): 12 functions promoted to Category A, 6 candidates
  cleared as alive. Remaining open evidence: production access logs for the
  7 NO-KNOWN-CONSUMER endpoints (needs user authorization).
- [x] 2026-07-03 13:35 CST: Phase 2 B1 dead code deletion executed: ark
  signer, dead test file, 7 empty service dirs, 12 zero-caller functions
  (283 lines) + 17 dangling imports, cook-web markFavoriteShifu catalog
  entry. A5 re-adjudicated as unused parameters and deferred to B7. Full
  pytest 1,873 passed; golden fixtures byte-identical; cook-web type-check
  clean.
- [x] 2026-07-03 14:00 CST: Phase 2 B2 config consolidation: in-package env
  reads now resolve through `flaskr/common/config.py` (3 new declared keys;
  new `get_explicit_env_override()` as the sanctioned raw-env accessor for
  bootstrap/precedence-constrained sites, each documented in place); Docker
  env examples regenerated. 33-case before/after behavior probe identical;
  pytest 1,873 passed; golden fixtures unchanged.
- [x] 2026-07-03 14:11 CST: Phase 2 B3 shared helpers: (1) one
  `normalize_pagination()` in `flaskr/service/common/pagination.py` replaces
  the three byte-identical copies (referral/admin, referral/campaign_admin,
  billing/queries); both referral `_serialize_dt` folded into `to_utc_iso()`
  (campaign_admin keeps a thin wrapper preserving its legacy `""`-for-None
  contract). (2) Ask-provider constants moved to their canonical home
  `flaskr/service/learn/ask_provider_adapters/consts.py` (constants module
  beside the registry to avoid the adapter import cycle);
  `shifu_draft_funcs.py` re-exports them as the deprecation-window shim;
  registries NOT merged (complementary halves per inventory §3g). (3) DTO
  serialization base `AutoJsonMixin` in
  `flaskr/service/common/dto_base.py` auto-generates `__json__` from pydantic
  field declarations (declaration-order identity keys, int/bool coercion,
  `__json_key_overrides__`/`__json_exclude__` knobs); pilot conversion:
  `dashboard/dtos.py` (18 `__json__` deleted, -183 lines), proven
  byte-identical via a probe script diffed against a HEAD worktree.
  Full pytest 1,894 passed (1,873 baseline + 21 new helper tests under
  `tests/service/common/`); golden 11 passed, fixtures byte-identical; ruff
  clean.
- [x] 2026-07-03 15:05 CST: Phase 2 B4 foundation + sub-batch (a):
  `flaskr/dao/uow.py` unit-of-work (outermost commits, nested joins,
  contextvars isolation, `on_commit()` post-commit callbacks for external
  side effects) and full `order/funs.py` migration — 13 scattered commits
  removed with a per-commit audit table in the commit message trail; the
  hidden timeout flip in `is_order_has_timeout` lifted into
  `init_buy_record`'s transaction (now a pure predicate);
  `_app_context_scope()` guard added because nested `app.app_context()`
  switches the Flask-SQLAlchemy 3.1 session. Adversarial money-path review
  found one regression (Feishu notify before outer commit when nested) —
  fixed via `uow.on_commit()`. Cross-module commit leaks documented in
  place (promo helpers, billing webhooks → sub-batches b/c). pytest 1,910
  passed (16 new tests); golden fixtures unchanged.
- [x] 2026-07-03: Phase 2 B4 sub-batch (b) `billing/renewal.py` — all 25
  scattered commits removed (worst offender). Entry points own
  `unit_of_work()`; handlers join. Two deliberate must-persist steps kept as
  independent transactions, each documented in place: (1) the claim
  (PENDING -> PROCESSING + attempt_count) commits before execution so a crash
  cannot cause duplicate execution and the stale-claim recovery in
  `billing/tasks.py` stays the reset path; (2) in
  `_execute_subscription_renewal` the renewal order + event payload
  `bill_order_bid` link commit before the provider sync (double-charge guard;
  `checkout.sync_billing_order` runs in its own session and only sees
  committed rows). Provider sync stays outside any uow/retry scope;
  `retry_on_deadlock` only on `claim_billing_renewal_event` (pure-DB CAS).
  Preorder credit-release dispatch moved to `uow.on_commit()`. Cross-module
  self-commit leaks NOTEd at call sites (`checkout.sync_billing_order`,
  `credit_notifications.enqueue_credit_notification` -> sub-batch c). 4 new
  failure-path tests (per-event isolation, claim persistence, pre-sync order
  persistence, on_commit drop/fire) under
  `tests/service/billing/test_renewal_uow_failure_paths.py`; pytest 1,914
  passed; golden fixtures unchanged.
- [x] 2026-07-03 16:20 CST: Phase 2 B4 sub-batch (c)
  `billing/credit_notifications.py` — all 20 scattered commits removed.
  Batch scans stage each candidate in its own per-item transaction
  (`_stage_scan_notification_isolated`: one bad item reports
  `stage_failed`, rolls back alone, and never aborts neighbors); delivery
  is one unit of work whose terminal SENT/FAILED_PROVIDER flip is the
  send marker (crash after the flip cannot double-send); stage-then-
  enqueue dispatches through `uow.on_commit`. Test-infra discovery: the
  pre-existing `db.session.begin_nested()` savepoint auto-commits under
  pysqlite's lazy-BEGIN mode, silently defeating rollback assertions on
  SQLite — the failure-path tests neutralize the savepoint (documented;
  the property under test belongs to `unit_of_work()`); MySQL semantics
  are unaffected. pytest 1,918 passed (4 new failure-path tests); golden
  fixtures unchanged.
- [x] 2026-07-03 16:35 CST: Phase 2 B4 finale — commit-site ratchet:
  `scripts/check_uow_commit_sites.py` compares `db.session.commit()` call
  sites outside `flaskr/dao/` against the committed baseline
  (`docs/generated/uow-commit-baseline.json`, 155 grandfathered sites, down
  from 213 at inventory); any increase fails, any decrease asks for a
  baseline ratchet-down. Wired into lefthook pre-commit. Remaining sites
  migrate opportunistically per the B4 plan.
- [x] 2026-07-03: Phase 2 B5 giant-file splits — mechanical decomposition
  (pure moves, AST-identical symbol check against HEAD) of the three giants:
  `shifu/admin_operations/courses.py` (5,757 lines) into 8 sibling
  `courses_*` modules (shared / credit_usage / listing / transfer_copy /
  detail / follow_ups / users / ratings); `shifu/admin.py` (4,495 lines)
  into 5 sibling `admin_*` modules (shared / user_credits / user_profiles /
  course_summaries / user_courses; the legacy course-helper duplicates moved
  verbatim — dedupe is out of scope); `shifu/admin_dtos.py` into
  `admin_dtos_courses.py` + `admin_dtos_users.py`. Two intra-file cycles
  were broken by assigning nine cross-domain helpers (outline-context
  loaders, `_merge_courses`, `_format_average_score`, etc.) to
  `courses_shared` — allowed leaf-module exception, still pure moves. All
  three old paths are explicit named re-export shims (retained for one
  release cycle); external callers were deliberately left on the shim
  paths. Because tests monkeypatch through `shifu.admin` (e.g. `datetime`,
  `db`, `_load_user_map`), the admin and courses shims install a module
  `__setattr__` that forwards attribute sets to every submodule defining
  the name — a generalization of the pre-existing
  `_AdminCompatibilityModule` forwarding, verified by a forwarding-chain
  probe including monkeypatch restore. Commit-site baseline regenerated
  (courses.py's 2 sites now in `courses_transfer_copy.py`; total unchanged
  at 155); architecture-boundary baseline regenerated (the moved files
  carry their grandfathered cross-service imports at new paths, 114 -> 130
  entries, plus 7 pre-existing stale learn entries dropped by
  regeneration). pytest 1,918 passed / 6 skipped; golden 11 passed,
  fixtures untouched; ruff clean.
- [x] 2026-07-03 23:55 CST: Phase 2 B6 complete (three PRs; child plan
  `learn-run-decomposition.md`): the /run runtime is now four
  collaborators — `learn/run/emitter.py` (sole SSE constructor),
  `learn/run/recorder.py` (step-scoped unit-of-work persistence; the
  flush-then-fail dirty-row class is gone), `learn/run/state.py` (pure
  read resolver), and a `run_inner` decomposed into 14 named phase
  generators on the context facade. Golden fixtures byte-identical
  throughout; every PR adversarially reviewed. This decomposition is the
  Go port's specification. Note: B6 executed as incremental extractions,
  not the config-flag parallel path sketched below in Plan of Work — see
  the child plan's decision log. Also landed: the reviewed leaf-bid
  placeholder fix (production-data findings in the child plan).
- [x] 2026-07-03: Phase 2 B7 tail cleanups: (1) the disconnect e2e test
  deferred from B6-PR3 landed
  (`tests/service/learn/run/test_run_disconnect_e2e.py`, 2 tests): real
  generator `.close()` on `run_script_inner` against the golden-seeded
  shifu proves a mid-stream disconnect discards the staged block row while
  committed steps survive and a re-run resumes from the last finalized
  block; mutation-verified (rollback->commit flip fails the test). (2) A5
  unused parameters removed with all call sites updated: `profile_array_str`
  (`learn/utils_v2.get_fmt_prompt`), `outline_description`/`outline_index`
  (`shifu_outline_funcs.create_outline`), `unit_index`
  (`shifu_outline_funcs.modify_unit`), `is_learned`
  (`shifu_publish_funcs._build_summary_text`); none was a route-facing
  kwargs contract (routes pass positionally; JSON body fields are
  unchanged and now simply unread). (3) `db.session.query(` call-style
  sites converted to 2.0 `select()` in the Phase-2-touched modules:
  learn/routes.py (2), billing/read_models.py (3, incl. the EXISTS
  subquery), billing/daily_aggregates.py (2); order/funs.py and
  learn/context_v2.py had zero remaining call-style sites (the inventory
  §3d "5" row was order/admin.py, untouched by Phase 2), and the 551-line
  `Model.query` attribute style was deliberately left alone. (4)
  `docs/QUALITY_SCORE.md` api rationale updated for Phase 2 outcomes. (5)
  `learn-run-decomposition.md` completed (Outcomes & Retrospective filled)
  and moved to `docs/exec-plans/completed/`. Full suite 1,942 passed / 6
  skipped; golden 11 passed, fixtures byte-identical; uow ratchet 155
  unchanged; boundary + harness checks green; ruff clean.
- [x] 2026-07-04 00:20 CST: Phase 2 final verification — full-stack local
  smoke on the task-workspace stack (fresh DB reset, all migrations, demo
  import): register/login via universal code; course list/info/outline
  tree; /run SSE fresh start (127 events: 77 streamed elements, heartbeats,
  audio_backfill, terminal done, zero errors) through the B6-decomposed
  runtime against a real LLM; interaction input -> variable_update
  persisted -> 204-event personalized continuation; GET run-status; learn
  records replay; outline progress flips durable (chapter + lesson
  in_progress); creator flow (create course, create outline, save MDF
  revision); order init through the B4a unit-of-work path (order created,
  status to-be-paid). Environment-only fixes during smoke (not repo
  changes): demo course model repointed to an available provider — the
  .env default deepseek key is dead and the qwen account is overdue;
  silicon works. Phase 2 is COMPLETE; the pre-Go review gate is now
  active.
- [ ] Phase 3: Go migration waves 1–5 (starts only after Phase 2 completes).

## Surprises & Discoveries

- `listen_element_legacy.py` and `legacy_record_builder.py` are NOT dead: they
  are actively imported by `learn_funcs.py`, `listen_elements.py`, and
  `listen_element_history.py`. They are compatibility paths that Phase 1 must
  adjudicate explicitly; do not delete on sight.
- The plugin loader (`flaskr/framework/plugin/load_plugin.py`) recursively
  imports every `*.py` under `flaskr/service/`, so import-graph reachability
  is a weak dead-code signal inside services; symbol-level and consumer-level
  evidence must carry the weight (see the inventory doc).
- The endpoint audit found a frontend/backend drift bug: cook-web's catalog
  defines `markFavoriteShifu: 'POST /shifu/mark-favorite-shifu'` with no
  matching backend route; the real favorite route has no frontend caller.
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
- 2026-07-03 hard gate: after Phase 2 completes (all batches + full test
  runs + local full-stack smoke), work STOPS for an explicit review of the
  Go repository layout with the owner before any Go scaffolding is
  generated.
- 2026-07-04 Go layout review CLEARED. Confirmed with the owner:
  (1) igo scaffold with the agreed layers api / service / dao / library /
  utils. (2) service is organized as one package per domain
  (learn/shifu/order/billing/user/...) with domain-private logic under
  `<domain>/internal/` (compiler-enforced visibility) and ONE cross-domain
  leaf package `service/base` that may import only dao/models/library/
  utils; domain packages must never import each other (cross-domain reuse
  sinks into base, cross-domain orchestration rises into api). A
  boundary lint enforcing this DAG lands in the Go repo from day one.
  (3) Config: env vars override config.toml (Viper AutomaticEnv; verify
  igo passthrough, wrap in library/config if needed); env names map
  directly to toml keys with no product prefix (MYSQL_DEFAULT_DATA_SOURCE
  style, consistent with the Python .env); secrets are env-only, static
  topology (port/swagger/log/pool) stays in toml. (4) Go code comments are
  written in Chinese; unit tests are mandatory. (5) Working defaults
  unless objected: DTOs in models/dto; markdown-flow-agent-go via go.mod
  replace during development, pinned release for production builds; LLM
  client library chosen by a Wave-1 spike; reverse-proxy config lives in
  deploy-config. Transaction doctrine carries over from B4: service owns
  the transaction (BeginTx), dao never commits, external side effects
  fire post-commit.
- 2026-07-04 owner updates: (a) NO dual-stack production period — the
  strangler proxy / shadow traffic / percentage rollout machinery is
  dropped from Phase 3; the deliverable is a fully locally-developed and
  locally-verified Go backend (golden-corpus dual-replay against the
  local Python stack, byte-aligned /run SSE), and production cutover is
  handled by the owner separately. Wave order survives as a development
  order only. (b) markdown-flow-agent-go is referenced via local go.mod
  replace (no published module exists). (c) DTOs confirmed at
  models/dto. (d) LLM access: NO framework (eino/langchaingo rejected);
  port the Python ProviderConfig registry (prefix -> base_url/key/param
  overrides; the Python side already ran everything as OpenAI-compatible
  through LiteLLM) over an OpenAI-compatible Go client, matching
  whichever client markdown-flow-agent-go already embeds so the repo
  carries one LLM stack; Langfuse tracing hooks at the registry layer.
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

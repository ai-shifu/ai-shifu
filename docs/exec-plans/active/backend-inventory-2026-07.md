# Backend Inventory 2026-07 (Phase 1)

Child deliverable of
[`backend-overhaul-master.md`](./backend-overhaul-master.md). Scope:
`src/api`, dated 2026-07-03. Covers Phase 1 steps 1 (static dead-code pass), 2
(import-graph reachability), 4 (grep audits + consumer-classified endpoint
audit), 5 (hotspot ranking), and 3 (runtime coverage; see §7 — pytest-based
line-level adjudication done, production access-log check still pending).

Environment: Python 3.10 (conda env `work`), `vulture 2.16`; a hand-written
ast walker was used for the import graph because the plugin loader semantics
needed custom modeling. All commands run from `src/api` unless noted.
Re-runnable helper scripts live in `src/api/scripts/inventory/`:
`filter_vulture.py`, `import_graph.py`, `extract_routes.py`,
`match_routes.py`.

Repo state at analysis time: branch `aichy/optimization-260703`, HEAD
`941da2c9`. Raw tool outputs referenced below (`vulture-*.txt`, `grep-*.txt`,
`import-graph-results.txt`, `routes-*.txt`) are not stored in the repo; every
one is regenerable from the evidence command quoted alongside it.

---

## 0. Load-bearing discovery: the plugin loader imports EVERYTHING

`flaskr/framework/plugin/load_plugin.py:load_plugins_from_dir` (called from
`app.py:87` with `flaskr/service`, and `app.py:89` with `flaskr/plugins`, which is
empty) **recursively imports every `*.py` file** under every top-level
subdirectory of `flaskr/service/` — not just `routes.py`. It skips only
`__init__.py` (imported implicitly as packages), `__pycache__`, dirs named
`migrations`, and dotfiles; per-directory import errors are caught and logged
(`load_plugin.py:67-71`).

Consequences for this inventory:

- Every module under `flaskr/service/<dir>/` is import-reachable at startup **by
  construction**. Import-graph reachability is therefore a weak dead-code signal
  inside `flaskr/service`; symbol-level (vulture) and consumer-level (route
  audit) signals must carry the weight there.
- Any module-level side effect in any service file runs at app startup.
- Deleting a service file can never break an import of it via the loader (it
  enumerates the filesystem), only explicit `import` statements elsewhere.

---

## 1. Vulture pass

Evidence commands:

    vulture flaskr/ --min-confidence 80                      # spec run
    vulture flaskr/ app.py celery_app.py scripts/ --min-confidence 60   # supplementary
    python filter_vulture.py <raw> /Users/aichy/work/aishifu/ai-shifu/src/api

Post-filter exclusions implemented (see `filter_vulture.py`): functions whose
decorator block contains `@inject`, `.route(`, or `shared_task`; symbols named
`register_*`; `__json__` methods; paths under `migrations/`. Note: vulture flags
the FIRST DECORATOR's line for decorated defs, so the filter scans from the
flagged line down to the `def`.

### 1.1 min-confidence 80 (spec run) — 8 findings, 0 excluded, all survive

All are 100%-confidence unused variables (raw file: `vulture-raw.txt`):

| file:line | symbol | confidence |
|---|---|---|
| flaskr/dao/__init__.py:161 | `executemany` | 100% |
| flaskr/framework/plugin/enable_plugin.py:91 | `compare_to` | 100% |
| flaskr/framework/plugin/enable_plugin.py:91 | `reflected` | 100% |
| flaskr/service/learn/utils_v2.py:122 | `profile_array_str` | 100% |
| flaskr/service/shifu/shifu_outline_funcs.py:237 | `outline_description` | 100% |
| flaskr/service/shifu/shifu_outline_funcs.py:238 | `outline_index` | 100% |
| flaskr/service/shifu/shifu_outline_funcs.py:480 | `unit_index` | 100% |
| flaskr/service/shifu/shifu_publish_funcs.py:529 | `is_learned` | 100% |

Caveat: the four `enable_plugin.py`/`dao` hits are callback signature parameters
(alembic `include_object`, SQLAlchemy `before_cursor_execute`) — required by the
callback contract, not deletable; the other four are genuinely dead locals.

### 1.2 Supplementary 60%-confidence run (Category B feedstock)

Run over `flaskr/ app.py celery_app.py scripts/` (running over `flaskr/` alone
produced ~15 false "unused" hits for functions only called from `app.py`, e.g.
`init_db`, `init_log`, `load_plugins_from_dir` — always include entry files).

- Raw findings: 674 → excluded 247 (flask route decorator 219, celery
  shared_task 19, `register_*` 10, others 0 — no `__json__`/migrations hits
  because vulture treats `__json__` as dunder) → **kept 425**
  (file: `vulture-filtered-60-full.txt`).
- Kept by kind: unused function 80, method 23, class 8, variable 265,
  attribute 47, property 2.
- Of the kept functions, **20 are Flask/Click CLI commands** (`@app.cli`,
  `@click.*`, `cli.command`) — a 5th false-positive class not in the spec list:
  all of `flaskr/service/billing/cli.py` (15), `flaskr/command/__init__.py` (4),
  `flaskr/framework/plugin/enable_plugin.py:131 migrate`. Treat as alive.
- Known remaining FP shapes in the kept list (verified by inspection): Flask
  error handlers / teardown hooks registered inside `register_common_handler`
  (`flaskr/route/common.py:74,80,87,97`), SQLAlchemy event listener
  (`flaskr/dao/__init__.py:159`), watchdog callback
  (`flaskr/framework/plugin/hot_reload.py:123 on_modified`), TTS provider
  interface methods (`get_supported_emotions` x3).
- Most promising true-dead candidates (need runtime confirmation → Category B):
  `flaskr/service/billing/read_models.py` build_* page builders at lines
  607, 616, 670, 817, 1503, 1535, 1548;
  `flaskr/service/billing/checkout.py:1142 _validate_plan_checkout_upgrade_only`;
  `flaskr/service/billing/primitives.py:140,154`;
  `flaskr/service/billing/queries.py:483 subscription_has_attention`;
  `flaskr/common/log.py:115 setup_logging`, `:158 log_sse_end`;
  `flaskr/common/config.py:1649 debug_print`
  (`:1668 export_env_example` is used by `scripts/generate_env_examples.py` —
  check before deleting);
  `flaskr/common/cache_provider.py:9 CacheLock`;
  `flaskr/api/tts/volcengine_protocol.py:88 ErrorCode`, `:276
  encode_cancel_session`.
- The 265 unused variables are mostly unpacking/callback-arg noise; batch-fix
  opportunistically, not a Phase 2 batch of its own.

---

## 2. Import-graph reachability

Evidence: `python import_graph.py` (ast-based; edges = every `Import`/
`ImportFrom` anywhere in each module, incl. function-local; roots = `app.py`,
`celery_app.py`, `flaskr/route/__init__.py`, `flaskr/command/*`, `scripts/*`,
plus every service module the plugin loader enumerates — see §0).
Output: `import-graph-results.txt`.

- 325 project modules; 267 roots (250 of them plugin-scanned service modules);
  **324 reachable; 1 unreachable**.

### Category A: `flaskr/api/ark/sign.py` (121 lines)

Volcengine "ark" HMAC request signer. Zero importers anywhere in `src/api`
(`grep -rn "api.ark\|ark.sign\|from .ark\|import ark" --include='*.py'` → only
markdown_flow false hits), **and** `flaskr/api/ark/` has no `__init__.py`, so it
is not even an importable package on this tree. Provably dead.

### Adjudicated legacy learn modules — REACHABLE, actively used (NOT dead)

Consistent with the master plan's "Surprises" note. Call-site evidence
(`grep -rn "<symbol>" flaskr --include='*.py'`):

| module | imported by (prod) | symbol usage outside defining module |
|---|---|---|
| `learn/listen_element_legacy.py` | `listen_elements.py:22` | `build_listen_elements_from_legacy_record`: 1 call site (`listen_elements.py:179`) |
| `learn/legacy_record_builder.py` | `learn_funcs.py:38`, `listen_element_history.py:18`, `listen_elements.py:21`, `listen_element_legacy.py` | `LegacyLearnRecord` 14 uses, `build_legacy_record_for_progress` 14 uses, `LegacyGeneratedBlockRecord` 7 uses |

Plus 5 test files exercising them (`tests/service/learn/test_listen_elements*`,
`test_element_protocol.py`, `test_learn_dtos_slide.py`). Disposition: keep;
these are the legacy-record compatibility path. Their retirement is a data/
behavior migration decision (Phase 2/3 adjudication), not a dead-code deletion.

### Empty service dirs — Category A (delete the dirs)

`find flaskr/service/<d> -name '*.py'` → zero for all of:
`active/` (contains only stale `AGENTS.md` + `CLAUDE.md` — delete those too),
`lesson/`, `question/`, `rag/`, `scenario/`, `tag/` (fully empty), `study/`
(only empty subdirs `continue/`, `input/`, `ui/`). The plugin loader logs a
harmless load attempt for each at startup. Only textual reference anywhere:

### `tests/run_script.py` — confirmed dead test — Category A

Imports the non-existent `flaskr.service.study.runscript` (`tests/run_script.py:2`).
`flaskr/service/study/` contains no Python. The file is not named `test_*.py` so
pytest never collects it as a module by default (`run_script.py` matches neither
`python_files` pattern), i.e. it is silently dead. Delete.

---

## 3. Grep audits

All counts exclude `__pycache__`. Raw outputs: `grep-3ab.txt`, `grep-3c.txt`,
`grep-3de.txt`.

### 3a. `db.session.commit()` per file — TOTAL 213

    grep -rn "db\.session\.commit()" flaskr --include="*.py" | grep -v __pycache__ \
      | cut -d: -f1 | sort | uniq -c | sort -rn | head -20

| n | file |
|---|---|
| 25 | flaskr/service/billing/renewal.py |
| 20 | flaskr/service/billing/credit_notifications.py |
| 13 | flaskr/service/order/funs.py |
| 10 | flaskr/service/tts/minimax_voice_clone.py |
| 10 | flaskr/service/billing/notifications.py |
| 9 | flaskr/route/user.py |
| 7 | flaskr/service/billing/wallets.py |
| 7 | flaskr/service/billing/checkout.py |
| 6 | flaskr/service/shifu/funcs.py |
| 6 | flaskr/service/referral/service.py |
| 6 | flaskr/service/promo/admin.py |
| 5 | flaskr/service/billing/cli.py |
| 4 | flaskr/service/user/user.py |
| 4 | flaskr/service/shifu/shifu_outline_funcs.py |
| 4 | flaskr/service/shifu/shifu_draft_funcs.py |
| 4 | flaskr/service/profile/profile_manage.py |
| 4 | flaskr/service/billing/subscriptions.py |
| 3 | flaskr/service/user/utils.py |
| 3 | flaskr/service/referral/campaign_admin.py |
| 3 | flaskr/service/learn/runscript_v2.py |

Matches the plan's B4 worst-offender list exactly (renewal 25, credit_notifications
20, order/funs 13 incl. the hidden commit in `is_order_has_timeout`).

### 3b. `db.session.flush()` per file — TOTAL 106

Same command with `flush()`. Top: `learn/context_v2.py` **32**,
`user/repository.py` 6, `user/phone_flow.py` 6, `shifu/shifu_import_export_funcs.py` 5,
`billing/checkout.py` 4, then a long tail of 2–3 (full list in `grep-3ab.txt`).

### 3c. `os.environ` / `os.getenv` outside `flaskr/common/config.py` and tests — 38 hits

    grep -rnE "os\.environ|os\.getenv" flaskr app.py celery_app.py scripts \
      --include="*.py" | grep -v __pycache__ | grep -v "^flaskr/common/config.py"

Full listing in `grep-3c.txt`. Triage:

- **Bootstrap-legitimate (leave):** `SKIP_APP_AUTOCREATE`/`SKIP_LOAD_DOTENV`
  setdefault/guards in `app.py:16,117`, `celery_app` wrapper
  (`flaskr/common/celery_app.py:184`), `flaskr/service/tts/tasks.py:20`,
  `flaskr/service/billing/tasks.py:81`, and all 12 `scripts/*` hits — these run
  before config exists by design.
- **B2 migration targets (config bypasses inside flaskr/):**
  `flaskr/common/celery_app.py:62,67,74,148` (CELERY_* fallbacks);
  `flaskr/api/llm/__init__.py:186,195,207` (`LLM_ALLOWED_MODELS`,
  `LLM_ALLOWED_MODEL_DISPLAY_NAMES`);
  `flaskr/api/tts/__init__.py:87` + `flaskr/api/tts/volcengine_http_provider.py:119,122`
  (`VOLCENGINE_TTS_RESOURCE_ID`/`CLUSTER_ID`);
  `flaskr/command/update_shifu_demo.py:132` (`SKIP_DEMO_SHIFU_IMPORT`);
  `flaskr/command/unified_migration_task.py:93` (database URL);
  `flaskr/i18n/__init__.py:18` (`SHARED_I18N_ROOT`);
  `app.py:20-21` TZ handling (reads config, writes env — keep but document).
  That's **~14 in-package reads** to fold into declared keys in
  `flaskr/common/config.py` (plan said "25"; the delta is scripts/bootstrap
  noise counted differently).

### 3d. Legacy `.query(` usage per module — top 15 (TOTAL 258 lines)

    grep -rn "\.query(" flaskr --include="*.py" | grep -v __pycache__ \
      | cut -d: -f1 | sort | uniq -c | sort -rn | head -15

| n | file |
|---|---|
| 82 | flaskr/service/shifu/admin_operations/courses.py |
| 63 | flaskr/service/shifu/admin.py |
| 50 | flaskr/service/dashboard/funcs.py |
| 11 | flaskr/service/shifu/admin_operations/users.py |
| 11 | flaskr/service/promo/admin.py |
| 6 | flaskr/service/shifu/shifu_draft_funcs.py |
| 6 | flaskr/service/billing/campaigns.py |
| 5 | flaskr/service/order/admin.py |
| 4 | flaskr/service/shifu/admin_operations/voice_clones.py |
| 3 | flaskr/service/shifu/course_activity.py |
| 3 | flaskr/service/billing/read_models.py |
| 2 | flaskr/service/shifu/permissions.py |
| 2 | flaskr/service/learn/routes.py |
| 2 | flaskr/service/learn/context_v2.py |
| 2 | flaskr/service/billing/daily_aggregates.py |

Companion metric — `Model.query.` attribute style: **551 lines**, top:
billing/credit_notifications.py 31, billing/read_models.py 29,
billing/subscriptions.py 25, shifu/admin_operations/courses.py 24,
shifu/admin.py 24, order/funs.py 21, learn/context_v2.py 20
(command in `grep-3de.txt`).

### 3e. Hand-written `def __json__` per file — top 15 (TOTAL 120)

    grep -rn "def __json__" flaskr --include="*.py" | grep -v __pycache__ \
      | cut -d: -f1 | sort | uniq -c | sort -rn | head -15

| n | file |
|---|---|
| 39 | flaskr/service/shifu/admin_dtos.py |
| 26 | flaskr/service/learn/learn_dtos.py |
| 18 | flaskr/service/dashboard/dtos.py |
| 6 | flaskr/service/shifu/dtos.py |
| 6 | flaskr/service/order/admin_dtos.py |
| 4 | flaskr/service/profile/dtos.py |
| 4 | flaskr/service/common/dtos.py |
| 3 | flaskr/service/order/funs.py |
| 2 | flaskr/service/user/dtos.py |
| 2 | flaskr/service/shifu/shifu_struct_manager.py |
| 2 | flaskr/service/learn/legacy_record_builder.py |
| 2 | flaskr/service/common/dicts.py |
| 1 x 6 | promo/admin_dtos, learn/utils_v2, learn/llmsetting, + 3 more |

(120 total, well beyond the plan's "40+".) B3 serialization-base target list.

### 3f. Duplicated pagination helpers — 3 identical copies

    grep -rn "def normalize_page\|def normalize_pagination\|def _normalize_page" \
      flaskr --include="*.py" | grep -v __pycache__

- `flaskr/service/referral/admin.py:53  _normalize_page`
- `flaskr/service/referral/campaign_admin.py:316  _normalize_page`
- `flaskr/service/billing/queries.py:84  normalize_pagination`

Body diff: **functionally identical** — same try/except int coercion, same
clamping, and identical constants in all three modules
(`DEFAULT_PAGE_INDEX = 1`, `DEFAULT_PAGE_SIZE = 20`, `MAX_PAGE_SIZE = 100`;
referral/admin.py:28-30, campaign_admin.py:49-51, billing/queries.py:48-50).
Only name and docstring differ. Bonus duplication found adjacent: both referral
files also carry a near-identical private `_serialize_dt` (admin.py:65 area,
campaign_admin.py:328 area) that re-implements the `fmt()` UTC-Z contract —
fold into `to_utc_iso()` per AGENTS.md when consolidating (B3).

### 3g. Dual ask-provider registries — complementary halves, not copies

- `flaskr/service/shifu/ask_provider_registry.py` — config/schema side. Public
  symbols: `get_default_ask_provider_config`, `get_ask_provider_schema_registry`,
  `validate_ask_provider_specific_config`, `get_effective_ask_provider_config`,
  `get_ask_provider_metadata` (+7 private `_localize_*` helpers).
- `flaskr/service/learn/ask_provider_adapters/registry.py` — runtime dispatch
  side. Public symbols: `get_ask_provider_adapter`,
  `stream_ask_provider_response`.

Overlap/coupling: no duplicated function bodies, but both key off the same
`ASK_PROVIDER_LLM/DIFY/COZE/COZE_WORKFLOW/VOLC_KNOWLEDGE` constants, which live
in a third place — `flaskr/service/shifu/shifu_draft_funcs.py` — imported
cross-service by the learn registry (`registry.py:7-13`). Consumers use both
halves together: `learn/handle_input_ask.py:39` (shifu registry) + `:553` (learn
adapters); `shifu/route.py:139` + `:2156` likewise. B3 disposition per plan:
learn side canonical, shifu path re-exports during deprecation; move the
provider constants out of `shifu_draft_funcs.py` into the canonical module.

---

## 4. Frontend-orphan endpoint audit (with consumer classification)

Evidence: `python extract_routes.py > routes-backend.txt` (ast-based; resolves
`path_prefix` positional/kw-only defaults, local prefix vars, and
`app.config.get(key, default)` prefixes; **222 unique method+path, 0 unresolved**)
then `python match_routes.py > routes-orphans.txt`.

Consumer surfaces checked:
1. **cook-web**: `src/cook-web/src/api/api.ts` catalog (`'METHOD /path'`,
   `/api`-prefixed by `lib/api.ts gen()`) + every raw `/api/...` string in
   `src/cook-web/src` (incl. template literals; `${...}`/`{x}`/`:x` segments
   treated as wildcards).
2. **skills CLI** (`/Users/aichy/work/aishifu/skills`): full `/api/...` strings
   plus relative `'/shifus...'` paths joined onto `/api/shifu` by
   `shifu-cli.py:api()` (line 106-108).
3. **mini-program** (`/Users/aichy/work/aishifu/陪跑小程序源代码`): grepped; it is a
   RuoYi-style `/api/system/...` backend — **zero path overlap** with ai-shifu
   (it does not call this API at all).
4. **external-callback**: path/handler matching `callback|notify|webhook`, plus
   `/api/open-api/v1/*` (integrator surface, token-authed).
5. **ops**: `/health` (`flaskr/route/user.py:1132`), `/internal/metrics` and
   `/internal/observability/health` (`flaskr/common/observability.py:145-150`,
   k8s/prometheus probes).

Headline: **222 endpoints → 200 used-by-cook-web, 24 used-by-cli (4 CLI-only),
8 external-callback, 3 ops, 8 NO-KNOWN-CONSUMER.**

### Endpoints NOT referenced by cook-web

| method | path | consumer | handler |
|---|---|---|---|
| POST | /api/callback/alipay-notify | external-callback | route/callback.py:40 |
| POST | /api/callback/pingxx-callback | external-callback | route/callback.py:20 |
| POST | /api/callback/wechatpay-notify | external-callback | route/callback.py:77 |
| POST | /api/order/stripe/webhook | external-callback | route/order.py:413 |
| POST | /api/open-api/v1/order/query | external-callback | route/open_api.py:62 |
| POST | /api/open-api/v1/order/grant | external-callback | route/open_api.py:73 |
| POST | /api/open-api/v1/order/revoke | external-callback | route/open_api.py:84 |
| GET | /health | ops | route/user.py:1132 |
| GET | /internal/metrics | ops | common/observability.py:146 |
| GET | /internal/observability/health | ops | common/observability.py:150 |
| POST | /api/creator-analytics/query | used-by-cli | route/creator_analytics.py:14 |
| POST | /api/creator-analytics/credit-detail | used-by-cli | route/creator_analytics.py:91 |
| GET | /api/shifu/shifus/&lt;shifu_bid&gt;/export | used-by-cli | service/shifu/route.py:2014 |
| POST | /api/user/console_send_sms_code | used-by-cli | route/user.py:490 |
| GET | /api/storage/&lt;profile&gt;/&lt;path:object_key&gt; | indirect: generated content URLs (see below) | route/storage.py:40 |
| POST | /api/billing/orders/&lt;bill_order_bid&gt;/refund | NO-KNOWN-CONSUMER | service/billing/routes.py:177 |
| GET | /api/dict/dicts | NO-KNOWN-CONSUMER | route/dicts.py:11 |
| GET | /api/dict/models | NO-KNOWN-CONSUMER | route/dicts.py:22 |
| GET | /api/learn/shifu/&lt;shifu_bid&gt;/lesson-feedbacks | NO-KNOWN-CONSUMER | service/learn/routes.py:748 |
| GET | /api/metering/usage-summary | NO-KNOWN-CONSUMER | service/metering/routes.py:29 |
| POST | /api/profiles/get-profile-item | NO-KNOWN-CONSUMER | service/profile/routes.py:320 |
| POST | /api/shifu/shifus/&lt;shifu_bid&gt;/favorite | NO-KNOWN-CONSUMER | service/shifu/route.py:1000 |

Adjudications:

- `/api/storage/...` is **not dead**: the backend generates `/storage/...` URLs
  into content (`flaskr/service/common/storage.py:101`,
  `flaskr/service/user/user.py:51`); browsers fetch them as plain asset links,
  so no frontend code references the path. Reclassified out of
  NO-KNOWN-CONSUMER → 7 true candidates.
- The 7 remaining NO-KNOWN-CONSUMER endpoints are **Category B** (candidates,
  need runtime/access-log or human sign-off — they may be operator tooling or
  planned surfaces): billing refund, dict/dicts, dict/models, lesson-feedbacks,
  metering usage-summary, profiles/get-profile-item, shifu favorite.
- **Drift bug found (bonus):** cook-web catalog defines
  `markFavoriteShifu: 'POST /shifu/mark-favorite-shifu'`
  (`src/cook-web/src/api/api.ts:59`) but **no such backend route exists** — the
  real backend route is `POST /api/shifu/shifus/<shifu_bid>/favorite`, which no
  frontend code calls; the only UI use is read-only `is_favorite` display
  (`src/cook-web/src/app/admin/page.tsx:827`). The catalog entry would 404 if
  ever invoked (it currently has no callers). Either wire the UI to the real
  route or delete both ends.

CLI-only endpoints (keep; consumer is `skills/ai-shifu-course-creator/scripts/shifu-cli.py`):
creator-analytics/query (`shifu-cli.py:250`), creator-analytics/credit-detail
(`:254`), shifus/&lt;bid&gt;/export (`:711`), user/console_send_sms_code (`:476`).
Note `shifu-cli.py` is a general passthrough onto `/api/shifu/*`
(`url = f"{base_url}/api/shifu{path}"`), so treat the whole `/api/shifu` surface
as CLI-callable when deleting anything under it.

---

## 5. Hotspot ranking (git churn x file size)

Evidence:

    git log --since='12 months ago' --format= --name-only -- src/api \
      | sort | uniq -c | sort -rn | head -40
    # cross-joined with wc -l per surviving file, product = churn x LOC

Top 30 by churn x LOC (commits, lines, product) — production code and tests
interleaved; tests marked (t):

| rank | commits | LOC | churn x LOC | file |
|---|---|---|---|---|
| 1 | 68 | 3728 | 253504 | flaskr/service/learn/context_v2.py |
| 2 | 50 | 4495 | 224750 | flaskr/service/shifu/admin.py |
| 3 | 72 | 2551 | 183672 | flaskr/service/shifu/route.py |
| 4 | 50 | 1995 | 99750 | flaskr/common/config.py |
| 5 (t) | 21 | 4569 | 95949 | tests/service/shifu/test_admin_course_detail.py |
| 6 (t) | 20 | 4739 | 94780 | tests/service/shifu/test_admin_users.py |
| 7 (t) | 14 | 5466 | 76524 | tests/service/learn/test_listen_elements.py |
| 8 | 25 | 2074 | 51850 | flaskr/service/order/funs.py |
| 9 | 30 | 1681 | 50430 | flaskr/service/learn/learn_funcs.py |
| 10 (t) | 11 | 4482 | 49302 | tests/service/billing/test_billing_write_routes.py |
| 11 (t) | 22 | 1996 | 43912 | tests/service/learn/test_context_v2.py |
| 12 | 37 | 1171 | 43327 | flaskr/api/llm/__init__.py |
| 13 | 18 | 2126 | 38268 | flaskr/service/tts/streaming_tts.py |
| 14 | 25 | 1422 | 35550 | flaskr/service/shifu/admin_dtos.py |
| 15 | 10 | 3433 | 34330 | flaskr/service/billing/credit_notifications.py |
| 16 | 35 | 958 | 33530 | flaskr/service/shifu/shifu_draft_funcs.py |
| 17 | 12 | 2641 | 31692 | flaskr/service/shifu/admin_operations/route.py |
| 18 | 11 | 2756 | 30316 | flaskr/service/dashboard/funcs.py |
| 19 | 11 | 2614 | 28754 | flaskr/service/billing/subscriptions.py |
| 20 | 24 | 1136 | 27264 | flaskr/route/user.py |
| 21 (t) | 10 | 2350 | 23500 | tests/service/dashboard/test_dashboard_routes.py |
| 22 | 18 | 1285 | 23130 | flaskr/service/order/admin.py |
| 23 | 24 | 895 | 21480 | flaskr/service/learn/runscript_v2.py |
| 24 | 19 | 1012 | 19228 | flaskr/service/learn/routes.py |
| 25 | 10 | 1909 | 19090 | flaskr/service/promo/admin.py |
| 26 (t) | 11 | 1590 | 17490 | tests/service/shifu/test_admin_courses.py |
| 27 | 16 | 1015 | 16240 | flaskr/service/learn/learn_dtos.py |
| 28 | 25 | 561 | 14025 | flaskr/service/shifu/shifu_publish_funcs.py |
| 29 | 23 | 608 | 13984 | flaskr/service/profile/funcs.py |
| 30 | 15 | 915 | 13725 | flaskr/service/shifu/models.py |

Special case: `flaskr/service/shifu/admin_operations/courses.py` — the repo's
biggest file (5757 LOC) has only 5 commits in 12 months (churn x LOC 28785,
~rank 19); it is recent, so churn understates it. B5 keeps it as a split target
on size alone. Non-Python high-churn files for context: requirements.txt (59),
error_codes.json (15).

Suggested Phase 2 batch ordering signal: (1) learn/context_v2.py,
(2) shifu/admin.py + shifu/route.py, (3) common/config.py (aligns with B2),
(4) order/funs.py + learn/learn_funcs.py, (5) api/llm/__init__.py.

---

## 6. Summary tables

### Category A — provably dead, safe to delete (B1)

| # | item | evidence |
|---|---|---|
| A1 | `flaskr/api/ark/sign.py` (121 LOC; dir lacks `__init__.py`) | import graph: 0 importers; `grep -rn "api\.ark\|ark\.sign" src/api --include='*.py'` |
| A2 | `tests/run_script.py` | imports non-existent `flaskr.service.study.runscript`; not collected by pytest naming rules |
| A3 | empty dirs `flaskr/service/{active,lesson,question,rag,scenario,study,tag}` (incl. `active/AGENTS.md`, `active/CLAUDE.md`, `study/{continue,input,ui}`) | `find flaskr/service/<d> -name '*.py'` → 0; only ref is A2 |
| A4 | cook-web catalog entry `markFavoriteShifu: 'POST /shifu/mark-favorite-shifu'` (`src/cook-web/src/api/api.ts:59`) | no matching backend route (routes-backend.txt); no callers (`grep -rn markFavoriteShifu src/cook-web/src`) |
| A5 | RE-ADJUDICATED during B1: these vulture hits (`learn/utils_v2.py:122`, `shifu/shifu_outline_funcs.py:237,238,480`, `shifu/shifu_publish_funcs.py:529`) are unused function PARAMETERS, not dead locals; removing them changes call signatures. Deferred to B7 opportunistic cleanup. | §1.1 + B1 execution notes |
| A6 | 12 functions with zero static callers AND zero runtime execution: `billing/read_models.py` 7 `build_*` (607,616,670,817,1503,1535,1548), `billing/checkout.py:1142`, `billing/primitives.py:140,154`, `billing/queries.py:483`, `api/tts/volcengine_protocol.py:276` | §7 line-level coverage adjudication |

Estimated direct deletion: small (~150 LOC + dirs); the plan's -5-10K LOC for B1
must come mostly from Category B items after runtime confirmation.

### Category B — suspected dead, needs runtime coverage / human sign-off

| # | item | evidence |
|---|---|---|
| B1 | 7 NO-KNOWN-CONSUMER endpoints (+ their handler chains): billing refund, dict/dicts, dict/models, learn lesson-feedbacks, metering usage-summary, profiles/get-profile-item, shifu favorite | §4 table; re-run `match_routes.py` |
| B2 | `POST /api/shifu/shifus/<bid>/favorite` + `mark_or_unmark_favorite_shifu` + `funcs.py:28,57,80` chain (pairs with A4 decision) | §4 drift note |
| B3 | remaining kept vulture unused functions/methods/classes after the §7 adjudication (12 promoted to A6; `common/log.py:115,158`, `common/config.py:1649,1668`, `common/cache_provider.py:9`, `api/tts/volcengine_protocol.py:88` cleared as alive) — the residue is mostly low-value; adjudicate opportunistically | `vulture-filtered-60-full.txt` + §7 |
| B4 | `learn/listen_element_legacy.py` + `learn/legacy_record_builder.py` — ALIVE compat path (1 + 35 call sites); adjudicate retirement as a migration, not deletion | §2 |
| B5 | 265 unused-variable + 47 unused-attribute vulture hits — opportunistic cleanup | `vulture-filtered-60-full.txt` |

### Category C — redundancy / consolidation targets (B2/B3/B4/B5)

| # | item | scope | consuming batch |
|---|---|---|---|
| C1 | pagination helper x3 (identical bodies+constants) + `_serialize_dt` x2 | referral/admin.py:53, referral/campaign_admin.py:316, billing/queries.py:84 | B3 |
| C2 | 120 hand-written `__json__` across 21 files (top: admin_dtos 39, learn_dtos 26, dashboard/dtos 18) | §3e | B3 |
| C3 | dual ask-provider registries + provider constants stranded in `shifu_draft_funcs.py` | §3g | B3 |
| C4 | ~14 in-package env reads bypassing config (celery 4, llm 3, tts 3, i18n 1, command 2, app TZ 1) | §3c | B2 |
| C5 | 213 `db.session.commit()` (renewal 25, credit_notifications 20, order/funs 13) + 106 `flush()` (context_v2 32) | §3a/3b | B4 |
| C6 | giant files: admin_operations/courses.py 5757, shifu/admin.py 4495, context_v2.py 3728, shifu/route.py 2551, admin_operations/route.py 2641 | §5 | B5 |
| C7 | legacy query styles: 258 `.query(` + 551 `Model.query.` lines | §3d | B5/B7 |

### Category D — hotspot ranking (orders Phase 2 batches)

Top production-code hotspots by churn x LOC: **context_v2.py, shifu/admin.py,
shifu/route.py, common/config.py, order/funs.py, learn_funcs.py,
api/llm/__init__.py, tts/streaming_tts.py, shifu/admin_dtos.py,
billing/credit_notifications.py** (full table §5). courses.py joins on size
despite low churn.

---

## 7. Runtime coverage pass (Phase 1 step 3)

Evidence:

    coverage run --source=flaskr -m pytest -q -x --ignore=tests/golden
    # 1862 passed, 6 skipped, 72.79s; TOTAL coverage 76%
    coverage report --sort=cover          # file level
    coverage json -o cov.json             # line level for B-item adjudication

File-level 0% (5 files, all CLI/ops — NOT dead): `flaskr/command/__init__.py`,
`import_user.py`, `unified_migration_task.py`, `update_shifu_demo.py`
(production migration-job commands), `flaskr/framework/plugin/enable_plugin.py`
(plugin migration helper). CLI surfaces need operational evidence, not test
coverage.

Line-level adjudication of the §1.2 suspected-dead functions (def line
imported but function body never executed by any of the 1,862 tests, AND zero
static callers per vulture):

**Promoted to Category A (dead, delete in B1) — 12 functions:**

- `flaskr/service/billing/read_models.py:607,616,670,817,1503,1535,1548`
  (7 `build_*` page builders)
- `flaskr/service/billing/checkout.py:1142`
  (`_validate_plan_checkout_upgrade_only`)
- `flaskr/service/billing/primitives.py:140,154`
- `flaskr/service/billing/queries.py:483` (`subscription_has_attention`)
- `flaskr/api/tts/volcengine_protocol.py:276` (`encode_cancel_session`)

**Cleared (body covered at runtime — alive, drop from candidates):**
`flaskr/common/log.py:115,158`, `flaskr/common/config.py:1649,1668`,
`flaskr/common/cache_provider.py:9`, `flaskr/api/tts/volcengine_protocol.py:88`.

Caveat: "no test executes it" plus "no static caller" is decisive for
module-internal symbols, but the 7 NO-KNOWN-CONSUMER endpoints (§4) still
need production access-log evidence — local runs cannot prove external
non-usage, and production log reads require explicit user authorization.

## Pending follow-ups

- Production access-log check for the 7 NO-KNOWN-CONSUMER endpoints (needs
  user authorization for read-only cluster queries).
- Dev-server smoke coverage overlay (optional; symbol-level adjudication above
  is already decisive for B1 scope).
- `deadcode` tool second-opinion pass (this document is vulture-only).

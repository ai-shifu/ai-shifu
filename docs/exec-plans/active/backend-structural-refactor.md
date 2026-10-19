# Backend structural refactor

## Purpose / Big Picture

Make the backend (`src/api/flaskr`) cheaper to read and change for humans and
coding agents without changing behavior. Very large files and functions force
every reader to load thousands of unrelated lines; the method follows the
Nous Research "Refactoring Hermes with 1,393 agents" write-up: measure, split
the code into non-overlapping ownership groups, give each group a written
brief, run one isolated worktree worker per group, gate every step on
interface-preservation checks, and integrate centrally.

Observable outcome: the same routes, endpoint names, CLI commands, and
importable public names exist before and after; the backend test suite has the
same result; the structural metrics below shrink.

## Progress

- [x] 2026-10-19 09:10 CST: Built an isolated Python 3.11 test environment and
  recorded the baseline on unchanged main `a63a0bc62`: 12,318 passed,
  107 skipped; pre-existing failures are 2 in
  `tests/common/test_gunicorn_post_fork_langfuse.py` and 5 errors in
  `tests/test_langfuse_v4_semantics.py`.
- [x] 2026-10-19 09:15 CST: Recorded baseline metrics and the interface
  snapshot (491 modules, 306 routes, 16 CLI command entries).
- [x] 2026-10-19 09:40 CST: Dispatched six group workers (`billing-checkout`,
  `billing-wallets-cli`, `shifu`, `learn`, `user-order`,
  `dashboard-promo-llm`). The `billing-notifications` and `engine-tts`
  dispatches were blocked by the session's permission policy; those files
  stay untouched pending an owner decision.
- [x] 2026-10-19 CST: Owner decided to leave `billing-notifications` and
  `engine-tts` out of this round; they become follow-up work.
- [x] 2026-10-19 CST: Workers stopped on API rate limits after nine verified
  commits. Merged all six branches without conflicts. Integrated gates:
  interface snapshot OK (523 modules, routes and CLI identical); full suite
  12,318 passed with exactly the baseline failure set; engine tests 1,039
  passed; uow ratchet OK. Counts of `try`, `except`, `suppress(`,
  `unit_of_work(`, `on_commit`, and `db.session.commit` are unchanged, and
  the multiset of `yield` lines is identical.
- [x] 2026-10-19 CST: Owner approved recording relocated imports in the
  architecture baseline. Resumed workers committed the remaining splits
  (`checkout.py`, `dashboard/funcs.py`, `shifu/route.py`, `order/funs.py`,
  more `context_v2*`, learn routes, learner TTS audio, CLI/profile/callback
  routes, account cancellation) through all hooks. The first learn commit
  had skipped only the boundary hook; its follow-up commit records the
  relocated keys and every later commit ran all hooks.
- [x] 2026-10-19 CST: Second integration (19 non-merge commits, no
  conflicts). Interface snapshot OK (552 modules; routes and CLI identical);
  full suite 12,318 passed with exactly the baseline failure set; engine
  tests 1,039 passed; uow ratchet OK; boundary check passes with
  `--fail-on-stale-baseline`; `lefthook run pre-commit --all-files` passes
  all 20 checks.
- [x] 2026-10-19 CST: Reviewed the two regression classes the source write-up
  says tests missed. Removed public names: the snapshot compare reports none.
  Changed exception handling: counts of `try`, `except`, `finally`,
  `suppress(`, `raise`, `unit_of_work(`, `on_commit`, and
  `db.session.commit` are identical to baseline, as is the multiset of
  `yield` lines. Baseline audit: 29 keys added, each targeting a module the
  same package already had in the baseline; 4 stale keys removed.
- [ ] Follow-up groups: `billing-notifications`, `engine-tts`, and the
  unfinished items listed under Outcomes.

## Surprises & Discoveries

- Several tests statically inspect source layout (for example
  `tests/service/learn/test_runtime_tts_admission.py` looks up nested view
  functions inside `register_learn_routes`). Those are the only tests workers
  may edit, and only to follow moved code.
- Tests monkeypatch by module path (`flaskr.route.user`,
  `flaskr.service.order.funs`, ...), so moved code must keep resolving patched
  names through the original module. Workers used three mechanisms: lazy
  facade lookups (`checkout`, `subscriptions`, shifu routes, `api/llm`), a
  call-time proxy (`service/order/funs_lookup.py`), and module-class
  attribute forwarding (`service/learn/split_module_patching.py`, mirroring
  the existing `shifu/admin.py` pattern). New code in the split modules must
  call patched collaborators through these paths.
- Splitting a file moves its cross-service imports into new files, which the
  boundary check reports as new violations even when the dependency already
  exists. The owner chose to record those relocated keys in the baseline.
- The boundary checker treats only files named exactly `routes.py` /
  `route.py` as route adapters, so learn routes stayed in one `routes.py`.
- API rate limits stopped all workers mid-run; commits survived and workers
  were resumed with their context, as the source write-up describes.

## Decision Log

- Scope is the backend only. Frontend splitting needs its own gates (type
  check, Jest, e2e) and is left for a separate plan.
- Excluded: `flaskr/common/config.py` (mostly declarative env definitions),
  `flaskr/service/billing/models.py` (SQLAlchemy metadata feeds Alembic
  autogenerate), migrations, and `i18n`.
- Public names must stay importable from their original module even when no
  repository code imports them, because plugins under `flaskr/plugins/` are
  external.
- Workers must not rewrite exception handling (no `suppress()` conversions).

## Outcomes & Retrospective

| Metric (`flaskr/`, excluding migrations) | Baseline | After |
| --- | --- | --- |
| Python lines | 193,386 in 491 files | 198,057 in 552 files |
| Files over 1,500 lines | 22 | 13 |
| Functions over 150 lines | 115 | 88 |
| Functions over 300 lines | 24 | 17 |
| `register_admin_operations_routes` | 2,774 lines | ~30 |
| `register_shifu_routes` | 2,196 lines | ~120 |
| `register_user_handler` | 1,144 lines | under 150 |
| `register_billing_commands` | 984 lines | split per domain |
| `checkout.py` / `order/funs.py` / `context_v2.py` | 3,560 / 3,150 / 3,819 | 644 / 955 / ~1,160 |

Total lines grew about 2% because facades re-export every old name and new
modules repeat imports; the source write-up reports the same trade-off.

Not done in this round (candidates for follow-up groups):
`credit_notifications.py` and the engine/TTS code (out of scope by owner
decision); `learn/live_follow_up_routes.py`, `handle_input_ask`,
`runscript_v2.run_script`, `agent/run_agent.py`, `get_outline_item_tree`;
`shifu/admin_user_credits.py`, `courses_listing.py`, `save_shifu_draft_info`,
`import_shifu`, `ask_preview_api`; `route/user.py` (1,517 lines, kept whole
because most groups call names tests patch there); `api/llm/__init__.py`
(1,472 lines; `chat_llm` 171 lines); `_build_dashboard_course_learners`
(187 lines); `learn_tts_audio.py` (1,468 lines); and several 150-190 line
lock- and verification-sensitive functions in `service/user`.

Review hot spots: the three patch-compatibility mechanisms above; late
bottom-of-module imports in `api/llm/__init__.py`; the edited source-layout
test `tests/service/shifu/test_billing_debug_admission_contracts.py` (reads
the moved route files, assertions unchanged).

## Context and Orientation

Baseline metrics (`flaskr/`, excluding migrations), measured with the
harness `metrics.py` described below:

| Metric | Baseline |
| --- | --- |
| Python lines | 193,386 in 491 files |
| Files over 1,500 lines | 22 |
| Functions over 150 lines | 115 |
| Functions over 300 lines | 24 |
| Longest function | 2,774 lines (`register_admin_operations_routes`) |
| Longest if/elif chain | 10 |

Ownership groups (each worker edits only its files plus new sibling modules):

1. `billing-notifications`: `service/billing/credit_notifications.py`.
2. `billing-checkout`: `service/billing/checkout.py`, `subscriptions.py`,
   `settlement.py`, `manual_plan_grants.py`.
3. `billing-wallets-cli`: `service/billing/wallets.py`, `cli.py`,
   `read_models.py`, `customization.py`, `routes.py`.
4. `shifu`: `service/shifu/**` (both route modules, `admin_operations/*`,
   admin/draft/publish/import-export helpers).
5. `learn`: `service/learn/**` except `agent/engine/`.
6. `user-order`: `route/*.py`, `command/__init__.py`, `service/order/**`,
   `service/user/**`, `service/profile/**`, `service/profile_research/**`.
7. `dashboard-promo-llm`: `service/dashboard/**`, `service/promo/**`,
   `api/llm/**`.
8. `engine-tts`: `service/learn/agent/engine/**`, `service/tts/**`,
   `api/tts/**`.

## Plan of Work

Each worker receives the common brief plus its file list, works in its own
worktree branch, commits after each verified step, and reports metrics and
risks. The coordinator merges the branches into
`sunner/backend-structural-refactor`, resolves any conflicts, reruns all
gates, and records the results here.

## Concrete Steps

From `src/api` with the refactor virtualenv on `PATH`:

```bash
python /tmp/refactor-harness/snapshot.py . /tmp/after.json
python /tmp/refactor-harness/compare.py /tmp/refactor-harness/baseline-snapshot.json /tmp/after.json
python /tmp/refactor-harness/metrics.py .
python -m pytest -q -p no:cacheprovider -n 8
python -m pytest tests/service/learn/agent/engine/ -q
```

From the repository root:

```bash
python3 scripts/check_uow_commit_sites.py
python3 scripts/check_architecture_boundaries.py
lefthook run pre-commit --all-files
```

## Validation and Acceptance

- `compare.py` prints `OK`: no module or public name removed, routes
  (rule, methods, endpoint) and CLI commands/options identical.
- Full backend suite: same pass set as baseline; only the seven pre-existing
  Langfuse failures/errors remain.
- Engine offline tests green; uow ratchet and lefthook pass.
- Metrics shrink versus the baseline table.

## Idempotence and Recovery

Worker branches are independent; a failed worker is redispatched from its
last commit with a handoff note. Integration merges are repeatable; a bad
merge is reverted per branch. The baseline snapshot is regenerated from
`main` by checking it out and rerunning `snapshot.py`.

## Interfaces and Dependencies

No new dependencies. The harness scripts (`snapshot.py`, `compare.py`,
`metrics.py`) are temporary coordinator tooling and are not committed.

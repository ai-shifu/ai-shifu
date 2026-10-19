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
- [ ] Dispatch the eight group workers.
- [ ] Integrate worker branches, rerun every gate on the integrated branch.
- [ ] Review the integrated diff for removed public names and changed
  exception handling (the two regression classes the source write-up says the
  test suite missed).

## Surprises & Discoveries

- Several tests statically inspect source layout (for example
  `tests/service/learn/test_runtime_tts_admission.py` looks up nested view
  functions inside `register_learn_routes`). Those are the only tests workers
  may edit, and only to follow moved code.
- Tests monkeypatch by module path (`flaskr.route.user`,
  `flaskr.service.order.funs`, ...), so moved code must keep resolving patched
  names through the original module.

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

Pending.

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

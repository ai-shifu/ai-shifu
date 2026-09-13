# Unit-of-Work Commit-Site Migration

## Purpose / Big Picture

Finish the B4 batch of the backend overhaul: every remaining direct
`db.session.commit()` in `src/api/flaskr/` outside `flaskr/dao/` moves onto
the shared unit-of-work boundary in `src/api/flaskr/dao/uow.py`, so service
functions no longer commit state their callers cannot roll back. The
commit-site ratchet (`scripts/check_uow_commit_sites.py` against
`docs/generated/uow-commit-baseline.json`) ends at an empty baseline and is
enforced in CI, not only in the local pre-commit hook.

The migration lands as one pull request per batch. Every batch is deployed to
the `dev01` test environment through CI/CD and exercised end to end before it
is merged; merges are manual.

## Progress

- [x] 2026-09-13 CST: Re-baselined the inventory on `origin/main`: 146
  grandfathered sites in 53 files (213 at the 2026-07 inventory, 155 when the
  ratchet was introduced).
- [x] 2026-09-13 CST: PR-0 governance — fixed the `on_commit` ordering bug in
  `dao/uow.py` (callbacks ran before the depth counter reset, so a callback
  that opened its own unit of work never committed), added `unit_of_work(discard=True)`
  and `autonomous_unit_of_work`, wired the ratchet into the `Static Checks`
  workflow, and recorded the rules in `src/api/AGENTS.md`.
- [x] 2026-09-13 CST: B1 — config, feedback, profile, promo, learn_funcs,
  order (22 sites; baseline 146 -> 124). Promo helpers now join the order
  unit of work, config cache writes and Feishu notifications moved to
  `on_commit`, `import_activation_order` runs as two explicit steps.
- [x] 2026-09-13 CST: B2 — shifu services and `shifu/route.py` push-down
  (18 sites; baseline 124 -> 106). Permission grant/remove moved into
  `service/shifu/shifu_permission_funcs.py`; publish starts the summary
  thread, and creator transfer/copy run cache invalidation and post-auth,
  from `on_commit`; `save_shifu_mdflow` keeps `retry_on_deadlock` on the
  closure that owns the unit of work; `import_shifu` lost its `commit` flag.
- [x] 2026-09-13 CST: B3 — user services, `route/user.py` push-down, and
  retirement of `user/repository.py::transactional_session` (14 sites;
  baseline 106 -> 92). Verification codes persist the record in one unit
  of work before delivery and mark it sent in a second; onboarding
  completion retries on the idempotency rewrite; password set/change/reset
  moved into `service/user/password_flow.py`; avatar CDN warm-up runs from
  `on_commit`; the email/phone/Google sign-in flows use `unit_of_work()`
  (nested under the route's block) instead of a savepoint.
- [x] 2026-09-13 CST: B4 — referral, `billing/referral_plan_rewards`,
  lesson_feedback, listen_element helpers, CLI commands (19 sites; baseline
  92 -> 73). `process_referral_post_auth` runs as three steps (persist
  relation + reward; grant + mark succeeded; mark failed), invite-code
  collisions retry under a savepoint, lesson feedback uses the idempotency
  rewrite, both element backfills use `unit_of_work(discard=dry_run)`,
  `import_user` keeps the account step ahead of `init_buy_record`, and
  `update_demo_shifu` wraps each demo course in one unit of work.
- [x] 2026-09-13 CST: B5 — billing operations and scheduled paths (33 sites;
  baseline 73 -> 40). Manual credit / referral-reward grants use the
  idempotency rewrite (a `_once` helper owns the unit of work, the caller
  answers with the winner on IntegrityError), trial bootstrap enqueues its
  notification from `on_commit`, `grant_manual_plan_to_user` runs its lock
  body as one unit of work with `enqueue=True`, campaign writes commit
  before the detail read-back, `entitlements.grant_creator_manual_entitlement`
  lost its `commit` flag, and the billing CLI dropped `_rollback_on_error`.
- [ ] B6 — billing payment chain: notifications, checkout, webhooks,
  settlement (22 sites).
- [ ] B7 — streaming and long-running flows plus autonomous audit rows:
  runscript_v2, context_v2, minimax_voice_clone, check_risk, metering,
  audio_record_utils (18 sites).
- [ ] Move this plan to `docs/exec-plans/completed/` once the baseline is
  empty and CI enforces it.

## Surprises & Discoveries

- `uow.on_commit` callbacks executed while the committing block still counted
  as depth 1. A callback opening its own `unit_of_work()` was therefore
  treated as nested and never committed. Production reaches this through
  `shifu/admin_operations/courses_transfer_copy.py` (`on_commit(finish_transfer)`
  -> `run_creator_granted_post_auth` -> post-auth extensions ->
  `billing/trials.py::_bootstrap_new_creator_trial_credits`), which only
  worked because the trial bootstrap still committed directly. Fixed in PR-0
  before any batch touches those callers.
- The ratchet was only wired into lefthook; `.github/workflows/` never ran it,
  so contributors without lefthook (or using `--no-verify`) could add sites.
- `user/repository.py::transactional_session` was a second, savepoint-based
  transaction helper. The login routes already wrap its three callers in
  `unit_of_work()`, so the savepoint was redundant there; callers without
  that outer block (tests, scripts) saw `token_store.save`'s
  `uow.on_commit(populate_cache)` fire before the commit. Replacing it with
  `unit_of_work()` removes the second abstraction and fixes that ordering.
- `uow.app_context_scope(app)` originally reused ANY active app context. The
  celery `FlaskTask` wrapper pushes the resolved Flask app's context before a
  task runs, and multi-app test fixtures nest contexts of different apps; in
  both cases reusing the active context bound the session to the wrong
  database (`no such table` in the billing task tests once B5 migrated
  `dispatch_due_renewal_events`). It now reuses the context only when it
  belongs to the same app and pushes `app.app_context()` otherwise; the
  identity check unwraps `current_app` proxies, which the billing CLI passes
  as `app`.
- `service/check_risk/funcs.py` and `service/metering/recorder.py`
  deliberately push a fresh app context to get an independent session, because
  they persist audit rows in the middle of a /run stream and must not commit
  the caller's staged rows. `autonomous_unit_of_work(app)` makes that explicit.

## Decision Log

- 2026-09-13: Streaming and long-running flows (`runscript_v2.py`,
  `context_v2.py`, `minimax_voice_clone.py`) are migrated last, as several
  consecutive units of work per persistence step, never as one transaction
  spanning a generator `yield` or a provider call.
- 2026-09-13: `billing/checkout.py` is migrated inside the billing batch with
  `uow.app_context_scope(app)` rather than waiting for the external PR #2652,
  which wraps the same functions in `app.app_context()` and would switch
  sessions when called from inside another unit of work.
- 2026-09-13: Deliberately intermediate commits (claim -> external call ->
  finalize, `dry_run` previews, per-item backfills) become one unit of work per
  step; `unit_of_work(discard=dry_run)` replaces direct `rollback()` calls in
  preview paths.
- 2026-09-13: Provider or LLM HTTP calls that currently run inside a
  transaction (`shifu_publish_funcs.get_shifu_summary`,
  `checkout._create_provider_checkout`) are out of scope for this plan; the
  migration keeps the existing ordering and records the debt here.
- 2026-09-13: `order/admin.py::import_activation_order` keeps two units of
  work (account + credential, then price + success flip) with
  `init_buy_record` between them instead of one enclosing block:
  `init_buy_record` owns a `retry_on_deadlock` unit of work, and nesting it
  would let a deadlock retry silently discard the caller's rolled-back
  account writes while the retried order still commits.
- 2026-09-13: The idempotency rewrite (try a unit of work, re-read the winner
  on IntegrityError) only works when that unit of work is the OUTERMOST
  one: nested, the IntegrityError surfaces at the caller's commit, outside
  the handler. Callers of such functions (`grant_manual_credit_wallet_balance`,
  `grant_referral_reward_credits_to_user`, `complete_onboarding_scene`,
  `submit_lesson_feedback`) therefore do not wrap them in their own block;
  the billing CLI's `_rollback_on_error` wrapper was removed for that reason.
- 2026-09-13: Each batch is verified on `dev01` (branch force-pushed, CI/CD
  build and compose deploy). Non-payment flows are exercised through the UI
  and verified against the database; payment and webhook flows are covered by
  failure-path tests plus service calls from a Flask shell inside the
  container.

## Outcomes & Retrospective

Pending. Update after each batch with the ratchet count, test totals, and the
dev01 verification results.

## Context and Orientation

- Framework: `src/api/flaskr/dao/uow.py` — `unit_of_work()` (outermost commits,
  nested joins, classified cleanup on failure), `on_commit(callback)`,
  `app_context_scope(app)`, the `discard` flag, `autonomous_unit_of_work(app)`.
- Ratchet: `scripts/check_uow_commit_sites.py` counts `db.session.commit()`
  under `src/api/flaskr/` outside `dao/` and compares with
  `docs/generated/uow-commit-baseline.json`; any increase fails, any decrease
  requires `--update`. Wired into lefthook pre-commit and the `Static Checks`
  workflow.
- Reference migrations: `service/order/funs.py`, `service/billing/renewal.py`,
  `service/billing/routes.py`, `learn/run/recorder.py` (one unit of work per
  recorder step, never across a `yield`), PR #2651 (`service/shifu/funcs.py`).
- Failure-path test pattern: `src/api/tests/service/order/test_uow_failure_paths.py`,
  `src/api/tests/service/billing/test_renewal_uow_failure_paths.py`.
- Remaining sites by module at the 2026-09 re-baseline: billing 57, shifu 18,
  learn 11, tts 11, referral 10, user 9, promo 8, route 5, order 4, profile 4,
  command 3, config 3, check_risk 1, feedback 1, metering 1.

## Plan of Work

Batches, dependencies, and the non-mechanical sites in each:

| Batch | Scope | Sites | Depends on |
|---|---|---|---|
| PR-0 | governance + `uow.py` fix | 0 | — |
| B1 | config, feedback, profile, promo, learn_funcs, order | 22 | PR-0 |
| B2 | shifu services, `shifu/route.py` push-down | 18 | PR-0 |
| B3 | user services, `route/user.py` push-down, `transactional_session` retirement | 14 | PR-0 |
| B4 | referral, referral_plan_rewards, lesson_feedback, listen_element, command | 19 | B1 |
| B5 | billing operations: wallets, cli, subscriptions, trials, campaigns, operation_credits, manual_plan_grants, daily_aggregates, domains, entitlements, referral_reward_grants, tasks | 33 | PR-0 |
| B6 | billing payment chain: notifications, checkout, webhooks, settlement | 22 | B5 |
| B7 | runscript_v2, context_v2, minimax_voice_clone, check_risk, metering, audio_record_utils | 18 | B4, B5 |

Rewrite rules that apply to every batch:

- `with app.app_context():` becomes `with app_context_scope(app), unit_of_work():`;
  early-return and end-of-function commits are deleted; generated ids come
  from `db.session.flush()`.
- Side effects that used to follow a commit (Feishu, SMS, celery enqueue,
  cache writes, background threads) move into `uow.on_commit`.
- Module-local `_with_app_context` / `_maybe_app_context` helpers are replaced
  by `uow.app_context_scope`.
- `IntegrityError` idempotency (`try: commit except IntegrityError: rollback;
  re-read`) becomes `try: with unit_of_work(): ... except IntegrityError: with
  unit_of_work(): re-read and update`. A retry that must stay inside a larger
  transaction (`referral/service.py::_create_invite_code_with_retry`) uses a
  manual `db.session.begin_nested()` savepoint instead.
- Route-level commits (`route/user.py`, `shifu/route.py`) move the boundary
  into a service function; routes only validate and call.
- Intentional intermediate commits (claim -> provider call -> finalize;
  per-item backfills) become consecutive units of work, each with a test that
  proves the must-persist step survives a later failure.

Non-mechanical sites by batch:

- B1: `feedback/funs.py` Feishu notify and `config/funcs.py` cache writes go
  through `on_commit`; `promo/funcs.py` stops opening its own app context so
  it joins the order transaction (and the `stub_promo_side_sessions` fixture in
  `tests/service/order/test_uow_failure_paths.py` is removed); `order/admin.py`
  `import_activation_order` becomes one unit of work around `init_buy_record`.
- B2: `shifu_mdflow_funcs.py` keeps `@retry_on_deadlock()` on the closure that
  owns the outermost unit of work; `shifu_publish_funcs.py` starts the summary
  thread from `on_commit`; `shifu_import_export_funcs.py` drops its `commit`
  flag; `shifu/route.py` permission endpoints move into a new
  `service/shifu/shifu_permission_funcs.py`.
- B3: `user/utils.py` verification-code flow becomes two units of work around
  the delivery call; `route/user.py` password endpoints move into
  `service/user/password_flow.py`; `transactional_session` is deleted and its
  callers (`email_flow.py`, `phone_flow.py`, `auth/providers/google.py`) use
  `unit_of_work()`.
- B4: `referral/service.py::process_referral_post_auth` becomes three steps
  (persist relation and reward; grant and mark succeeded; mark failed);
  `lesson_feedback.py` uses the idempotency rewrite;
  `listen_element_mdflow_backfill.py` uses `unit_of_work(discard=dry_run)`; CLI commands wrap
  their whole run.
- B5: `billing/cli.py::_rollback_on_error` is deleted; per-user backfills use
  one unit of work per iteration; `wallets.py`/`trials.py`/
  `referral_reward_grants.py` use the idempotency rewrite;
  `manual_plan_grants.py` relies on `enqueue=True` instead of manual enqueue
  loops; `entitlements.py` drops its `commit` flag.
- B6: `checkout.py::create_billing_order_checkout` splits the commit-then-raise
  expiry path into two units of work; `notifications.py` becomes claim ->
  provider -> finalize with one unit of work per step; webhook and sync paths
  dispatch `order_update` from `on_commit`.
- B7: `runscript_v2.py` finalizes rider writes through a recorder step;
  `context_v2.py::reload` stops pushing a nested app context inside the
  producer thread; `minimax_voice_clone.py` becomes claim -> provider ->
  finalize; `check_risk` and `metering` use `autonomous_unit_of_work(app)`;
  `audio_record_utils.py` drops its `commit` flag.

## Concrete Steps

For each batch:

1. Branch from the latest `origin/main`.
2. Migrate the listed sites; keep a per-function map of old commit points to
   new boundaries for the PR description.
3. Add `tests/service/<module>/test_<module>_uow_failure_paths.py` covering:
   a mid-flow failure leaves no partial rows; `on_commit` side effects do not
   fire on rollback; must-persist steps survive a later failure.
4. `python scripts/check_uow_commit_sites.py --update`; the baseline diff must
   only remove entries or lower counts.
5. `cd src/api && pytest tests/service/<module> tests/test_uow.py
   tests/service/common/test_uow.py -q`, plus `tests/golden` for learn
   batches, and the full suite before opening the PR.
6. `lefthook run pre-commit --all-files`; `python scripts/check_repo_harness.py`
   when docs change; `python scripts/check_architecture_boundaries.py`.
7. Push the branch, force-push it to `dev01`, wait for the CI/CD build and
   deploy, and exercise the flows listed under Validation.
8. Open the PR, record the dev01 results in it, and update this plan's
   Progress after merge.

## Validation and Acceptance

- `python scripts/check_uow_commit_sites.py` prints `uow commit-site ratchet
  OK (0 grandfathered sites)` after B7.
- The `Static Checks` workflow shows the ratchet step on every pull request.
- The backend suite passes; each batch adds its failure-path tests.
- dev01 verification per batch (UI flows plus database checks; payment paths
  through Flask shell calls inside the API container):
  - B1: promotions and coupons admin, coupon checkout to a zero-price order,
    feedback submission, config edits (tables: promo/coupon, order_orders,
    feedback, config, Redis cache).
  - B2: course creation, outline edits and reordering, MDF save with a
    concurrent editor, publish and summary, import/export, permission grant
    and removal, course transfer and copy.
  - B3: phone-code, email-code, and Google sign-in for new and existing users
    (with learning-record merge), guest to registered upgrade, set/change/reset
    password, profile update, avatar upload (tables: user_users,
    user_auth_credentials, token store and its Redis cache timing).
  - B4: invite-code creation, invited sign-up and reward grant including a
    forced grant failure, duplicate lesson feedback, `import_user` and
    `update_demo_shifu` commands.
  - B5: manual plan and credit grants with repeated request ids, wallet
    adjustments, domain binding, trial claim, billing CLI commands, one
    scheduled aggregate run.
  - B6: checkout, webhook, sync, and refund service calls; expired-order
    reopen; notification state in `billing_order.metadata_json`.
  - B7: a full /run lesson including reconnect, reload, and ask; audio
    backfill; voice-clone submit with success and failure; golden SSE
    fixtures unchanged.

## Idempotence and Recovery

- Every batch is a self-contained PR that can be reverted on its own; the
  ratchet baseline is regenerated by the same script in both directions, so a
  revert restores the previous counts with `--update`.
- Rewritten flows keep their existing Redis locks and idempotency keys, so a
  rerun after a rollback behaves exactly like a retry of the old code.
- dev01 is a disposable environment: force-pushing the next batch (or `main`)
  to the `dev01` branch resets it.

## Interfaces and Dependencies

- `src/api/flaskr/dao/uow.py` is the only transaction API for service code:
  `unit_of_work`, `on_commit`, `in_unit_of_work`, `app_context_scope`,
  `unit_of_work(discard=...)`, `autonomous_unit_of_work`.
- `src/api/flaskr/dao/__init__.py` provides the classified session cleanup
  (`cleanup_session_after`, `invalidate_session`, `retry_on_deadlock`) that
  the unit of work delegates to.
- `scripts/check_uow_commit_sites.py`, `docs/generated/uow-commit-baseline.json`,
  `lefthook.yml`, `.github/workflows/repo-harness.yml` enforce the ratchet.
- `docs/exec-plans/active/backend-overhaul-master.md` (B4) is the parent plan;
  `docs/exec-plans/active/backend-inventory-2026-07.md` holds the original
  per-file inventory.

# ExecPlan: Billing Subscription Preorder

## Purpose / Big Picture

实现套餐预购与已预购后立即升级抵扣，让不支持自动扣费的支付链路可以提前收款，并在当前周期结束后续订或降级生效；当用户在已预购状态下选择更高等级套餐时，旧预付款抵扣升级费用，新套餐立即生效且不产生退款。

来源设计：

- `docs/design-docs/billing-subscription-preorder.md`
- `docs/billing-subscription-design.md`

核心边界：订阅、订单、钱包桶、账本仍是唯一账务真相源；预购只扩展套餐支付和周期切换，不改变 topup 积分包的独立购买模型。

## Progress

- [x] 2026-05-25 09:15 CST: Added the proposed preorder design document and linked it from the billing subscription design.
- [x] 2026-05-25 09:20 CST: Add this active ExecPlan and regenerate repository knowledge indexes.
- [x] 2026-05-25 09:25 CST: Inspect current checkout, paid-order, renewal, wallet, DTO, and tests before editing.
- [x] 2026-05-25 09:35 CST: Implement backend preorder helpers and checkout action routing.
- [x] 2026-05-25 10:10 CST: Implement preorder paid side effects, cycle-end activation, and immediate-upgrade offset.
- [x] 2026-05-25 10:40 CST: Add focused backend regression coverage.
- [x] 2026-05-25 11:00 CST: Run focused validation and update the draft PR branch.

## Surprises & Discoveries

- Existing self-managed Pingxx renewal already reserved future-cycle subscription credits and released them at cycle boundary; preorder can reuse that ledger and bucket model with explicit metadata states.
- The existing `downgrade_effective` event only switched `next_product_bid`; paid preorder activation needs to consume the matching paid renewal order at the same boundary so credits and cycle windows are applied together.

## Decision Log

- Use the existing PR branch `codex/billing-subscription-preorder-design` and keep unrelated untracked local files out of commits.
- Start with backend behavior and tests because the current creator checkout API already owns subscription purchase decisions.

## Outcomes & Retrospective

Implemented backend preorder support for self-managed payment channels, including one active preorder per subscription, delayed credit availability, cycle-end activation, and paid-preorder offset for immediate upgrades. Focused billing route and renewal execution tests pass locally.

Validation completed:

- `cd src/api && pytest tests/service/billing/test_billing_write_routes.py tests/service/billing/test_billing_renewal_execution.py -q`
- `python scripts/check_repo_harness.py`
- `git diff --check`
- `SKIP=check-architecture-boundaries pre-commit run -a`

`pre-commit run -a` without skips reached the architecture-boundary hook and reported unrelated violations from existing untracked `src/api/flaskr/service/learn/http/*`, `src/api/flaskr/service/shifu/http/*`, and route-support files in the local worktree.

## Context and Orientation

Relevant docs:

- `docs/design-docs/billing-subscription-preorder.md`
- `docs/billing-subscription-design.md`

Likely backend surfaces:

- `src/api/flaskr/service/billing/checkout.py`
- `src/api/flaskr/service/billing/subscriptions.py`
- `src/api/flaskr/service/billing/renewal.py`
- `src/api/flaskr/service/billing/models.py`
- `src/api/flaskr/service/billing/consts.py`
- `src/api/flaskr/service/billing/dtos.py`
- `src/api/flaskr/service/billing/serializers.py`
- `src/api/flaskr/service/billing/read_models.py`
- `src/api/tests/service/billing/`

Existing behavior to preserve:

- `subscription_start` activates immediately when there is no active plan.
- Existing immediate upgrade paid apply switches `product_bid`, clears `next_product_bid`, resets the cycle, and grants subscription credits.
- Existing Pingxx/native/manual self-managed cycle calculation remains the source of local validity windows.
- Existing renewal reservation/release behavior must stay idempotent.

## Plan of Work

1. Add an active ExecPlan and update generated indexes.
2. Add preorder constants/helper functions around metadata states and plan tier resolution.
3. Extend checkout decision logic so active subscribers can choose immediate upgrade or preorder.
4. Record preorder state in `bill_orders.metadata` and subscription metadata.
5. Prevent multiple active preorders and prevent cancel/target switch through self-service.
6. Extend paid-order side effects so preorder payment reserves or records credits without making them available before cycle end.
7. Extend renewal/cycle-end handling to apply paid preorder, clear old credits, and activate the target product.
8. Extend immediate upgrade so an existing preorder offsets the upgrade payable amount and is marked absorbed.
9. Add focused tests for action validation, one-preorder invariant, payment side effects, cycle-end activation, idempotency, and upgrade offset.
10. Run focused pytest and repository harness checks.

## Concrete Steps

1. Inspect the current checkout route and test helpers to identify stable extension points.
2. Add metadata helpers in the billing service layer:
   - `resolve_plan_tier`
   - `find_active_preorder_order`
   - `mark_preorder_pending_effective`
   - `mark_preorder_absorbed`
   - `mark_preorder_effective_applied`
3. Extend `create_billing_subscription_checkout` request handling:
   - no active subscription -> `subscription_start`
   - `action=upgrade_immediate` -> target tier must be higher
   - `action=preorder` -> target tier must be current or lower and no active preorder exists
   - active preorder -> only immediate upgrade is allowed
4. Store preorder metadata on pending and paid preorder orders.
5. During preorder paid apply:
   - do not make credits available immediately
   - set `next_product_bid`
   - store `preorder_order_bid`
   - sync renewal/downgrade-effective event for the current period end
6. During cycle-end application:
   - consume the linked paid preorder order
   - expire old subscription bucket credits
   - release reserved credits or grant target credits
   - update subscription cycle and product
   - mark preorder effective applied
7. During immediate upgrade with an active preorder:
   - reduce upgrade payable amount by old paid preorder amount
   - mark old preorder absorbed by the upgrade order
   - clear preorder subscription metadata
   - activate and grant upgrade normally
8. Add or update tests under `src/api/tests/service/billing/`.
9. Regenerate docs indexes and run validations.

## Validation and Acceptance

- Active user with no preorder can immediately upgrade to a higher-tier plan.
- Active user with no preorder can preorder the same or a lower-tier plan.
- Active user with a preorder cannot create another preorder or switch target.
- Active user with a preorder can immediately upgrade; payable amount equals target price minus paid preorder amount.
- Paid preorder does not make new credits available before cycle end.
- Cycle-end preorder activation expires old subscription credits and makes the target plan credits available.
- Expired paid users are treated as new purchase users.
- Active trial users can upgrade but cannot preorder; expired trial users cannot self-service buy trial again.
- Repeated webhook/sync calls do not duplicate grants, absorb the same preorder twice, or apply preorder twice.

Minimum checks:

```bash
python scripts/build_repo_knowledge_index.py
python scripts/check_repo_harness.py
cd src/api && pytest tests/service/billing/test_billing_write_routes.py tests/service/billing/test_billing_renewal_execution.py -q
```

## Idempotence and Recovery

- `bill_orders` remains the payment truth source and `grant:{bill_order_bid}` remains the primary grant idempotency key.
- Preorder metadata state transitions are monotonic:
  `pending_effective -> effective_applied` or
  `pending_effective -> absorbed_by_upgrade`.
- If checkout succeeds but provider callback is delayed, the order can be synced later and will apply the same preorder state.
- If cycle-end activation is retried, an already `effective_applied` preorder should be a no-op.
- If immediate upgrade callback is retried, an already `absorbed_by_upgrade` preorder should not discount a second order.

## Interfaces and Dependencies

- Existing creator route: `POST /api/billing/subscriptions/checkout`
- Existing order sync route: `POST /api/billing/orders/{bill_order_bid}/sync`
- Existing subscription fields: `product_bid`, `next_product_bid`, `metadata`
- Existing order fields: `order_type`, `payable_amount`, `paid_amount`, `metadata`
- Existing wallet bucket fields: `available_credits`, `reserved_credits`, `effective_from`, `effective_to`
- Existing renewal events: `renewal`, `downgrade_effective`, `expire`

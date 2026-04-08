# Billing Rollout Runbook

更新日期：2026-04-08

## 1. 目标

本 runbook 只覆盖 creator billing v1 的上线、迁移、回填、监控告警和回滚操作，不覆盖 v1.1 的 entitlement/domain/report 扩展。

上线目标：

- 让 creator 侧 `/admin/billing`、`/api/billing/*`、Stripe/Pingxx 支付链路和 credit settlement 在生产环境可控上线
- 保持旧 `/api/order/*` 学员购课链路不受影响
- 保证 `billing_orders`、`billing_subscriptions`、`credit_wallets`、`credit_wallet_buckets`、`credit_ledger_entries` 一致

## 2. 上线前检查

发布前必须确认：

- 最新代码已包含 billing models、migrations、CLI、Celery tasks 和前端 `/admin/billing`
- `flask db upgrade` 将会应用 billing 相关 revision：
  - `4fd52d0d9a01_add_billing_core_tables.py`
  - `8f1d2c3b4a5e_add_billing_rate_and_renewal_tables.py`
  - `9c1d2e3f4a5b_harden_billing_schema_and_seed_rates.py`
  - `ab12cd34ef56_seed_billing_sys_configs.py`
- Redis、`celery-worker`、`celery-beat` 已部署且与 API 使用同一套配置
- Stripe webhook 继续走旧入口 `/api/order/stripe/webhook`
- Pingxx callback 继续走旧入口 `/api/callback/pingxx-callback`
- `sys_configs` 中以下 key 已存在：
  - `BILLING_ENABLED`
  - `BILLING_LOW_BALANCE_THRESHOLD`
  - `BILLING_RENEWAL_TASK_CONFIG`
  - `BILLING_RATE_VERSION`

## 3. 迁移步骤

建议顺序：

1. 先发后端代码，但保持 creator billing 入口处于关闭或内部可见状态。
2. 执行数据库迁移：`cd src/api && FLASK_APP=app.py flask db upgrade`
3. 校验新表已创建：
   - `billing_products`
   - `billing_subscriptions`
   - `billing_orders`
   - `credit_wallets`
   - `credit_wallet_buckets`
   - `credit_ledger_entries`
   - `credit_usage_rates`
   - `billing_renewal_events`
4. 校验 seed：
   - `billing_products` 中存在 2 个 plan + 2 个 topup SKU
   - `credit_usage_rates` 已覆盖 `production / preview / debug`
   - `sys_configs` 已写入 billing feature flag 和 rate version
5. 启动或滚动更新 `celery-worker` 与 `celery-beat`
6. 再发前端并打开 creator billing 导航

## 4. 回填与修复

统一优先使用已有 CLI，不要手写 SQL 修改账本。

常用命令：

```bash
cd src/api
FLASK_APP=app.py flask console billing backfill-settlement --usage-bid <usage_bid>
FLASK_APP=app.py flask console billing rebuild-wallets --creator-bid <creator_bid>
FLASK_APP=app.py flask console billing reconcile-order --billing-order-bid <billing_order_bid>
FLASK_APP=app.py flask console billing run-renewal-event --renewal-event-bid <renewal_event_bid>
FLASK_APP=app.py flask console billing retry-renewal --renewal-event-bid <renewal_event_bid>
```

操作原则：

- settlement 异常优先用 `backfill-settlement` 或 replay，不要直接改 `credit_ledger_entries`
- 钱包快照异常优先用 `rebuild-wallets`
- webhook 丢失或 provider 状态不一致优先用 `reconcile-order`
- 续费事件异常优先用 `run-renewal-event` 或 `retry-renewal`

## 5. 上线验证

至少做以下冒烟：

1. Creator 进入 `/admin/billing` 能看到 catalog、overview、orders。
2. Stripe topup 成功后：
   - `billing_orders` 进入 `paid`
   - `credit_wallet_buckets` 新增 topup bucket
   - `credit_ledger_entries` 新增 grant entry
   - `credit_wallets.available_credits` 增加
3. Stripe subscription 首次支付成功后：
   - `billing_subscriptions` 进入 `active`
   - 首期 bucket / ledger / wallet 已写入
4. Pingxx topup 成功后：
   - 旧 callback 入口能推进 `billing_orders`
   - 不影响旧 `/order` 流程
5. 对同一 creator 触发多条 usage settlement：
   - Celery 按 creator 维度串行
   - `free > subscription > topup` 顺序正确

## 6. 监控与告警

上线后重点关注：

- provider callback 失败率
  - Stripe `/api/order/stripe/webhook`
  - Pingxx `/api/callback/pingxx-callback`
- `billing_orders` 长时间停留在 `init/pending`
- `billing_renewal_events` 中 `failed` / `processing` 积压
- `credit_wallet_buckets` 到期任务失败或 backlog
- `billing.settle_usage` 任务异常率
- 低余额告警数量异常增长
- orphan webhook 数量异常增长

建议最少落地以下可观测项：

- API error log：按 route + provider 聚合
- Celery task error log：按 task name 聚合
- 订单状态分布看板：`init / pending / paid / failed / refunded`
- 续费事件状态分布看板：`pending / processing / succeeded / failed`

## 7. 回滚策略

回滚原则：不回滚账本，不删除已写入的 wallet/ledger/order 数据，优先“停止入口 + 前滚修复 + CLI 补偿”。

分级处理：

- 仅前端异常：
  - 关闭 creator billing 导航或隐藏 `/admin/billing` 入口
  - 保持后端和 callback 在线，避免丢支付结果
- 仅后台任务异常：
  - 暂停 `celery-beat`
  - 保留 `celery-worker` 处理手动触发的修复任务，或按需下线 worker
  - 用 CLI 手动执行 `reconcile-order` / `retry-renewal` / `rebuild-wallets`
- 支付状态推进异常：
  - 保持 webhook 入口不下线
  - 暂停新的 creator checkout 入口
  - 对受影响订单执行 `reconcile-order`
- settlement 异常：
  - 暂停新的 usage settlement 任务投递
  - 用 `backfill-settlement` 和 `rebuild-wallets` 做 repair

不要做的事：

- 不要手工删除 `credit_ledger_entries`
- 不要手工回退 Alembic revision 来“撤销”已上线账务表
- 不要让旧 `/order` callback 停机，因为 billing 仍复用这些入口

## 8. 上线完成标准

满足以下条件后可视为 v1 稳定上线：

- creator billing checkout、sync、wallet、orders 正常
- 连续一个观察窗口内无重复 grant / 重复 consume / 状态回退问题
- 续费任务、bucket 过期任务、低余额任务无持续积压
- 旧 `/order` 学员购课链路回归通过

# Billing 交付任务

## 已完成调研与文档整理

- [x] 审查现有课程订单与支付流程。
- [x] 审查现有 metering 与 runtime config 流程。
- [x] 确认计费主体、产品范围、续费模式、权益范围和文档存放路径。
- [x] 将商品目录统一为 `billing_products` 单表，并保留 `plans[]` / `topups[]` API 投影。
- [x] 将支付持久化模型统一为 `billing_orders`，并将最近一次 provider payload 收敛到 `billing_orders.metadata`。
- [x] 统一扣分场景为 `production`、`preview`、`debug`，并明确由课程所属创作者承担。
- [x] 统一 LLM `input/cache/output` 与 TTS `按次/按字数` 的扣分口径。
- [x] 将库表分层为 `v1 核心表` 与 `v1.1 扩展表`。
- [x] 将设计文档重写为表格化字段定义，并统一字段编码规范。
- [x] 将 billing 文档编码体系调整为“复用共享码 + billing 专属 `7100+` 段位”。
- [x] 将现有代码改造边界补充进设计文档。
- [x] 将 Celery 作为 v1 基础设施接入方案补充进设计文档。
- [x] 将 `credit_wallet_buckets`、积分来源优先级和 `GET /billing/wallet-buckets` 约束补充进设计文档。

## 当前实现批次：Figma `方案1` Billing UI + 可联调后端 MVP

- [x] 将当前批次范围同步到 `docs/billing-subscription-design.md`，明确 Figma `方案1` 浅色稿、provider 能力矩阵和暂缓项。
- [x] 在 creator admin 入口补齐侧边栏会员卡和 `会员与积分` 导航。
- [x] 新增 `/admin/billing`，按 `套餐与积分`、`积分明细`、`付款记录` 三个 tab 落地 Billing Center。
- [x] 新增 `src/cook-web/src/components/billing/`、`src/cook-web/src/types/billing.ts` 和 `module.billing.*` i18n。
- [x] 新增 `/payment/stripe/billing-result`，回跳后先调用 `/billing/orders/{billing_order_bid}/sync` 再回到 `/admin/billing`。
- [x] 新增 `service/billing` 模块与 `/api/billing` 路由，不复用旧 `order_*` 表。
- [x] 新增 `billing_products`、`billing_subscriptions`、`billing_orders`、`credit_wallets`、`credit_wallet_buckets`、`credit_ledger_entries` 迁移和 seed。
- [x] 实现 `GET /billing/catalog`、`GET /billing/overview`、`GET /billing/wallet-buckets`、`GET /billing/ledger`、`GET /billing/orders`、`GET /billing/orders/{billing_order_bid}`。
- [x] 实现 `POST /billing/subscriptions/checkout`、`POST /billing/subscriptions/cancel`、`POST /billing/subscriptions/resume`、`POST /billing/topups/checkout`、`POST /billing/orders/{billing_order_bid}/sync`。
- [x] 复用现有 `/api/order/stripe/webhook`、`/api/callback/pingxx-callback` 处理 billing webhook，并确保 `billing_orders` 状态机幂等。
- [x] 在本批次里固定 Stripe 支持套餐 + topup，Pingxx 仅支持 topup，subscription 返回 `unsupported`。
- [x] 支付成功后真实刷新 `billing_orders`、`billing_subscriptions`、`credit_wallets`、`credit_wallet_buckets`、`credit_ledger_entries`，保证前端可联调。
- [x] 增加本批次的前后端联调测试与旧 `/order` 路径回归测试。

本批次暂缓：

- `bill_usage -> credit_ledger_entries` 结算。
- Celery settlement、creator 维度串行化与防重入。
- 自动续费排期、失败重试、bucket 过期扫描、低余额提醒。
- daily aggregate、admin adjust、entitlements/domains/reports 扩展。

## v1 核心交付

### 产品与费率

- [x] 冻结套餐、充值包、试用积分和赠送积分的最终业务规则。
- [x] 冻结 `free > subscription > topup` 的 bucket 扣减优先级、同优先级到期排序和退款返还归类规则。
- [x] 冻结升级、降级、取消、恢复、宽限期和退款规则。
- [x] 冻结 `production`、`preview`、`debug` 三个 scene 的 provider/model/metric 费率矩阵。
- [x] 冻结低余额阈值、告警触发条件和 billing 错误码文案。

### 现有代码改造

- [x] 明确并落地 `service/order/payment_providers` 在 billing 域的复用边界，不复用旧 `order_*` 表。
- [x] 新增 `service/billing/consts.py`，统一承载 billing 专属 `7100+` 编码。
- [x] 扩展 `payment_providers/base.py` 支持 billing recurring/subscription/webhook 统一接口。
- [x] 调整 metering 的 `debug/preview` billable 逻辑，移除常量层硬编码 non-billable 判定。
- [x] 在 learn/preview/debug 入口接入 creator admission service。
- [x] 增加 `shifu_bid -> creator_bid` 的 ownership resolver 供 settlement 使用。
- [x] 明确 learn/preview/debug 请求线程只做 admission + usage 落库，不直接执行积分扣减。
- [x] 明确并保留不改的旧链路：`/order` API、旧 order admin、raw `bill_usage` 结构、全局 `/api/config`。

### Schema 与迁移

- [x] 新增 `billing_products`、`billing_subscriptions`、`billing_orders`。
- [x] 新增 `credit_wallets`、`credit_wallet_buckets`、`credit_ledger_entries`、`credit_usage_rates`、`billing_renewal_events`。
- [x] 为核心表补齐索引、唯一约束和基础 seed 数据。
- [x] 在 `sys_configs` 中增加 billing feature flag、低余额阈值、续费任务配置和 rate version 配置。

### 支付与订阅

- [x] 实现统一的 billing payment orchestration，并在 adapter 层封装 Stripe/Pingxx 差异。
- [x] 实现 subscription checkout、cancel、resume 和退款流程。
- [x] 实现 topup checkout 与到账流程。
- [x] 实现 `GET /billing/wallet-buckets` creator 侧只读接口。
- [x] 实现 `GET /billing/orders`、`GET /billing/orders/{billing_order_bid}`、`POST /billing/orders/{billing_order_bid}/sync` 三个 creator 侧接口。
- [x] 实现基于 `billing_orders` 的 webhook 幂等状态机，确保重复和乱序回调不会回退状态或重复入账。
- [x] 在 `billing_orders.metadata` 中仅保留最近一次 provider 原始 payload 与事件摘要。
- [x] 实现找不到关联订单的 webhook ignore 策略，并依赖 sync/reconcile 补偿。
- [x] 实现订阅生命周期推进，包括开通、升级、续费、宽限期、取消和降级排期。
- [x] 确认国内支付通道 recurring capability，并对不支持能力返回 `unsupported`。

### 计量与结算

- [x] 实现 `bill_usage -> credit_ledger_entries` 的多维度结算逻辑。
- [x] 实现 `billing.settle_usage` Celery task，作为默认积分扣减入口。
- [x] 实现 `credit_wallet_buckets` 的来源分桶、余额汇总和生命周期状态推进。
- [x] 实现 `free > subscription > topup` 的 bucket 选择顺序，并在同优先级下按最早到期、最早创建扣减。
- [x] 实现 LLM `input/cache/output` 三维扣分。
- [x] 实现 TTS `按次` 与 `按字数` 两种计费模式。
- [x] 实现 `production`、`preview`、`debug` 三场景的 creator 归属解析。
- [x] 实现 `creator_bid` 维度的 settlement 串行化与防重入，避免多个学生同时学习同一 creator 课程时并发扣减算错。
- [x] 实现账本不可变写入和钱包乐观锁更新。
- [x] 为 `credit_ledger_entries` 增加 `wallet_bucket_bid` 字段，并让 `idempotency_key` 包含 bucket 维度。
- [x] 实现 bucket 到期、耗尽和 refund return -> `free` bucket 的状态迁移规则。
- [x] 实现余额不足、订阅失效的前置拦截。
- [x] 实现结算幂等 key 和 replay 安全，避免重复扣分。

### Celery 与基础设施

- [ ] 引入 Redis broker 与 Celery worker/beat 进程配置。
- [x] 新增 Celery app factory，并让 worker 复用 Flask `create_app()` 配置。
- [ ] 在 `requirements.txt`、配置定义和环境变量示例中接入 Celery/Redis 配置。
- [ ] 在 `docker-compose.yml`、`docker-compose.latest.yml`、`docker-compose.dev.yml` 中增加 `redis`、`celery-worker`、`celery-beat`。
- [ ] 为 usage settlement、renewal、retry、reconcile、settlement replay、low balance alert 注册 Celery tasks。
- [ ] 增加 wallet bucket 过期扫描与 `expire` ledger 落账任务。
- [ ] 实现 `billing_renewal_events` 的入队、抢占和幂等执行。
- [ ] 实现 webhook 补偿同步和失败续费重试。
- [ ] 保留 Flask CLI 作为 backfill / rebuild / manual replay 入口，并与 Celery 任务分工清晰。

### 前端与管理端

- [ ] 在 `src/cook-web/src/app/admin/layout.tsx` 增加 Billing 菜单入口。
- [ ] 新增 `src/cook-web/src/app/admin/billing/page.tsx`，实现单路由 Billing Center。
- [ ] 在 Billing Center 中实现 `Overview`、`Ledger`、`Orders` 三个 tab。
- [ ] 在 `src/cook-web/src/api/api.ts` 中增加 billing 前后台接口定义。
- [ ] 新增 `src/cook-web/src/types/billing.ts`，定义 billing 前端类型。
- [ ] 新增 `src/cook-web/src/components/billing/` 组件目录，拆分 overview、catalog、ledger、orders、checkout、detail sheet 组件。
- [ ] 实现套餐/充值包目录、购买流程、订阅卡片和钱包余额展示。
- [ ] 为 wallet 来源明细接入 `GET /billing/wallet-buckets` 的按需查询与只读展示。
- [ ] 实现账本、creator 侧订单、取消订阅和恢复订阅交互。
- [ ] 为 `BillingOrderDetailSheet` 接入 `GET /billing/orders/{billing_order_bid}`。
- [x] 新增 Stripe billing result 页，并接入 `sync/detail` 接口后回跳 `/admin/billing`。
- [ ] 将 `billing_alerts` 渲染改为基于 `code/severity/message_key/message_params` 的结构化展示。
- [ ] 实现 admin 侧订阅、订单、账本调整和异常处理页面。
- [ ] 增加 `module.billing.*` i18n keys，并补齐状态码到文案的映射。

### 测试与上线

- [ ] 增加支付、订阅生命周期、webhook 幂等、乱序回调、ignore orphan webhook 和退款测试。
- [ ] 增加结算、余额计算、积分消耗顺序和三场景扣分测试。
- [ ] 增加多个学生并发学习同一 creator 课程时，Celery 串行扣减仍然准确的测试。
- [ ] 增加多 bucket 拆分扣减、bucket 过期和 `credit_wallets`/`credit_wallet_buckets`/`credit_ledger_entries` 一致性测试。
- [ ] 增加 billing 常量静态校验，确保不与 `user/promo/profile/shifu/metering` 常量撞码，并且 `usage_type/usage_scene` 直接复用 metering。
- [ ] 增加 `CELERY_TASK_ALWAYS_EAGER=1` 下的任务集成测试与调度回归测试。
- [ ] 增加旧 `/order` 学员购课流程回归测试。
- [ ] 编写 rollout、migration、backfill、监控告警和回滚 runbook。

## v1.1 扩展交付

### 权益与域名

- [ ] 新增 `billing_entitlements` 和 `billing_domain_bindings`。
- [ ] 实现创作者维度的权益快照和运行时解析逻辑。
- [ ] 实现 `max_concurrency`、priority class 和 runtime admission enforcement。
- [ ] 实现自定义域名绑定、校验、停用和 host 解析逻辑。
- [ ] 扩展 runtime config，返回 entitlement、branding 和 domain 结果。

### 报表与聚合

- [ ] 新增 `billing_daily_usage_metrics` 与 `billing_daily_ledger_summary`。
- [ ] 实现 usage 日汇总增量任务和 finalize 任务。
- [ ] 实现 ledger 日汇总增量任务和 finalize 任务。
- [ ] 实现按 creator/shifu/date window 的 rebuild 任务与 CLI 入口。
- [ ] 为 daily aggregate、rebuild、domain verify 注册 v1.1 Celery tasks。

### 前端与管理端扩展

- [ ] 在 `/admin/billing` 增加 `Entitlements`、`Domains`、`Reports` 三个扩展 tab。
- [ ] 实现品牌配置与域名设置页面。
- [ ] 实现分析等级、支持等级、优先级和并发能力的展示。
- [ ] 实现 usage 日汇总和 ledger 日汇总报表视图。
- [ ] 实现 admin 侧域名审核、权益查看和报表页面。

### 测试与上线扩展

- [ ] 增加权益快照、自定义域名和 host 解析测试。
- [ ] 增加日报表、rebuild 和报表对账测试。
- [ ] 增加 v1 升级到 v1.1 的迁移和回填验证。

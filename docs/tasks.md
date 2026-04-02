# Billing 交付任务

## 已完成调研与文档整理

- [x] 审查现有课程订单与支付流程。
- [x] 审查现有 metering 与 runtime config 流程。
- [x] 确认计费主体、产品范围、续费模式、权益范围和文档存放路径。
- [x] 将商品目录统一为 `billing_products` 单表，并保留 `plans[]` / `topups[]` API 投影。
- [x] 将支付持久化模型统一为 `billing_orders` + `billing_provider_events`。
- [x] 统一扣分场景为 `production`、`preview`、`debug`，并明确由课程所属创作者承担。
- [x] 统一 LLM `input/cache/output` 与 TTS `按次/按字数` 的扣分口径。
- [x] 将库表分层为 `v1 核心表` 与 `v1.1 扩展表`。
- [x] 将设计文档重写为表格化字段定义，并统一字段编码规范。
- [x] 将现有代码改造边界补充进设计文档。
- [x] 将 Celery 作为 v1 基础设施接入方案补充进设计文档。

## v1 核心交付

### 产品与费率

- [ ] 冻结套餐、充值包、试用积分和赠送积分的最终业务规则。
- [ ] 冻结升级、降级、取消、恢复、宽限期和退款规则。
- [ ] 冻结 `production`、`preview`、`debug` 三个 scene 的 provider/model/metric 费率矩阵。
- [ ] 冻结低余额阈值、告警触发条件和 billing 错误码文案。

### 现有代码改造

- [ ] 明确并落地 `service/order/payment_providers` 在 billing 域的复用边界，不复用旧 `order_*` 表。
- [ ] 扩展 `payment_providers/base.py` 支持 billing recurring/subscription/webhook 统一接口。
- [ ] 调整 metering 的 `debug/preview` billable 逻辑，移除常量层硬编码 non-billable 判定。
- [ ] 在 learn/preview/debug 入口接入 creator admission service。
- [ ] 增加 `shifu_bid -> creator_bid` 的 ownership resolver 供 settlement 使用。
- [ ] 明确并保留不改的旧链路：`/order` API、旧 order admin、raw `bill_usage` 结构、全局 `/api/config`。

### Schema 与迁移

- [ ] 新增 `billing_products`、`billing_subscriptions`、`billing_orders`、`billing_provider_events`。
- [ ] 新增 `billing_wallets`、`billing_ledger_entries`、`billing_usage_rates`、`billing_renewal_events`。
- [ ] 为核心表补齐索引、唯一约束和基础 seed 数据。
- [ ] 在 `sys_configs` 中增加 billing feature flag、低余额阈值、续费任务配置和 rate version 配置。

### 支付与订阅

- [ ] 实现统一的 billing payment orchestration，并在 adapter 层封装 Stripe/Pingxx 差异。
- [ ] 实现 subscription checkout、cancel、resume 和退款流程。
- [ ] 实现 topup checkout 与到账流程。
- [ ] 实现 `billing_provider_events` 去重、重放和原始事件审计。
- [ ] 实现订阅生命周期推进，包括开通、升级、续费、宽限期、取消和降级排期。
- [ ] 确认国内支付通道 recurring capability，并对不支持能力返回 `unsupported`。

### 计量与结算

- [ ] 实现 `bill_usage -> billing_ledger_entries` 的多维度结算逻辑。
- [ ] 实现 LLM `input/cache/output` 三维扣分。
- [ ] 实现 TTS `按次` 与 `按字数` 两种计费模式。
- [ ] 实现 `production`、`preview`、`debug` 三场景的 creator 归属解析。
- [ ] 实现账本不可变写入和钱包乐观锁更新。
- [ ] 实现余额不足、订阅失效的前置拦截。
- [ ] 实现结算幂等 key 和 replay 安全，避免重复扣分。

### Celery 与基础设施

- [ ] 引入 Redis broker 与 Celery worker/beat 进程配置。
- [ ] 新增 Celery app factory，并让 worker 复用 Flask `create_app()` 配置。
- [ ] 在 `requirements.txt`、配置定义和环境变量示例中接入 Celery/Redis 配置。
- [ ] 在 `docker-compose.yml`、`docker-compose.latest.yml`、`docker-compose.dev.yml` 中增加 `redis`、`celery-worker`、`celery-beat`。
- [ ] 为 renewal、retry、reconcile、settlement replay、low balance alert 注册 Celery tasks。
- [ ] 实现 `billing_renewal_events` 的入队、抢占和幂等执行。
- [ ] 实现 webhook 补偿同步和失败续费重试。
- [ ] 保留 Flask CLI 作为 backfill / rebuild / manual replay 入口，并与 Celery 任务分工清晰。

### 前端与管理端

- [ ] 实现 creator Billing Center 的基础页面。
- [ ] 实现套餐/充值包目录、购买流程、订阅卡片和钱包余额展示。
- [ ] 实现账本、订单、取消订阅和恢复订阅交互。
- [ ] 实现 admin 侧订阅、订单、账本调整和异常处理页面。

### 测试与上线

- [ ] 增加支付、订阅生命周期、webhook 幂等和退款测试。
- [ ] 增加结算、余额计算、积分消耗顺序和三场景扣分测试。
- [ ] 增加 `CELERY_TASK_ALWAYS_EAGER=1` 下的任务集成测试与调度回归测试。
- [ ] 增加旧 `/order` 学员购课流程回归测试。
- [ ] 编写 rollout、migration、backfill、监控告警和回滚 runbook。

## v1.1 扩展交付

### 权益与域名

- [ ] 新增 `billing_entitlements` 和 `billing_domain_bindings`。
- [ ] 实现创作者维度的权益快照和运行时解析逻辑。
- [ ] 实现自定义域名绑定、校验、停用和 host 解析逻辑。
- [ ] 扩展 runtime config，返回 entitlement、branding 和 domain 结果。

### 报表与聚合

- [ ] 新增 `billing_daily_usage_metrics` 与 `billing_daily_ledger_summary`。
- [ ] 实现 usage 日汇总增量任务和 finalize 任务。
- [ ] 实现 ledger 日汇总增量任务和 finalize 任务。
- [ ] 实现按 creator/shifu/date window 的 rebuild 任务与 CLI 入口。
- [ ] 为 daily aggregate、rebuild、domain verify 注册 v1.1 Celery tasks。

### 前端与管理端扩展

- [ ] 实现品牌配置与域名设置页面。
- [ ] 实现分析等级、支持等级、优先级和并发能力的展示。
- [ ] 实现 admin 侧域名审核、权益查看和报表页面。

### 测试与上线扩展

- [ ] 增加权益快照、自定义域名和 host 解析测试。
- [ ] 增加日报表、rebuild 和报表对账测试。
- [ ] 增加 v1 升级到 v1.1 的迁移和回填验证。

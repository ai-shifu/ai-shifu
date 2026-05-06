# Billing 设计文档

更新日期：2026-04-08

## 1. 文档目标

### 1.1 v1 核心计费目标

v1 只解决最小可上线的 creator billing 闭环：

- 创作者购买套餐和充值包
- 套餐自动续费
- 学员 `production`、作者 `preview`、作者 `debug` 三类场景统一扣创作者积分
- LLM 按 `input/cache/output` 三维扣分
- TTS 同时支持 `按次` 和 `按字数` 两种费率模型
- 支付、订阅、钱包、余额桶、账本、费率、续费排期形成完整真相源

### 1.2 v1.1 扩展目标

v1.1 再补充下列扩展能力：

- 创作者权益快照
- 自定义域名绑定
- 按天 usage/ledger 报表聚合
- 基于权益的 branding、domain、analytics、priority、concurrency 扩展输出

### 1.3 本文冻结的关键决策

- 计费主体固定为 `creator_bid`
- 课程学习、预览、调试的 LLM/TTS 消耗都由课程所属创作者承担
- 商品目录统一使用 `bill_products` 单表，API 仍按 `plans[]` / `topups[]` 投影
- 支付持久化统一以 `bill_orders` 为业务真相源；provider 最新摘要保留在 `bill_orders.metadata`，provider raw snapshot 复用 `order_pingxx_orders` / `order_stripe_orders`，native 国内直连 provider 写入 `order_native_payment_orders`，并通过 `biz_domain`、`bill_order_bid`、`creator_bid` 隔离
- 钱包/余额桶/账本三层分离：`credit_wallets` 只做总余额快照，`credit_wallet_buckets` 负责按来源管理可消费余额桶，`credit_ledger_entries` 才是不可变真相源
- `bill_usage + credit_ledger_entries` 是结算真相源；日报表只是报表层聚合，不参与扣费真相判断
- 积分消费顺序固定为 `free > subscription > topup`；同优先级下按 `effective_to` 最早优先，再按 `created_at` 最早优先
- 旧的学员购课 `/order` 流程继续保留，不与 creator billing 混表

### 1.4 当前实现批次范围（2026-04-08）

本文描述的是完整 billing v1 / v1.1 设计；但当前实施批次只落地 “Figma `方案1` 浅色稿 + creator billing 可联调 MVP”，范围固定如下：

- 前端以 Figma `方案1` 浅色稿为唯一视觉准绳，保留现有 `/admin` 作为创作中心首页，只补侧边栏会员卡、`会员与积分` 导航和新的 `/admin/billing`
- 新增 `/payment/stripe/billing-result`，专门承接 creator billing 的 Stripe 回跳与 sync
- 后端新增 `service/billing` 模块、独立 `/api/billing` 路由、核心表和只读查询接口；业务状态不复用旧 `order_orders`，provider raw snapshot 复用旧 `order_pingxx_orders` / `order_stripe_orders`
- Stripe 在本批次支持套餐 checkout 与 topup checkout；Pingxx 支持 topup checkout，以及由平台自管的 subscription start / renewal 补单链路；native Alipay / WeChat Pay 首版只提供一次性 checkout 与 sync/webhook paid grant，不依赖 provider-managed recurring
- 支付成功后必须真实写入 `bill_orders`、`bill_subscriptions`、`credit_wallets`、`credit_wallet_buckets`、`credit_ledger_entries`，保证前端可以直接联调真实余额和订单状态
- 本批次不以 `bill_usage -> credit_ledger_entries` 结算、Celery 串行 settlement、自动续费排期、失败续费重试、bucket 过期扫描、admin adjust、entitlements/domains/reports 为阻塞项
- 以上暂缓能力仍属于完整 v1 / v1.1 目标，继续保留在本文后续章节和任务清单中

### 1.5 能力状态矩阵（代码真相源）

以下矩阵以 `src/api/flaskr/service/billing/capabilities.py` 为唯一真相源。文档描述必须跟随代码状态，不再混用“已实现”“暂缓”“未来支持”三套口径。

| capability | status | 入口 | 默认开关 | 用户可见 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `creator_catalog` | `active` | `GET /api/billing/catalog` | on | 是 | creator 可以查看当前可售套餐和充值包 |
| `creator_subscription_checkout` | `active` | `/api/billing/overview`、`/subscriptions/checkout`、`/subscriptions/cancel`、`/subscriptions/resume` | on | 是 | 套餐购买、取消、恢复和 overview 当前正式可达 |
| `creator_wallet_ledger` | `active` | `GET /api/billing/wallet-buckets`、`GET /api/billing/ledger` | on | 是 | 钱包桶和账本明细当前正式可达 |
| `creator_orders` | `active` | `POST /api/billing/topups/checkout`、`POST /api/billing/orders/*/sync`、`POST /api/billing/orders/*/checkout`、`POST /api/billing/orders/*/refund` | on | 是 | creator topup、补单 checkout、sync、refund 当前正式可达 |
| `admin_subscriptions` | `active` | `GET /api/admin/billing/subscriptions` | on | 是 | admin 订阅审查当前正式可达 |
| `admin_orders` | `active` | `GET /api/admin/billing/orders` | on | 是 | admin 订单审查当前正式可达 |
| `admin_ledger_adjust` | `active` | `POST /api/admin/billing/ledger/adjust` | on | 是 | admin 手工账本调整当前正式可达 |
| `admin_entitlements` | `active` | `GET /api/admin/billing/entitlements` | on | 是 | admin 权益查看当前正式可达 |
| `admin_domains` | `active` | `GET /api/admin/billing/domain-audits` | on | 是 | admin 域名审核当前正式可达 |
| `admin_reports` | `active` | `GET /api/admin/billing/reports/*` | on | 是 | admin usage/ledger 报表当前正式可达 |
| `runtime_billing_extensions` | `active` | `GET /api/config/runtime-config` | on | 否 | runtime config 已返回 billing entitlement/domain 扩展 |
| `billing_feature_flag` | `default_disabled` | `BILL_ENABLED` | off | 否 | feature flag seed 默认关闭，代码能力存在 |
| `renewal_task_queue` | `default_disabled` | `BILL_RENEWAL_TASK_CONFIG.enabled` | off | 否 | renewal worker 默认配置关闭 |
| `usage_settlement` | `internal_only` | task/CLI | on | 否 | usage settlement 只供内部任务和补偿使用 |
| `renewal_compensation` | `internal_only` | task/CLI | on | 否 | renewal/retry 补偿链路只供内部执行 |
| `provider_reconcile` | `internal_only` | task/CLI | on | 否 | provider reconcile 只作为内部修复面保留 |
| `wallet_bucket_expiration` | `internal_only` | task | on | 否 | bucket 过期扫描和 expire ledger 内部执行 |
| `low_balance_alerts` | `internal_only` | task | on | 否 | 低余额告警生成属于后台任务 |
| `daily_aggregate_rebuild` | `internal_only` | task/CLI | on | 否 | 日报表聚合重建和 finalize 属于内部修复能力 |
| `domain_verify_refresh` | `internal_only` | task | on | 否 | 域名验证刷新属于后台任务 |

## 2. 字段类型与编码约定

### 2.1 公共基础字段

除非特别说明，以下字段适用于所有 billing 表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | `primary_key=True, autoincrement=True` | 自增主键 | `Primary key` | 物理主键 |
| `deleted` | `SmallInteger` | `not null, default=0, index=True` | `0=active; 1=deleted` | `Deletion flag` | 软删标记 |
| `created_at` | `DateTime` | `not null, default=func.now()` | 创建时写入 | `Creation timestamp` | 创建时间 |
| `updated_at` | `DateTime` | `not null, default=func.now(), onupdate=func.now()` | 更新时刷新 | `Last update timestamp` | 更新时间 |

如果某张表会被后台管理端直接维护，可按仓库现有 Cook 规范额外补充：

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `created_user_bid` | `String(36)` | `not null, default="", index=True` | 管理端写入人 | `Creator user business identifier` | 创建人业务 ID |
| `updated_user_bid` | `String(36)` | `not null, default="", index=True` | 管理端更新人 | `Last updater user business identifier` | 更新人业务 ID |

### 2.2 通用编码

#### 2.2.1 编码来源规则

- `usage_type` 与 `usage_scene` 直接复用 `src/api/flaskr/service/metering/consts.py` 中的现有常量，billing 域不重新分配数字
- billing 专属状态、类型、metric、rounding mode 统一放到 `7100-7799` 段位
- `service/billing/consts.py` 应作为 billing 专属编码的唯一来源，其他模块只引用，不复制数字

#### 2.2.2 `usage_type`

| 编码 | 含义 |
| --- | --- |
| `1101` | `LLM` |
| `1102` | `TTS` |

#### 2.2.3 `usage_scene`

| 编码 | 含义 |
| --- | --- |
| `1201` | `debug` |
| `1202` | `preview` |
| `1203` | `production` |

#### 2.2.4 `billing_metric`

| 编码 | 含义 |
| --- | --- |
| `7451` | `llm_input_tokens` |
| `7452` | `llm_cache_tokens` |
| `7453` | `llm_output_tokens` |
| `7454` | `tts_request_count` |
| `7455` | `tts_output_chars` |
| `7456` | `tts_input_chars`，保留给后续特殊 provider 合同 |

#### 2.2.5 `credit_bucket_category`

| 编码 | 含义 |
| --- | --- |
| `7431` | `free` |
| `7432` | `subscription` |
| `7433` | `topup` |

#### 2.2.6 `credit_bucket_status`

| 编码 | 含义 |
| --- | --- |
| `7441` | `active` |
| `7442` | `exhausted` |
| `7443` | `expired` |
| `7444` | `canceled` |

#### 2.2.7 `credit_usage_rate_status`

| 编码 | 含义 |
| --- | --- |
| `7151` | `active` |
| `7152` | `inactive` |

#### 2.2.8 `billing_renewal_event_type`

| 编码 | 含义 |
| --- | --- |
| `7501` | `renewal` |
| `7502` | `retry` |
| `7503` | `cancel_effective` |
| `7504` | `downgrade_effective` |
| `7505` | `expire` |
| `7506` | `reconcile` |

#### 2.2.9 `billing_renewal_event_status`

| 编码 | 含义 |
| --- | --- |
| `7511` | `pending` |
| `7512` | `processing` |
| `7513` | `succeeded` |
| `7514` | `failed` |
| `7515` | `canceled` |

#### 2.2.10 类型与存储约定

- 所有业务 ID 统一使用 `String(36)`，命名为 `*_bid`
- 所有状态、类型、场景、metric 字段统一使用 `SmallInteger` 编码，不在库里直接存英文状态串
- 金额统一使用 `BIGINT` 保存最小货币单位，例如分
- 所有积分相关字段统一使用 `Numeric(20,10)` / `DECIMAL(20,10)`
- provider、model、reference id 等短文本按现有仓库风格使用 `String(32/64/100/255)`
- 扩展载荷优先 `JSON`，仅在 provider 原始对象体积或兼容性要求下退回 `Text`

## 3. v1 核心表

### 3.1 `bill_products`

角色：目录真相源；不是账务真相源；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `product_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Billing product business identifier` | 商品业务 ID |
| `product_code` | `String(64)` | `not null, default="", unique=True` | 稳定编码，用于配置和对外联调 | `Billing product code` | 商品稳定编码 |
| `product_type` | `SmallInteger` | `not null, index=True` | `7111=plan; 7112=topup; 7113=grant; 7114=custom` | `Billing product type code` | 商品类型编码 |
| `billing_mode` | `SmallInteger` | `not null` | `7121=recurring; 7122=one_time; 7123=manual` | `Billing mode code` | 计费模式编码 |
| `billing_interval` | `SmallInteger` | `not null, default=0` | `7131=none; 7132=month; 7133=year; 7134=day` | `Billing interval code` | 套餐周期编码 |
| `billing_interval_count` | `Integer` | `not null, default=0` | 周期倍数，月套餐常见为 `1` | `Billing interval count` | 周期倍数 |
| `display_name_i18n_key` | `String(128)` | `not null, default=""` | i18n key | `Display name i18n key` | 展示名称翻译 key |
| `description_i18n_key` | `String(128)` | `not null, default=""` | i18n key | `Description i18n key` | 描述翻译 key |
| `currency` | `String(16)` | `not null, default="CNY"` | ISO 4217，例如 `CNY`/`USD` | `Currency code` | 货币编码 |
| `price_amount` | `BIGINT` | `not null, default=0` | 最小货币单位 | `Product price amount` | 商品价格 |
| `credit_amount` | `Numeric(20,10)` | `not null, default=0` | 发放积分数量 | `Credit amount` | 商品附带积分数 |
| `allocation_interval` | `SmallInteger` | `not null, default=7141` | `7141=per_cycle; 7142=one_time; 7143=manual` | `Credit allocation interval code` | 积分发放节奏 |
| `auto_renew_enabled` | `SmallInteger` | `not null, default=0` | `0=no; 1=yes` | `Auto renew enabled flag` | 是否允许自动续费 |
| `entitlement_payload` | `JSON` | `nullable=True` | v1 可留空，v1.1 用于权益扩展 | `Entitlement payload` | 权益扩展载荷 |
| `metadata` | `JSON` | `nullable=True` | 自定义展示、运营标记等 | `Billing product metadata` | 商品扩展元数据 |
| `status` | `SmallInteger` | `not null, default=7151, index=True` | `7151=active; 7152=inactive` | `Billing product status code` | 商品状态 |
| `sort_order` | `Integer` | `not null, default=0` | 列表排序，越小越靠前 | `Sort order` | 排序值 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 唯一索引：`product_bid`、`product_code`
- 关键索引：`product_bid`、`product_type + status`

与其他表关系：

- `bill_subscriptions.product_bid`
- `bill_subscriptions.next_product_bid`
- `bill_orders.product_bid`

本表职责与边界：

- 统一承载套餐、充值包、赠送包、定制包目录
- `product_type=plan` 才允许进入订阅流程
- `product_type=topup` 必须是一次性支付，不创建 subscription

v1 冻结业务规则：

- 面向 creator 的公开自助目录继续由 `bill_products` 驱动，但 API 仍只把付费 plan/topup 投影到 `GET /billing/catalog` 的 `plans[]` / `topups[]`
- `creator-plan-trial` 是一个正式 `bill_products` 记录：`product_type=plan`、`billing_mode=manual`、`price_amount=0`、`credit_amount=100`、`auto_renew_enabled=0`
- public trial product 不进入 creator 自助 checkout；它只用于 `GET /billing/overview` 的免费试用卡片，以及 post-auth 自动开通
- `gift` 积分不作为 creator 自助购买商品；赠送积分和后台正向补偿仍走运营或人工 grant 流程
- `product_type=grant` 与 `product_type=custom` 仅保留给运营投放、后台人工赠送和未来定制方案，不纳入当前 creator 自助购买入口

### 3.2 `bill_subscriptions`

角色：订阅真相源；不是账本真相源；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `subscription_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Billing subscription business identifier` | 订阅业务 ID |
| `creator_bid` | `String(36)` | `not null, default="", index=True` | 订阅所属创作者 | `Creator business identifier` | 创作者业务 ID |
| `product_bid` | `String(36)` | `not null, default="", index=True` | 必须引用 `product_type=plan` | `Current billing product business identifier` | 当前套餐商品 ID |
| `status` | `SmallInteger` | `not null, default=7201, index=True` | `7201=draft; 7202=active; 7203=past_due; 7204=paused; 7205=cancel_scheduled; 7206=canceled; 7207=expired` | `Billing subscription status code` | 订阅状态 |
| `billing_provider` | `String(32)` | `not null, default="", index=True` | `stripe` / `pingxx` | `Billing provider name` | 支付 provider |
| `provider_subscription_id` | `String(255)` | `not null, default=""` | provider 订阅 ID | `Provider subscription identifier` | provider 订阅号 |
| `provider_customer_id` | `String(255)` | `not null, default=""` | provider 客户 ID | `Provider customer identifier` | provider 客户号 |
| `billing_anchor_at` | `DateTime` | `nullable=True` | 账期锚点 | `Billing anchor timestamp` | 账期锚点时间 |
| `current_period_start_at` | `DateTime` | `nullable=True` | 当前周期开始 | `Current period start timestamp` | 当前周期开始时间 |
| `current_period_end_at` | `DateTime` | `nullable=True` | 当前周期结束 | `Current period end timestamp` | 当前周期结束时间 |
| `grace_period_end_at` | `DateTime` | `nullable=True` | 宽限期结束 | `Grace period end timestamp` | 宽限期结束时间 |
| `cancel_at_period_end` | `SmallInteger` | `not null, default=0` | `0=no; 1=yes` | `Cancel at period end flag` | 是否周期结束后取消 |
| `next_product_bid` | `String(36)` | `not null, default="", index=True` | 仅用于降级或续费切换目标套餐 | `Next billing product business identifier` | 下周期套餐 ID |
| `last_renewed_at` | `DateTime` | `nullable=True` | 最近一次续费成功时间 | `Last renewed timestamp` | 最近续费成功时间 |
| `last_failed_at` | `DateTime` | `nullable=True` | 最近一次续费失败时间 | `Last failed timestamp` | 最近失败时间 |
| `metadata` | `JSON` | `nullable=True` | provider 辅助字段、迁移兼容标记；不作为 webhook 原始载荷默认存档位置 | `Billing subscription metadata` | 订阅扩展元数据 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 唯一索引：`subscription_bid`
- 建议唯一索引：`creator_bid + status in active-like set` 由业务约束保证同一创作者仅一个活跃主订阅
- 关键索引：`subscription_bid`、`creator_bid + status`

与其他表关系：

- 引用 `bill_products.product_bid`
- 被 `bill_orders.subscription_bid`、`bill_renewal_events.subscription_bid` 关联

本表职责与边界：

- 只表示套餐订阅合同，不表示一次性充值
- `cancel_scheduled` 表示当前周期仍有效，但未来不再自动续费
- `next_product_bid` 只用于未来生效的套餐切换，不立即替换 `product_bid`
- provider 订阅事件可直接推进 `status`、`current_period_*`、`last_failed_at` 等字段
- `past_due` 时必须回填 `grace_period_end_at`，并把续费排期切换为 retry
- `bill_renewal_events` 需要跟随订阅状态维护 `renewal/retry/cancel_effective/downgrade_effective`
- v1 不新增独立的 subscription webhook 存储层

v1 冻结 subscription lifecycle 规则：

- 当前 creator 自助 API 只开放 `subscription_start` checkout、`cancel` 和 `resume`；升级、降级仍按领域状态机冻结，但不在本批次新增独立 self-serve 路由
- `subscription_start` 支付成功后立即生效：创建或激活订阅、写入当前 `product_bid`、打开新的 `current_period_start_at/current_period_end_at` 周期窗口，并按当前套餐发放 `subscription` bucket
- `subscription_upgrade` 的领域规则固定为“支付成功后立即升级，不做 prorate credit 结转”：`product_bid` 立即切到新套餐、`next_product_bid` 清空、当前周期窗口按新订单生效时间重置，并重新排下一次 `renewal`
- `downgrade` 的领域规则固定为“下周期生效，不立即降级”：当前周期只记录 `next_product_bid`，并在 `current_period_end_at` 创建 `downgrade_effective` 事件；只有下一笔 `subscription_renewal` paid apply 成功后，才把 `next_product_bid` 真正切到 `product_bid`
- `cancel` 规则固定为“周期末取消”：API cancel 只把 `cancel_at_period_end=1` 且 `status=cancel_scheduled`，当前已发放积分和当前周期有效期继续保留到 `current_period_end_at`；不会立即关停当前周期
- `resume` 只允许从 `cancel_scheduled` 或 provider 标记的 `paused` 状态恢复；恢复时必须清空 `cancel_at_period_end`，把订阅回到 `active`，并重新启用后续 `renewal`
- provider 把订阅推进到 `past_due` 后，v1 一律进入宽限期模式：`grace_period_end_at` 默认等于当前 `current_period_end_at`，原 `renewal/cancel_effective/downgrade_effective` 事件让位给 `retry`，直到续费成功或订阅被取消/过期
- `paused` 属于 provider 驱动状态，当前批次不提供主动 pause API；若 provider 事件把订阅置为 `paused`，creator 只能通过已有 `resume` 接口恢复
- 退款规则固定为：`POST /billing/orders/{bill_order_bid}/refund` 当前只支持 Stripe 已支付订单，Pingxx 必须返回 `unsupported`；若退款订单绑定了订阅，则关联订阅立即进入 `canceled` 并取消后续 renewal event，不再保留 `cancel_scheduled` 或宽限期
- refund 造成的积分返还不恢复原 subscription/topup bucket；如需返还 credit，一律按上一节的 `refund return -> free bucket` 规则执行

### 3.3 `bill_orders`

角色：支付动作真相源，同时承载 webhook / sync 驱动的状态推进；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `bill_order_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Billing order business identifier` | 支付动作单业务 ID |
| `creator_bid` | `String(36)` | `not null, default="", index=True` | 所属创作者 | `Creator business identifier` | 创作者业务 ID |
| `order_type` | `SmallInteger` | `not null, index=True` | `7301=subscription_start; 7302=subscription_upgrade; 7303=subscription_renewal; 7304=topup; 7305=manual; 7306=refund` | `Billing order type code` | 支付动作类型 |
| `product_bid` | `String(36)` | `not null, default="", index=True` | 对应商品 ID | `Billing product business identifier` | 商品业务 ID |
| `subscription_bid` | `String(36)` | `not null, default="", index=True` | 套餐场景必填；topup 可留空字符串 | `Billing subscription business identifier` | 关联订阅 ID |
| `currency` | `String(16)` | `not null, default="CNY"` | ISO 4217 | `Currency code` | 货币编码 |
| `payable_amount` | `BIGINT` | `not null, default=0` | 应付金额，最小货币单位 | `Payable amount` | 应付金额 |
| `paid_amount` | `BIGINT` | `not null, default=0` | 实付金额，最小货币单位 | `Paid amount` | 实付金额 |
| `payment_provider` | `String(32)` | `not null, default="", index=True` | `stripe` / `pingxx` | `Payment provider name` | 支付 provider |
| `channel` | `String(64)` | `not null, default=""` | provider 内部支付渠道 | `Payment channel` | 支付渠道 |
| `provider_reference_id` | `String(255)` | `not null, default="", index=True` | 通用 provider 引用，如 checkout/session/charge/invoice | `Provider reference identifier` | provider 参考 ID |
| `status` | `SmallInteger` | `not null, default=7311, index=True` | `7311=init; 7312=pending; 7313=paid; 7314=failed; 7315=refunded; 7316=canceled; 7317=timeout` | `Billing order status code` | 支付状态 |
| `paid_at` | `DateTime` | `nullable=True` | 支付成功时间 | `Paid timestamp` | 支付成功时间 |
| `failed_at` | `DateTime` | `nullable=True` | 支付失败时间 | `Failed timestamp` | 支付失败时间 |
| `refunded_at` | `DateTime` | `nullable=True` | 退款完成时间 | `Refunded timestamp` | 退款时间 |
| `failure_code` | `String(255)` | `not null, default=""` | provider 错误码 | `Failure code` | 失败码 |
| `failure_message` | `String(255)` | `not null, default=""` | provider 错误信息 | `Failure message` | 失败信息 |
| `metadata` | `JSON` | `nullable=True` | 最近一次 webhook/sync 摘要、event type、event time、return url、补偿标记；provider raw object 另镜像写入 `order_pingxx_orders` / `order_stripe_orders` | `Billing order metadata` | 支付动作扩展元数据 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 唯一索引：`bill_order_bid`
- 关键索引：`bill_order_bid`、`creator_bid + status`、`provider_reference_id`

与其他表关系：

- 关联 `bill_products.product_bid`
- 关联 `bill_subscriptions.subscription_bid`
- 被 `credit_ledger_entries.source_bid` 使用

本表职责与边界：

- 一次 checkout、一笔续费、一笔 topup、一笔退款，各自对应一条 `bill_orders`
- v1 不引入 `payment_attempts` 子表；支付重试通过创建新的 `bill_orders` 完成
- `bill_orders` 通过 `provider_reference_id`、当前状态和单向状态推进规则承担 webhook 幂等
- 订单级 webhook 直接推进 `bill_orders` 状态，并覆盖写入最近一次 provider payload 到 `metadata`
- 订阅级 provider 事件优先回填同 `subscription_bid` 最近一笔 `bill_orders.metadata`，并更新关联 provider raw snapshot；如找不到关联订单，则只推进状态或忽略，不额外补 raw snapshot
- 找不到关联订单的孤儿 webhook 直接忽略，后续依赖 `POST /billing/orders/{bill_order_bid}/sync` 或 reconcile 补偿

### 3.4 `credit_wallets`

角色：余额快照；不是扣费真相源；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `wallet_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Credit wallet business identifier` | 钱包业务 ID |
| `creator_bid` | `String(36)` | `not null, default="", unique=True` | 一创作者一钱包 | `Creator business identifier` | 创作者业务 ID |
| `available_credits` | `Numeric(20,10)` | `not null, default=0` | 当前可用积分 | `Available credits` | 可用积分 |
| `reserved_credits` | `Numeric(20,10)` | `not null, default=0` | hold 后冻结积分 | `Reserved credits` | 冻结积分 |
| `lifetime_granted_credits` | `Numeric(20,10)` | `not null, default=0` | 累计发放积分 | `Lifetime granted credits` | 累计发放积分 |
| `lifetime_consumed_credits` | `Numeric(20,10)` | `not null, default=0` | 累计消耗积分 | `Lifetime consumed credits` | 累计消耗积分 |
| `last_settled_usage_id` | `BIGINT` | `not null, default=0, index=True` | 最近结算到的 `bill_usage.id` | `Last settled usage record id` | 最近已结算 usage 主键 |
| `version` | `Integer` | `not null, default=0` | 乐观锁版本号 | `Wallet version` | 钱包版本号 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 唯一索引：`wallet_bid`、`creator_bid`
- 关键索引：`wallet_bid`、`last_settled_usage_id`

与其他表关系：

- 被 `credit_wallet_buckets.wallet_bid` 关联
- 被 `credit_ledger_entries.wallet_bid` 关联

本表职责与边界：

- 仅做余额快照和快速读模型
- `available_credits` = 所有可消费 bucket 的 `available_credits` 汇总
- `reserved_credits` = 所有 bucket 的 `reserved_credits` 汇总
- `lifetime_granted_credits` 与 `lifetime_consumed_credits` 仍按账本聚合，不从 bucket 快照反推历史
- 钱包数值必须由账本结果推导和更新，禁止直接手改余额

### 3.5 `credit_wallet_buckets`

角色：按来源管理的可消费余额桶快照；不是扣费真相源；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `wallet_bucket_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Credit wallet bucket business identifier` | 钱包余额桶业务 ID |
| `wallet_bid` | `String(36)` | `not null, default="", index=True` | 所属钱包 | `Credit wallet business identifier` | 钱包业务 ID |
| `creator_bid` | `String(36)` | `not null, default="", index=True` | 所属创作者 | `Creator business identifier` | 创作者业务 ID |
| `bucket_category` | `SmallInteger` | `not null, index=True` | `7431=legacy_free; 7432=subscription; 7433=topup` | `Credit bucket category code` | 余额桶分类；creator 运行时只暴露 `subscription/topup` 两类，`7431` 仅保留给历史数据兼容 |
| `source_type` | `SmallInteger` | `not null, index=True` | `7411=subscription; 7412=topup; 7413=gift; 7415=refund; 7416=manual` | `Billing ledger source type code` | 余额桶来源类型 |
| `source_bid` | `String(36)` | `not null, default="", index=True` | 对应发放业务单号，如 order/subscription/refund | `Credit bucket source business identifier` | 来源业务 ID |
| `priority` | `SmallInteger` | `not null, index=True` | 运行时扣减顺序固定为 `20=subscription; 30=topup` | `Credit bucket priority` | 扣减优先级 |
| `original_credits` | `Numeric(20,10)` | `not null, default=0` | 初始发放积分 | `Original credits` | 初始积分 |
| `available_credits` | `Numeric(20,10)` | `not null, default=0` | 当前可消费积分 | `Available credits` | 当前可用积分 |
| `reserved_credits` | `Numeric(20,10)` | `not null, default=0` | 当前冻结积分 | `Reserved credits` | 当前冻结积分 |
| `consumed_credits` | `Numeric(20,10)` | `not null, default=0` | 累计已消费积分 | `Consumed credits` | 已消费积分 |
| `expired_credits` | `Numeric(20,10)` | `not null, default=0` | 累计已过期积分 | `Expired credits` | 已过期积分 |
| `effective_from` | `DateTime` | `not null, index=True` | 生效开始时间 | `Effective from timestamp` | 生效开始时间 |
| `effective_to` | `DateTime` | `nullable=True, index=True` | 生效结束时间；`null` 表示永不过期 | `Effective to timestamp` | 生效结束时间 |
| `status` | `SmallInteger` | `not null, default=7441, index=True` | `7441=active; 7442=exhausted; 7443=expired; 7444=canceled` | `Credit bucket status code` | 余额桶状态 |
| `metadata` | `JSON` | `nullable=True` | 必须支持来源订单、订阅周期、refund return、manual remark 等上下文 | `Credit wallet bucket metadata` | 余额桶元数据 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 唯一索引：`wallet_bucket_bid`
- 关键索引：`wallet_bucket_bid`、`wallet_bid + status + priority + effective_to`、`creator_bid + status + priority + effective_to`、`source_type + source_bid`

与其他表关系：

- 关联 `credit_wallets.wallet_bid`
- 被 `credit_ledger_entries.wallet_bucket_bid` 关联

本表职责与边界：

- 一条发放动作创建一个 bucket，不把多个来源合并到同一 bucket
- bucket 只维护当前可消费余额和生命周期状态，不替代不可变账本
- 结算时按运行时 category priority、`effective_to asc nulls last`、`created_at asc` 选择可消费 bucket
- 一条 usage 扣费可以拆分消费多个 bucket，但默认只生成一条 `consume` ledger；bucket 级扣减明细回填到 `metadata.bucket_breakdown[]`
- creator 可消费 credits 运行时只保留 `subscription` 与 `topup` 两类；`gift` / `refund` / `manual` 继续只保留为审计 `source_type`
- 产品化 trial 作为正式 subscription grant，落成 `subscription` bucket；不存在单独的 “trial credits” 第三类
- bucket 到期后不再参与 admission / settlement，需写入 `expire` ledger 并关闭 bucket

v1 冻结 bucket 规则：

- bucket 运行时分类与优先级固定为：
  - `subscription` bucket：优先级 `20`，承载 subscription 周期发放积分，以及 legacy gift / refund return / manual credit 等归并后的可消费积分
  - `topup` bucket：优先级 `30`，承载一次性充值包积分，以及能明确解析为 topup 的退款返还或历史赠送；若 creator 当前存在有效套餐，则 topup bucket 的 `effective_to` 必须与当前套餐 `current_period_end_at` 对齐
- usage settlement 与 admission 只允许消费同时满足以下条件的 bucket：`status=active`、`available_credits > 0`、`effective_from <= settlement_at`，并且 `effective_to is null or effective_to > settlement_at`
- bucket 扣减顺序在 v1 固定为 `(runtime priority asc, effective_to asc nulls last, created_at asc, id asc)`；也就是始终先扣 `subscription`，再扣 `topup`，同优先级下先扣最早到期、最早创建的 bucket
- `effective_to = null` 明确表示永不过期，在同优先级排序中必须排在所有有具体过期时间的 bucket 之后
- `refund return` 不回写原 bucket，也不恢复原 bucket 的 `available_credits`；会新建 `source_type=refund` bucket，并按原订单类型映射到 `subscription/topup`，无法解析历史来源时默认归到 `subscription`
- 正向人工补偿统一创建 `subscription` bucket；负向人工扣减按 `subscription -> topup` 顺序执行
- legacy gift 默认归到 `subscription`；若历史元数据能明确解析出 topup 来源，则归到 `topup`
- 同一条 usage 允许拆分扣减多个 bucket；bucket 级命中顺序和金额必须保留在 `metadata.bucket_breakdown[]` 中，历史多行 usage consume ledger 仍视为合法存量数据

### 3.6 `credit_ledger_entries`

角色：积分账本真相源；不是快照；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `ledger_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Credit ledger business identifier` | 账本业务 ID |
| `creator_bid` | `String(36)` | `not null, default="", index=True` | 所属创作者 | `Creator business identifier` | 创作者业务 ID |
| `wallet_bid` | `String(36)` | `not null, default="", index=True` | 归属钱包 | `Credit wallet business identifier` | 钱包业务 ID |
| `wallet_bucket_bid` | `String(36)` | `not null, default="", index=True` | 归属余额桶；单 bucket 分录回填，多 bucket usage consume 可为空 | `Credit wallet bucket business identifier` | 余额桶业务 ID |
| `entry_type` | `SmallInteger` | `not null, index=True` | `7401=grant; 7402=consume; 7403=refund; 7404=expire; 7405=adjustment; 7406=hold; 7407=release` | `Billing ledger entry type code` | 账本分录类型 |
| `source_type` | `SmallInteger` | `not null, index=True` | `7411=subscription; 7412=topup; 7413=gift; 7414=usage; 7415=refund; 7416=manual` | `Billing ledger source type code` | 分录来源类型 |
| `source_bid` | `String(36)` | `not null, default="", index=True` | 对应业务单号，如 order/subscription/usage | `Ledger source business identifier` | 来源业务 ID |
| `idempotency_key` | `String(128)` | `not null, default="", index=True` | 统一幂等键；聚合 usage consume 以 usage 维度稳定去重 | `Ledger idempotency key` | 分录幂等键 |
| `amount` | `Numeric(20,10)` | `not null, default=0` | 正数增加可用余额，负数减少可用余额 | `Ledger amount` | 分录金额 |
| `balance_after` | `Numeric(20,10)` | `not null, default=0` | 写入后钱包总可用余额快照 | `Balance after entry` | 分录后钱包总余额 |
| `expires_at` | `DateTime` | `nullable=True, index=True` | 仅 grant 类分录会有到期时间 | `Entry expiration timestamp` | 积分到期时间 |
| `consumable_from` | `DateTime` | `nullable=True` | 仅需延迟可用时使用 | `Consumable from timestamp` | 开始可消费时间 |
| `metadata` | `JSON` | `nullable=True` | 必须支持 `usage_bid`、`usage_scene`、`provider`、`model`、`metric_breakdown[]`、`bucket_breakdown[]` | `Billing ledger metadata` | 分录元数据 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 唯一索引：`ledger_bid`
- 关键索引：`ledger_bid`、`wallet_bucket_bid`、`creator_bid + created_at`、`source_type + source_bid`
- 唯一约束：`creator_bid + idempotency_key`，由业务侧生成稳定幂等 key，避免重复入账

与其他表关系：

- 关联 `credit_wallets.wallet_bid`
- 关联 `credit_wallet_buckets.wallet_bucket_bid`
- `source_bid` 可对应 `bill_orders`、`bill_subscriptions` 或 `bill_usage.usage_bid`

本表职责与边界：

- 所有发放、扣减、退款、过期、人工调整都必须落账
- `grant`、`consume`、`refund`、`expire`、`adjustment` 至少要能回溯到受影响的 `wallet_bucket_bid`
- 同一个 `usage_bid + billing_metric` 允许拆成多条 `consume` 分录，每条对应一个 bucket
- usage 扣分分录的 `idempotency_key` 应为 `usage_bid + billing_metric + wallet_bucket_bid + entry_type`
- 非 usage 分录由业务侧生成稳定幂等键，如 `source_bid + wallet_bucket_bid + entry_type`
- `metadata.metric_breakdown[]` 用于保存 LLM 三维或 TTS metric 的细分扣分来源

### 3.7 `credit_usage_rates`

角色：费率真相源；不是账本；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `rate_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Credit usage rate business identifier` | 费率业务 ID |
| `usage_type` | `SmallInteger` | `not null, index=True` | `1101=LLM; 1102=TTS` | `Usage type code` | usage 类型 |
| `provider` | `String(32)` | `not null, default="", index=True` | provider 名称，可允许 `*` 作为 wildcard | `Provider name` | provider |
| `model` | `String(100)` | `not null, default="", index=True` | model 名称，可允许 `*` 作为 wildcard | `Provider model` | 模型名 |
| `usage_scene` | `SmallInteger` | `not null, index=True` | `1201=debug; 1202=preview; 1203=production` | `Usage scene code` | 场景编码 |
| `billing_metric` | `SmallInteger` | `not null, index=True` | `7451=llm_input_tokens; 7452=llm_cache_tokens; 7453=llm_output_tokens; 7454=tts_request_count; 7455=tts_output_chars; 7456=tts_input_chars` | `Billing metric code` | 计费 metric |
| `unit_size` | `Integer` | `not null, default=1` | 计费单位分母，如 `1000 tokens` | `Billing unit size` | 费率分母 |
| `credits_per_unit` | `Numeric(20,10)` | `not null, default=0` | 每个计费单位对应积分 | `Credits per unit` | 单位积分消耗 |
| `rounding_mode` | `SmallInteger` | `not null, default=7421` | `7421=ceil; 7422=floor; 7423=round` | `Rounding mode code` | 取整模式 |
| `effective_from` | `DateTime` | `not null, index=True` | 生效开始时间 | `Effective from timestamp` | 生效开始时间 |
| `effective_to` | `DateTime` | `nullable=True, index=True` | 生效结束时间 | `Effective to timestamp` | 生效结束时间 |
| `status` | `SmallInteger` | `not null, default=7151, index=True` | `7151=active; 7152=inactive` | `Credit usage rate status code` | 费率状态 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 唯一索引：`rate_bid`
- 唯一约束：`usage_type + provider + model + usage_scene + billing_metric + effective_from`
- 关键索引：`usage_type + provider + model + usage_scene + billing_metric + effective_from`

与其他表关系：

- 结算时与 `bill_usage` 联合匹配
- 结算结果写入 `credit_ledger_entries`

本表职责与边界：

- LLM 默认要求同一 provider/model/scene 至少配置三条 metric：`7451/7452/7453`
- TTS 默认只启用一种主 metric：`7454` 或 `7455`
- 如果找不到精确 model，可按 `model="*"` 或 `provider="*"` fallback
- 当前 bootstrap seed 使用 `provider="*"`、`model="*"` 的 wildcard 费率，并先以 `0.0000000000` 占位；待费率规则冻结后替换为正式值

v1 冻结 scene/provider/model/metric 矩阵：

- 三个计费 scene 固定全部进入 creator billing：`production(1203)`、`preview(1202)`、`debug(1201)` 都允许 admission 和 settlement，不再存在“debug 固定免计费”的常量例外
- LLM 费率矩阵固定为每个 scene 都需要 3 个独立 metric：
  - `7451=llm_input_tokens`
  - `7452=llm_cache_tokens`
  - `7453=llm_output_tokens`
- TTS 费率矩阵固定为每个 scene 只启用 1 个主扣费 metric，结算优先级固定为：
  - 先尝试 `7454=tts_request_count`
  - 若当前 scene/provider/model 没有激活的 `tts_request_count` 费率，再回退到 `7455=tts_output_chars`
  - 若仍未命中，再回退到 `7456=tts_input_chars`
  - 单条 TTS usage 最终只允许落 1 个主 metric，避免按次和按字数重复计费
- provider/model 的费率匹配优先级固定为：`provider=exact + model=exact` > `provider=exact + model=*` > `provider=* + model=exact` > `provider=* + model=*`
- 当前批次的 bootstrap seed 继续为每个 scene 预置 wildcard 默认行：
  - LLM：每个 scene 3 条 `*/*` 默认 rate
  - TTS：每个 scene 1 条 `tts_request_count` 的 `*/*` 默认 rate
- v1 允许按 provider/model 增加精确覆盖费率，但不新增 scene 级特殊结算逻辑；`production`、`preview`、`debug` 仅通过 `credit_usage_rates` 配置差异体现成本差异

### 3.8 `bill_renewal_events`

角色：续费排期真相源；不是支付真相源；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `renewal_event_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Billing renewal event business identifier` | 续费事件业务 ID |
| `subscription_bid` | `String(36)` | `not null, default="", index=True` | 关联订阅 | `Billing subscription business identifier` | 订阅业务 ID |
| `creator_bid` | `String(36)` | `not null, default="", index=True` | 所属创作者 | `Creator business identifier` | 创作者业务 ID |
| `event_type` | `SmallInteger` | `not null, index=True` | `7501=renewal; 7502=retry; 7503=cancel_effective; 7504=downgrade_effective; 7505=expire; 7506=reconcile` | `Renewal event type code` | 排期事件类型 |
| `scheduled_at` | `DateTime` | `not null, index=True` | 计划执行时间 | `Scheduled timestamp` | 计划执行时间 |
| `status` | `SmallInteger` | `not null, default=7511, index=True` | `7511=pending; 7512=processing; 7513=succeeded; 7514=failed; 7515=canceled` | `Renewal event status code` | 排期执行状态 |
| `attempt_count` | `Integer` | `not null, default=0` | 已尝试次数 | `Attempt count` | 执行尝试次数 |
| `last_error` | `String(255)` | `not null, default=""` | 最近错误摘要 | `Last error message` | 最近错误 |
| `payload` | `JSON` | `nullable=True` | 事件上下文、重试参数、排期快照 | `Renewal event payload` | 排期扩展载荷 |
| `processed_at` | `DateTime` | `nullable=True` | 最后一次完成处理时间 | `Processed timestamp` | 处理完成时间 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 唯一索引：`renewal_event_bid`
- 唯一约束：`subscription_bid + event_type + scheduled_at`
- 关键索引：`subscription_bid + event_type + scheduled_at`、`status + scheduled_at`

与其他表关系：

- 关联 `bill_subscriptions.subscription_bid`
- 成功执行后通常会生成新的 `bill_orders`

本表职责与边界：

- 负责续费、失败重试、周期结束取消、未来降级和 reconcile 排期
- Worker 必须依赖 `status` 做幂等抢占，不允许同一排期被并发重复执行

## 4. v1.1 扩展表

### 4.1 `bill_entitlements`

角色：权益快照；不是账本真相源；不是报表表；v1.1 才引入。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `entitlement_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Billing entitlement business identifier` | 权益业务 ID |
| `creator_bid` | `String(36)` | `not null, default="", index=True` | 所属创作者 | `Creator business identifier` | 创作者业务 ID |
| `source_type` | `SmallInteger` | `not null, index=True` | `7411=subscription; 7412=topup; 7413=gift; 7416=manual` | `Entitlement source type code` | 权益来源类型 |
| `source_bid` | `String(36)` | `not null, default="", index=True` | 来源业务单号 | `Entitlement source business identifier` | 权益来源业务 ID |
| `branding_enabled` | `SmallInteger` | `not null, default=0` | `0=no; 1=yes` | `Branding enabled flag` | 是否启用品牌定制 |
| `custom_domain_enabled` | `SmallInteger` | `not null, default=0` | `0=no; 1=yes` | `Custom domain enabled flag` | 是否支持自定义域名 |
| `priority_class` | `SmallInteger` | `not null, default=7701` | `7701=standard; 7702=priority; 7703=vip` | `Priority class code` | 队列优先级档位 |
| `analytics_tier` | `SmallInteger` | `not null, default=7711` | `7711=basic; 7712=advanced; 7713=enterprise` | `Analytics tier code` | 分析能力等级 |
| `support_tier` | `SmallInteger` | `not null, default=7721` | `7721=self_serve; 7722=business_hours; 7723=priority` | `Support tier code` | 支持等级 |
| `feature_payload` | `JSON` | `nullable=True` | 细粒度 feature 开关 | `Entitlement feature payload` | 权益扩展载荷 |
| `effective_from` | `DateTime` | `not null, index=True` | 生效开始 | `Effective from timestamp` | 生效开始时间 |
| `effective_to` | `DateTime` | `nullable=True, index=True` | 生效结束 | `Effective to timestamp` | 生效结束时间 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 关键索引：`creator_bid + effective_to`、`source_type + source_bid`

与其他表关系：

- 来源于 `bill_products` 的 entitlement payload 或后台人工调整

本表职责与边界：

- 只在 v1.1 引入
- 如果 v1 只做计费闭环，可直接由套餐商品推导默认权益而不落这张表

### 4.2 `bill_domain_bindings`

角色：域名绑定真相源；不是账务真相源；不是报表表；v1.1 才引入。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `domain_binding_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Billing domain binding business identifier` | 域名绑定业务 ID |
| `creator_bid` | `String(36)` | `not null, default="", index=True` | 所属创作者 | `Creator business identifier` | 创作者业务 ID |
| `host` | `String(255)` | `not null, default="", unique=True` | 绑定域名 | `Custom domain host` | 自定义域名 |
| `status` | `SmallInteger` | `not null, default=7601, index=True` | `7601=pending; 7602=verified; 7603=failed; 7604=disabled` | `Domain binding status code` | 域名绑定状态 |
| `verification_method` | `SmallInteger` | `not null, default=7611` | `7611=dns_txt; 7612=cname; 7613=file` | `Verification method code` | 域名校验方式 |
| `verification_token` | `String(255)` | `not null, default=""` | 校验 token | `Verification token` | 校验 token |
| `last_verified_at` | `DateTime` | `nullable=True` | 最近一次校验成功时间 | `Last verified timestamp` | 最近校验时间 |
| `ssl_status` | `SmallInteger` | `not null, default=7621` | `7621=not_requested; 7622=provisioning; 7623=active; 7624=failed` | `SSL status code` | 证书状态 |
| `metadata` | `JSON` | `nullable=True` | 证书 provider、DNS 检查结果等 | `Domain binding metadata` | 域名扩展元数据 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 唯一索引：`host`
- 关键索引：`creator_bid + status`

与其他表关系：

- 与 `bill_entitlements` 联动，只有启用自定义域名权益的 creator 才允许生效

本表职责与边界：

- 只在 v1.1 引入
- v1 阶段不应让主链路依赖它

### 4.3 `bill_daily_usage_metrics`

角色：usage 日报表聚合；只用于报表；v1.1 才引入。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `daily_usage_metric_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Daily usage metric business identifier` | usage 日聚合业务 ID |
| `stat_date` | `String(10)` | `not null, default="", index=True` | `YYYY-MM-DD` | `Statistic date` | 统计日期 |
| `creator_bid` | `String(36)` | `not null, default="", index=True` | 创作者维度 | `Creator business identifier` | 创作者业务 ID |
| `shifu_bid` | `String(36)` | `not null, default="", index=True` | 课程维度 | `Shifu business identifier` | 师傅业务 ID |
| `usage_scene` | `SmallInteger` | `not null, index=True` | `1201=debug; 1202=preview; 1203=production` | `Usage scene code` | 使用场景 |
| `usage_type` | `SmallInteger` | `not null, index=True` | `1101=LLM; 1102=TTS` | `Usage type code` | usage 类型 |
| `provider` | `String(32)` | `not null, default="", index=True` | provider | `Provider name` | provider |
| `model` | `String(100)` | `not null, default="", index=True` | model | `Provider model` | 模型 |
| `billing_metric` | `SmallInteger` | `not null, index=True` | 见 `7451-7456` | `Billing metric code` | 计费 metric |
| `raw_amount` | `BIGINT` | `not null, default=0` | 原始用量汇总 | `Raw amount` | 原始用量 |
| `record_count` | `BIGINT` | `not null, default=0` | usage 记录数 | `Record count` | 记录条数 |
| `consumed_credits` | `Numeric(20,10)` | `not null, default=0` | 当天扣除积分汇总 | `Consumed credits` | 消耗积分 |
| `window_started_at` | `DateTime` | `not null` | 聚合窗口开始 | `Window start timestamp` | 聚合窗口开始时间 |
| `window_ended_at` | `DateTime` | `not null` | 聚合窗口结束 | `Window end timestamp` | 聚合窗口结束时间 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 建议唯一索引：`stat_date + creator_bid + shifu_bid + usage_scene + usage_type + provider + model + billing_metric`

与其他表关系：

- 从 `bill_usage` 和 `credit_ledger_entries` 增量汇总而来

本表职责与边界：

- 只用于 dashboard、运营分析和快查
- 如与账本不一致，以账本和原始 usage 为准并触发 rebuild

### 4.4 `bill_daily_ledger_summary`

角色：账本日报表聚合；只用于报表；v1.1 才引入。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `daily_ledger_summary_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Daily ledger summary business identifier` | 账本日摘要业务 ID |
| `stat_date` | `String(10)` | `not null, default="", index=True` | `YYYY-MM-DD` | `Statistic date` | 统计日期 |
| `creator_bid` | `String(36)` | `not null, default="", index=True` | 创作者维度 | `Creator business identifier` | 创作者业务 ID |
| `entry_type` | `SmallInteger` | `not null, index=True` | `7401=grant; 7402=consume; 7403=refund; 7404=expire; 7405=adjustment; 7406=hold; 7407=release` | `Billing ledger entry type code` | 分录类型 |
| `source_type` | `SmallInteger` | `not null, index=True` | `7411=subscription; 7412=topup; 7413=gift; 7414=usage; 7415=refund; 7416=manual` | `Billing ledger source type code` | 来源类型 |
| `amount` | `Numeric(20,10)` | `not null, default=0` | 当天同类分录金额汇总 | `Ledger amount total` | 汇总金额 |
| `entry_count` | `BIGINT` | `not null, default=0` | 当天同类分录条数 | `Ledger entry count` | 分录条数 |
| `window_started_at` | `DateTime` | `not null` | 聚合窗口开始 | `Window start timestamp` | 聚合窗口开始时间 |
| `window_ended_at` | `DateTime` | `not null` | 聚合窗口结束 | `Window end timestamp` | 聚合窗口结束时间 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 建议唯一索引：`stat_date + creator_bid + entry_type + source_type`

与其他表关系：

- 从 `credit_ledger_entries` 增量汇总而来

本表职责与边界：

- 只用于后台统计和账务报表
- 如与明细账本不一致，以 `credit_ledger_entries` 为准

## 5. 现有代码改造清单

### 5.1 支付与订单域

当前支付主流程位于 `src/api/flaskr/service/order/funs.py`，特点是：

- 面向学员购课，而不是 creator billing
- 通过 `order_orders`、`order_pingxx_orders`、`order_stripe_orders` 三张旧表落库
- Pingxx 和 Stripe 已有 shared adapter 与 callback 能力抽象，但持久化仍是 provider-specific

v1 的改造要求：

- 旧 `/order` API 和旧订单表全部保留，不做迁移或重构
- 新 billing 不复用 `order_*` 表，只复用并扩展 `service/order/payment_providers/` 的 adapter 层
- 新 billing 路由以 `src/api/flaskr/service/billing/routes.py` 的 plugin route 方式注册，不继续追加到旧 `route/order.py`
- billing 侧新增独立 `service/billing/` 代码层：
  - `models.py`
  - `consts.py`
  - `capabilities.py`
  - `primitives.py`
  - `queries.py`
  - `serializers.py`
  - `read_models.py`
  - `checkout.py`
  - `subscriptions.py`
  - `provider_state.py`
  - `webhooks.py`
  - `trials.py`
  - `settlement.py`
  - `admission.py`
  - `routes.py`
  - `tasks.py`
  - `renewal.py`
  - `funcs.py`（仅兼容导出层）

当前批次最小实现要求：

- 先落 `models.py`、`consts.py`、`routes.py` 和迁移脚本，再把 creator billing 的查询、checkout、sync、webhook 和 paid success 入账拆到各自模块
- 当前实现中，`bill_products`、`bill_subscriptions`、`bill_orders`、`credit_usage_rates`、`bill_renewal_events`、核心唯一约束、bootstrap `credit_usage_rates` seed、billing `sys_configs` seed 以及 provider raw table 的 billing bridge columns，已统一收敛到 `src/api/migrations/versions/b114d7f5e2c1_add_billing_core_phase.py`
- 当前实现中，`src/api/flaskr/common/celery_app.py` 已提供共享 Celery app factory，`src/api/celery_app.py` 作为 worker / beat 入口统一复用 `app.py:create_app()`
- 当前实现中，`src/api/flaskr/common/config.py` 已注册 `CELERY_BROKER_URL`、`CELERY_RESULT_BACKEND`、`CELERY_TASK_ALWAYS_EAGER`，并同步刷新 `docker/.env.example.full`
- 当前实现中，`docker/docker-compose.yml`、`docker/docker-compose.latest.yml`、`docker/docker-compose.dev.yml` 已补 `ai-shifu-redis`、Celery worker、Celery beat 三类服务，并统一为 API / worker / beat 注入容器内 Redis/Celery 地址
- 当前实现中，`src/api/flaskr/service/billing/tasks.py` 已注册 `billing.settle_usage`、`billing.replay_usage_settlement`、`billing.expire_wallet_buckets`、`billing.reconcile_provider_reference`、`billing.send_low_balance_alert`、`billing.run_renewal_event`、`billing.retry_failed_renewal` 以及 v1.1 的 `billing.aggregate_daily_usage_metrics`、`billing.aggregate_daily_ledger_summary`、`billing.rebuild_daily_aggregates`、`billing.verify_domain_binding`
- 当前实现中，`billing.expire_wallet_buckets` 会直接复用 `src/api/flaskr/service/billing/wallets.py:expire_credit_wallet_buckets`，扫描到期 bucket 并落 `credit_ledger_entries.entry_type=expire`
- 当前实现中，`src/api/flaskr/service/billing/cli.py` 已提供 `flask console billing backfill-settlement`、`rebuild-wallets`、`rebuild-daily-aggregates`、`reconcile-order`、`run-renewal-event`、`retry-renewal` 六个离线运维入口，统一复用 service helper，不再单独实现一套 CLI 专属账务逻辑
- 当前实现中，billing v1.1 的所有表结构已统一收敛到 `src/api/migrations/versions/b114d7f5e2c1_add_billing_core_phase.py`
- 当前实现中，`credit_usage_rates` 与 billing `sys_configs` 的 bootstrap 已移出 Alembic，改由 `flask console billing seed-bootstrap-data` 手工执行；付费 plan/topup/custom SKU 改由 `flask console billing upsert-product` 手工录入，不再在 migration 中写死产品目录
- 当前实现中，creator 侧 entitlement/domain/report 的底层表、resolver、聚合任务与 runtime-config 扩展已落地；但 creator 运行时 `/admin/billing` 仍只保留 `packages` / `details` 两个 tab，不额外暴露独立 entitlements/domains/reports 接口
- 当前实现中，learn / preview / debug 的 runtime admission 仅校验 subscription / credits 可用性；不再做 `creator_bid` 维度的 runtime slot 并发限流
- 当前实现中，admin 域名面已收敛为 `GET /admin/billing/domain-audits` 审核视图；creator 自助 bind / verify / disable 不属于当前 active surface
- 当前实现中，`billing.verify_domain_binding` task 已复用 `src/api/flaskr/service/billing/domains.py` 的既有 verify flow：可按 `domain_binding_bid` 或 `host` 加载 binding，并在未显式传 `verification_token` 时回退到绑定上已有 token 做后台刷新
- 当前实现中，`src/api/flaskr/common/shifu_context.py` 已开始在缺少 `shifu_bid` 时回退按 `Host` / `X-Forwarded-Host` 解析 `bill_domain_bindings.host`，但只认可 `status=verified` 且 creator 仍具备 `custom_domain_enabled` 权益的域名
- 当前实现中，`/api/runtime-config` 已开始返回 `entitlements`、`branding`、`domain` 三个 v1.1 扩展字段；当 creator 启用 branding 且 feature payload 提供 logo/home 配置时，会覆盖顶层 `logoWideUrl`、`logoSquareUrl`、`faviconUrl`、`homeUrl`
- 当前实现中，`bill_daily_usage_metrics`、`bill_daily_ledger_summary` 已由 `src/api/flaskr/service/billing/models.py` 和 `src/api/migrations/versions/b114d7f5e2c1_add_billing_core_phase.py` 落地；其中 usage / ledger 两条日报表都已由 `src/api/flaskr/service/billing/daily_aggregates.py` 和 `src/api/flaskr/service/billing/tasks.py` 补齐 `stat_date + creator_bid` 维度的重算任务，增量窗口按 `day_start -> min(now, day_end)` 回填，`finalize=true` 时会重算整天窗口；同时 `rebuild_daily_aggregates` 已支持按 `creator_bid + date window` 全量重算 usage / ledger 报表，若再传 `shifu_bid`，则只重算 usage 报表并跳过 ledger summary，因为 `bill_daily_ledger_summary` 本身不含 `shifu_bid` 维度
- 当前实现中，`src/api/flaskr/service/billing/renewal.py` 已落地 renewal executor：`bill_renewal_events` 通过 `pending/failed -> processing` compare-and-set 抢占；未来排期会释放回 `pending`；`cancel_effective`、`downgrade_effective`、`expire` 会直接推进 `bill_subscriptions` 并把事件标记为 `succeeded`
- 当前实现中，`renewal/retry/reconcile` 已复用同一条 renewal order 补偿链路：`subscription_renewal` 订单会写入 `bill_orders.metadata.provider_reference_type=subscription` 与 `renewal_cycle_*` 周期快照，`POST /billing/orders/{bill_order_bid}/sync`、`billing.retry_failed_renewal` 和 Stripe `customer.subscription.updated` webhook 都会围绕这笔 renewal order 做 paid/failed 状态推进与幂等 grant
- 当前实现中，billing checkout / webhook / sync 编排已分别落在 `src/api/flaskr/service/billing/checkout.py`、`src/api/flaskr/service/billing/webhooks.py`、`src/api/flaskr/service/billing/provider_state.py`，并且只通过 shared `src/api/flaskr/service/order/payment_providers/` adapter 暴露的接口访问 Stripe / Pingxx；`src/api/flaskr/service/billing/funcs.py` 仅保留兼容导出层
- 当前实现中，subscription lifecycle 已由 `src/api/flaskr/service/billing/subscriptions.py` 维护：`subscription_start/subscription_upgrade/subscription_renewal` 的 paid apply 会推进 `bill_subscriptions` 周期字段，并同步维护 `bill_renewal_events`
- 当前实现中，`bill_usage -> credit_ledger_entries` 的多维度结算 helper 已由 `src/api/flaskr/service/billing/settlement.py` 落地；`billing.settle_usage` task entrypoint 已由 `src/api/flaskr/service/billing/tasks.py` 提供，`record_llm_usage` / `record_tts_usage` 会在 billable 的 root usage 落库后投递该异步入口，Celery app factory、worker/beat 基础设施和 creator 维度串行化仍留在后续任务
- 当前实现中，`credit_wallet_buckets` 已承担 source bucket snapshot：paid grant 会按 order type 创建 `subscription` / `topup` bucket，wallet 总余额与冻结余额会从 bucket 表重算，consume 结算会把扣空 bucket 推进到 `exhausted`
- 当前实现中，creator 在有效套餐期内购买 topup 时，grant 会把 topup bucket / ledger 的过期时间对齐到当前套餐 `current_period_end_at`，避免 topup 积分无限期保留
- 当前实现中，usage settlement 已固定按 `subscription > topup` 扣减；同优先级内按 `effective_to` 最早优先，再按 `created_at` 最早优先，`effective_to = null` 排在最后；历史 `free` bucket 会在运行时归并进 `subscription/topup`
- 当前实现中，LLM usage 已拆成 `input`、`cache`、`output` 三个 billing metric 独立计算费率与扣分，并把每个 metric 的 breakdown 写入 `credit_ledger_entries.metadata`
- 当前实现中，TTS usage 已支持两种 billing mode：有 `tts_request_count` 费率时按次扣分；未配置按次费率时回退到 `tts_output_chars`，再回退到 `tts_input_chars` 的按字数扣分
- 当前实现中，`production`、`preview`、`debug` 三种 billing scene 都统一通过 `src/api/flaskr/service/billing/ownership.py` 的 `resolve_usage_creator_bid` 解析归属 creator；优先按 `shifu_bid -> creator_bid`，无 `shifu_bid` 的 debug authoring usage 则回落到 `user_bid`
- 当前实现中，`src/api/flaskr/service/billing/settlement.py` 会在 creator 归属解析完成后，按 `creator_bid` 获取 `billing:settle_usage:{creator_bid}` cache lock，串行执行同一 creator 的 usage settlement 并在异常时释放锁
- 当前实现中，`credit_ledger_entries` 继续只做 append-only 新增写入；`credit_wallets.version` 已用于 optimistic update，grant / settlement 会按 `id + version` compare-and-set 持久化钱包快照，冲突时抛出 `credit_wallet_version_conflict`
- 当前实现中，`credit_ledger_entries.wallet_bucket_bid` 已成为必填字段；usage consume 的 `idempotency_key` 采用 `usage:{usage_bid}:{billing_metric}:{wallet_bucket_bid}:consume`，grant 也会把 ledger 与 bucket 一一关联
- 当前实现中，`src/api/flaskr/service/billing/wallets.py` 已提供 bucket 生命周期 helper：扣空 bucket 进入 `exhausted`；`expire_credit_wallet_buckets` 会把到期 bucket 迁移为 `expired` 并写 `expire` ledger；`grant_refund_return_credits` 会把 refund return 新增为 `subscription/topup` bucket + `refund` ledger，不回原 bucket
- 当前实现中，admission 前置拦截只认可“当前可消费”的 bucket：必须 `status=active`、`available_credits>0`、`effective_from<=now` 且 `effective_to>now/null`；已到期 bucket、未来生效 bucket 和失效订阅都不会放行 learn / preview / debug 请求
- 当前实现中，`replay_bill_usage_settlement` / `billing.replay_usage_settlement` 已落地：重放时会复用既有 usage 幂等检查，已结算 usage 返回 `already_settled` 而不会重复扣分；若传入的 `creator_bid` 与 usage 实际归属不一致，则直接返回 `creator_mismatch`
- 旧 `service/order/payment_providers/` 继续作为 provider 能力来源；如需 billing-specific 参数或返回结构，可在 adapter 层做最小扩展，但不把 creator billing 挂回旧订单表

旧 `order` 域明确不改的范围：

- `order_orders`
- `order_pingxx_orders`
- `order_stripe_orders`
- 旧购课 admin 页面
- 旧学员购课退款逻辑

### 5.2 Metering 与结算入口

当前 metering 代码位于：

- `src/api/flaskr/service/metering/consts.py`
- `src/api/flaskr/service/metering/recorder.py`
- `src/api/flaskr/service/metering/models.py`

当前已存在的事实：

- LLM/TTS usage 已经会落到 `bill_usage`
- `record_llm_usage` / `record_tts_usage` 默认把 `production` / `preview` / `debug` 都视为可计费 usage
- 只有显式传入 `billable=0` 的内部调用才会保留免计费语义

当前约束：

- `production`、`preview`、`debug` 三种 scene 都允许计费
- 是否真正扣费不再由 metering 常量决定，而由 billing service 的 admission / settlement 规则决定
- `record_llm_usage` / `record_tts_usage` 继续只负责原始 usage 落库，并在 billable 的 root usage 成功写入后异步投递 settlement，不直接承担 creator 账务逻辑
- 结算层新增 `creator ownership resolver`，优先把 `shifu_bid -> creator_bid` 固化给 billing settlement 使用，debug authoring 的无 `shifu_bid` usage 再回落到 `user_bid`
- 当前实现将该边界收敛到 `src/api/flaskr/service/billing/ownership.py`，由 billing 域统一复用 `resolve_shifu_creator_bid` / `resolve_usage_creator_bid`

### 5.3 Learn / Preview / Debug 入口改造

当前学习与预览链路已经会写 usage，包括：

- learn 正式学习链路
- preview block 链路
- preview tts 链路
- debug 场景下的模型和语音调用

v1 需要新增的改造点：

- 在 learn / preview / debug 的 billable 动作入口前增加 `admission service`
- admission 至少校验：
  - creator 钱包余额
  - creator 订阅状态
- admission 拒绝后，不进入新的 billable LLM/TTS 调用
- 当前实现已落到 `src/api/flaskr/service/billing/admission.py`，并接入 `src/api/flaskr/service/learn/routes.py` 与 `src/api/flaskr/service/shifu/route.py` 的 billable 入口
- usage 落库成功后，统一投递 Celery settlement task，再由 task 消费 `bill_usage` 并写入 `credit_ledger_entries`
- 不允许在 learn / preview / debug 的请求线程内直接扣减积分、更新 `credit_wallet_buckets` 或刷新 `credit_wallets`
- 当前 `src/api/flaskr/service/metering/recorder.py` 仍只负责 `bill_usage` 持久化，不触碰 `credit_wallets`、`credit_wallet_buckets`、`credit_ledger_entries`
- v1 不做运行时并发配额控制，但必须在结算层实现 `creator_bid` 维度串行化，避免多个学生同时学习同一 creator 课程时发生并发扣减算错
- 当前版本已确认不再引入 creator runtime 并发配额；entitlement 侧只保留 `priority_class`、branding、domain、analytics、support 等扩展能力

### 5.4 Runtime Config 与前端边界

当前 runtime config 位于 `src/api/flaskr/route/config.py`，输出全局：

- `logoWideUrl`
- `logoSquareUrl`
- `faviconUrl`
- `homeUrl`

边界约束：

- v1 不改全局 `/api/config` 为 creator-scoped
- v1 前端只新增 Billing Center，不要求接管全站 branding 输出
- v1.1 再扩展 entitlement / branding / domain 相关返回
- 旧 `src/api/flaskr/route/order.py`、旧 order admin、`src/api/flaskr/service/metering/models.py` 的 raw `bill_usage` 结构在 v1 保持原状，不并入 creator billing 路由或 schema

### 5.5 现有后台线程模式替换

当前仓库存在 ad-hoc 线程后台模式，例如 `src/api/flaskr/service/shifu/shifu_publish_funcs.py` 的 `threading.Thread(...)`。

v1 约束：

- billing 新增异步任务不允许继续沿用这种线程模式
- usage settlement、续费、重试、对账、结算 replay、低余额提醒统一走 Celery
- 旧业务暂不强制迁移到 Celery，但 billing 域从第一版开始必须统一

## 6. Celery 接入与基础设施

说明：

- 本章描述完整 billing v1 的基础设施目标
- 当前 “Figma `方案1` + 可联调 MVP” 批次先以支付成功入账和读模型可查询为交付目标，不以 Celery 上线作为前端联调阻塞项
- 但未来所有实际 usage 扣减、续费、失败重试和 bucket 过期仍必须回到本章定义的 Celery 方案

### 6.1 接入目标

Celery 是 billing v1 必做基础设施，原因是 billing 至少需要：

- 周期续费
- 失败重试
- creator 维度串行的 usage settlement
- provider 补偿同步
- settlement replay / reconcile
- 低余额提醒

这些任务不应继续塞进同步请求尾部，也不应使用 ad-hoc 线程执行。

### 6.2 Flask App Factory 集成

Celery 应复用 `src/api/app.py` 的 `create_app()` 作为唯一 Flask 配置入口。

建议新增：

- `src/api/flaskr/common/celery_app.py`
- `src/api/flaskr/service/billing/tasks.py`

集成要求：

- Celery worker 启动时通过 app factory 创建 Flask app
- task 执行时自动进入 `app.app_context()`
- Flask 配置和 Celery 配置统一从 `common/config.py` 读取
- usage settlement task 必须支持 `creator_bid` 维度的串行化执行，避免同一 creator 的扣减逻辑并发重入

### 6.3 Celery 配置

v1 需要补充以下环境变量和配置项：

| 配置项 | 用途 |
| --- | --- |
| `CELERY_BROKER_URL` | Redis broker 地址 |
| `CELERY_RESULT_BACKEND` | 结果后端，默认可与 broker 同源 Redis |
| `CELERY_TASK_ALWAYS_EAGER` | 测试环境同步执行任务 |
| `BILLING_RENEWAL_CRON` | 续费排期调度表达式 |
| `BILLING_RECONCILE_CRON` | provider reconcile 调度表达式 |
| `BILLING_BUCKET_EXPIRE_CRON` | 余额桶过期扫描调度表达式 |
| `BILLING_LOW_BALANCE_CRON` | 低余额扫描调度表达式 |
| `BILLING_DAILY_AGGREGATE_CRON` | 日汇总调度表达式，v1.1 才启用 |

同时在 `sys_configs` 预置以下 billing bootstrap 配置：

- `BILL_ENABLED=0`
- `BILL_LOW_BALANCE_THRESHOLD=0.0000000000`
- `BILL_RENEWAL_TASK_CONFIG={"enabled":0,"batch_size":100,"lookahead_minutes":60,"queue":"billing-renewal"}`
- `BILL_RATE_VERSION=bootstrap-v1`

v1 冻结低余额阈值、告警与错误码规则：

- `BILL_LOW_BALANCE_THRESHOLD` 在当前批次固定为 `0.0000000000` credits；也就是只有当 `wallet.available_credits <= 0` 时才触发低余额告警，不额外引入“剩余 10%”或“剩余 N credits”之类的第二阈值
- `GET /billing/overview` 的 `billing_alerts` 只冻结 3 类 code：
  - `low_balance`：`severity=warning`，触发条件为 `available_credits <= BILL_LOW_BALANCE_THRESHOLD`，`action_type=checkout_topup`
  - `subscription_past_due`：`severity=error`，触发条件为订阅状态 `past_due`，`action_type=open_orders`
  - `subscription_cancel_scheduled`：`severity=info`，触发条件为 `cancel_at_period_end=1`，`action_type=resume_subscription`
- `billing_alerts` 一律通过 `message_key + message_params` 渲染，不在接口里返回拼接好的自然语言；v1 固定使用：
  - `module.billing.alerts.lowBalance`
  - `module.billing.alerts.subscriptionPastDue`
  - `module.billing.alerts.cancelScheduled`
- creator runtime admission 的阻断错误码在 v1 固定只使用 `server.billing` 命名空间下的 2 个 key：
  - `server.billing.creditInsufficient`：当前没有任何处于有效期内、可消费且余额大于 `0` 的 bucket
  - `server.billing.subscriptionInactive`：当前没有 active-like subscription，且也没有任何 `free/topup` bucket 可兜底
- `server.billing.creditInsufficient` 的文案语义固定为“积分不足，请先充值或开通订阅”；`server.billing.subscriptionInactive` 的文案语义固定为“订阅不可用且没有免费/充值积分可继续使用”；后续多语言翻译必须保持这个语义边界，不扩展额外业务分支说明
- v1 不再新增新的 backend billing admission 错误码；更多 UI 提示优先通过 `billing_alerts` 承载，而不是扩散新的阻断错误 key
- 当前版本不再保留 `server.billing.concurrencyExceeded`；runtime admission 阻断只围绕 credits / subscription 状态

### 6.4 Worker / Beat 分工

- `celery-worker`
  - 执行 usage settlement、renewal、retry、reconcile、settlement replay、wallet bucket expiration、low balance alert
  - v1.1 再执行 domain verify、daily aggregate、rebuild
- `celery-beat`
  - 只负责调度任务
  - 不承载业务逻辑

### 6.5 v1 必做 Tasks

| Task Name | 作用 | 最小 payload |
| --- | --- | --- |
| `billing.settle_usage` | 异步串行执行单条 usage 的积分扣减 | `creator_bid`, `usage_bid` |
| `billing.run_renewal_event` | 执行一次续费排期事件 | `renewal_event_bid`, `subscription_bid`, `creator_bid` |
| `billing.retry_failed_renewal` | 对失败续费进行重试 | `renewal_event_bid`, `bill_order_bid`, `provider_reference_id` |
| `billing.reconcile_provider_reference` | 对账或补偿同步 provider 状态 | `payment_provider`, `provider_reference_id`, `bill_order_bid` |
| `billing.replay_usage_settlement` | 重放 usage 结算 | `creator_bid`, `usage_bid` 或 `usage_id_start/usage_id_end` |
| `billing.expire_wallet_buckets` | 扫描到期余额桶并写入过期账本 | `creator_bid` 或批量扫描窗口 |
| `billing.send_low_balance_alert` | 扫描并通知低余额 creator | `creator_bid` 或批量扫描窗口 |

额外执行约束：

- 所有实际积分扣减统一通过 `billing.settle_usage` 或 `billing.replay_usage_settlement` 完成
- 当前实现已提供 `billing.settle_usage` 任务入口，并由该入口复用 `src/api/flaskr/service/billing/settlement.py` 执行单条 usage 结算；后续再接入统一 Celery app、broker 和 worker 编排
- 同一 `creator_bid` 的 usage settlement 任务不可并发执行，必须依赖 creator-scoped lock、串行队列或等价机制保证防重入

### 6.6 v1.1 扩展 Tasks

| Task Name | 作用 | 最小 payload |
| --- | --- | --- |
| `billing.aggregate_daily_usage_metrics` | 生成 usage 日聚合 | `stat_date`, `creator_bid` 可选，`finalize` 可选 |
| `billing.aggregate_daily_ledger_summary` | 生成 ledger 日聚合 | `stat_date`, `creator_bid` 可选，`finalize` 可选 |
| `billing.rebuild_daily_aggregates` | 重建日报表 | `creator_bid`, `shifu_bid`, `date_from`, `date_to` |
| `billing.verify_domain_binding` | 域名校验与状态刷新 | `domain_binding_bid`, `creator_bid` |

### 6.7 Docker 与本地开发

当前 `docker-compose.yml`、`docker-compose.latest.yml`、`docker-compose.dev.yml` 都没有 Redis/Celery 服务。

v1 需要新增：

- `redis`
- `celery-worker`
- `celery-beat`

接入要求：

- API 服务继续只负责 HTTP 请求
- worker / beat 独立容器运行
- 本地开发命令中要明确如果只启动 Flask 而不启动 worker / beat，billing 的异步链路不可用

### 6.8 CLI 与运维辅助

- 保留 Flask CLI 作为 backfill / rebuild / manual replay 的入口
- 在线周期调度和在线执行交给 Celery
- 不再把周期扫描任务写进 HTTP route、`threading.Thread` 或 gunicorn worker 内部
- 当前实现固定使用 `flask console billing ...` 作为运维入口：
  - `backfill-settlement`：离线 replay usage settlement，只用于 backfill / repair
  - `rebuild-wallets`：从 `credit_wallet_buckets` 重建 `credit_wallets` 快照
  - `reconcile-order`：手动触发 provider sync / orphan recovery
  - `run-renewal-event`、`retry-renewal`：手动执行 renewal / retry / reconcile 补偿
- 分工固定为：
  - CLI：人工触发、离线修复、历史回填、定点 replay
  - Celery：在线请求后的异步执行、周期调度、批量扫描和重试

## 7. 结算、支付与接口

### 7.1 支付与订阅

- `GET /billing/catalog` 读取 `bill_products`，但 API 返回仍按 `plans[]` / `topups[]` 投影
- `POST /billing/subscriptions/checkout` 只能购买 `product_type=plan`
- `POST /billing/topups/checkout` 只能购买 `product_type=topup`，且 creator 当前必须处于有效套餐周期内
- public trial plan 不允许通过 creator 自助 checkout；只允许 post-auth bootstrap 以 `manual` provider 自动创建
- `bill_orders` 是统一支付动作单；Stripe/Pingxx/Alipay/WeChat Pay 业务编排一致，差异只放在 shared provider adapter
- webhook 不单独落事件表；直接按 `bill_orders` 状态机做幂等推进，最新摘要只保留最近一次，同时镜像更新关联 provider raw snapshot
- 自动续费和失败重试由 `bill_renewal_events` 驱动，成功后生成新的 `bill_orders`
- 当前批次 provider 能力矩阵固定为：
  - Stripe：支持 `subscription_start` checkout、`topup` checkout、webhook、sync、`refund_payment`、paid success grant
  - Pingxx：支持 `topup` checkout、`subscription_start` checkout、webhook、sync，以及通过本地 renewal order 继续支付；`refund_payment` 继续显式返回 `unsupported`
  - Alipay：支持 `alipay_qr` 一次性 checkout、webhook、sync、paid success grant；`subscription_start` 仍按一次性支付激活本地订阅；`refund_payment` 返回 `unsupported`
  - WeChat Pay：支持 `wx_pub_qr` / `wx_pub` 一次性 checkout、webhook、sync、paid success grant；`subscription_start` 仍按一次性支付激活本地订阅；`refund_payment` 返回 `unsupported`
- `POST /billing/orders/{bill_order_bid}/sync` 是当前批次的主补偿入口，前端支付回跳默认先调 sync 再刷新 overview / orders
- 当前批次已落地真实 paid success 入账：Stripe/Pingxx/Alipay/WeChat Pay `subscription_start` 与 `topup` 支付成功后，必须幂等写入 `credit_wallet_buckets` grant bucket、`credit_ledger_entries` grant entry，并刷新 `credit_wallets`；重复 sync / webhook 不得重复发放
- 当前实现中，`subscription_upgrade` / `subscription_renewal` 的 paid apply 会同步推进 `bill_subscriptions.product_bid/current_period_*/next_product_bid`，并维护 `bill_renewal_events` 的 `renewal/retry/cancel_effective/downgrade_effective`
- 当前实现中，Stripe subscription `past_due` 会回填 `grace_period_end_at`，取消或退款后会取消待执行的 renewal event
- 当前实现中，trial bootstrap 会创建一笔 `payment_provider='manual'`、金额为 `0` 的 `subscription_start` 订单和对应 subscription，并复用 paid-order grant helper 写入 wallet bucket、ledger 与 subscription 生命周期
- 当前实现中，active 的非自动续费 subscription 只要存在 `current_period_end_at`，都会同步生成 `expire` renewal event；因此 manual trial 会在 15 天后进入 `expired`

### 7.2 扣分与结算

- 学员正式学习 `production`、作者 `preview`、作者 `debug` 统一扣课程所属创作者积分
- LLM 一条 usage 默认按三条费率结算：
  - `7451=llm_input_tokens`
  - `7452=llm_cache_tokens`
  - `7453=llm_output_tokens`
- TTS 一条 usage 默认只命中一种主费率：
  - `7454=tts_request_count`
  - 或 `7455=tts_output_chars`
- 结算真相源为：
  - 原始 usage：`bill_usage`
  - 积分真相：`credit_ledger_entries`
  - 余额桶快照：`credit_wallet_buckets`
  - 余额快照：`credit_wallets`
- 所有实际积分扣减统一异步走 Celery settlement task；请求线程只负责准入判断和 usage 落库
- 结算执行顺序固定为：先选择 `credit_wallet_buckets`，再写入 `credit_ledger_entries`，最后刷新 `credit_wallets`
- 同一 `creator_bid` 的结算任务必须串行化，避免多个学生同时学习同一 creator 课程时发生并发扣减算错
- bucket 扣减顺序固定为：`subscription > topup`；同优先级内按 `effective_to` 最早优先，再按 `created_at` 最早优先
- `gift`、正向人工补偿、退款返还不再形成第三类可消费 credits；它们仅保留为 `source_type`，bucket 统一归到 `subscription/topup`
- 一条 usage 可以拆成多个 bucket 扣减，但默认只生成一条聚合 `consume` ledger；bucket 明细保留在 `metadata.bucket_breakdown[]`
- bucket 过期任务只扫描 `credit_wallet_buckets`；过期后写 `expire` ledger 并把 bucket 关闭
- 结算幂等 key 应至少以 `bill_usage.usage_bid` 为核心保证 usage 级去重；bucket 级扣减明细保留在 metadata 里
- 当前实现中，`src/api/flaskr/service/billing/settlement.py` 已支持：
  - LLM `input/cache/output` 三维 rate 匹配与扣分
  - TTS 主 metric 结算
  - `credit_wallet_buckets -> credit_ledger_entries -> credit_wallets` 的顺序写入
  - usage 级幂等、防 segment/non-billable 重复结算，以及 exact rate 优先于 wildcard rate

### 7.3 现有接口如何改造

- 旧 `/order` 保持不变，只说明“不复用其表结构”
- 新 `/billing` 接口继续独立
- 现有 `/api/order/stripe/webhook`、`/api/callback/pingxx-callback` 继续作为 provider callback 入口；native 国内直连新增 `/api/callback/alipay-notify` 与 `/api/callback/wechatpay-notify`，统一复用 shared provider adapter 验签/归一化结果，再直接推进 billing order / subscription 状态
- `/api/config` 在 v1 继续保持全局配置输出；v1.1 开始允许在 `runtime-config` 中附加 creator-scoped `entitlements`、`branding`、`domain` 结果，并按 branding override 顶层 logo/home 字段

### 7.4 内部支付接口契约

```ts
interface BillingPaymentProviderAdapter {
  create_checkout(input: {
    bill_order_bid: string;
    creator_bid: string;
    product_bid: string;
    payment_provider: string;
    channel: string;
  }): Promise<ProviderCheckoutResult>;

  create_recurring_subscription(input: {
    bill_order_bid: string;
    creator_bid: string;
    subscription_bid: string;
    product_bid: string;
  }): Promise<ProviderSubscriptionResult>;

  cancel_subscription(input: {
    subscription_bid: string;
    provider_subscription_id: string;
  }): Promise<ProviderSubscriptionResult>;

  resume_subscription(input: {
    subscription_bid: string;
    provider_subscription_id: string;
  }): Promise<ProviderSubscriptionResult>;

  refund_payment(input: {
    bill_order_bid: string;
    provider_reference_id: string;
    amount?: number;
  }): Promise<ProviderRefundResult>;

  verify_webhook(input: {
    headers: Record<string, string>;
    raw_body: string;
  }): Promise<VerifiedProviderEvent>;

  sync_reference(input: {
    provider_reference_id: string;
    reference_type: string;
  }): Promise<ProviderSyncResult>;
}
```

- `verify_webhook` 返回归一化事件后，调用方直接按订单状态机推进 `bill_orders` / `bill_subscriptions`
- `sync_reference` 只做主动对账与状态补偿，不生成独立 webhook 记录
- 当前实现约束：`service/billing` 与旧 `/order` 仅复用 shared `payment_providers` adapter 暴露的 checkout/subscription/webhook/sync/refund 接口，不直接耦合 provider SDK；业务状态不复用旧 `order_orders`，provider raw snapshot 通过 `order_pingxx_orders` / `order_stripe_orders` / `order_native_payment_orders` 按 provider 与 `biz_domain` 隔离

### 7.5 前端实现方案

当前前端的已知事实：

- App Router 入口集中在 `src/cook-web/src/app/`
- 接口定义集中在 `src/cook-web/src/api/api.ts`
- 请求封装集中在 `src/cook-web/src/lib/request.ts`
- 运行时配置通过 `src/cook-web/src/lib/initializeEnvData.ts` 写入 `envStore`
- 管理端统一布局在 `src/cook-web/src/app/admin/layout.tsx`
- 现有订单管理页已经使用 `Table + Sheet + 本地状态/搜索参数` 的管理端交互模式
- `/admin` 现有创作中心首页已经接近目标结构；当前批次只做 Figma `方案1` 浅色稿对齐，不重做信息架构

v1 前端不新建全局 billing store，默认采用：

- 读接口：SWR
- 写接口：统一 `api` 方法 + 成功后 `mutate`
- 页面局部状态：`useState`
- 公共类型：新增 `src/cook-web/src/types/billing.ts`

#### 7.5.1 v1 路由与页面结构

当前批次固定采用 Figma `方案1` 浅色稿，对 creator admin 侧只落一个 Billing Center 单路由，避免一开始拆太多子页面。

- 新增 `src/cook-web/src/app/admin/billing/page.tsx`
- 在 `src/cook-web/src/app/admin/layout.tsx` 侧边栏新增常驻 `我的会员` 卡片
- 在 `src/cook-web/src/app/admin/layout.tsx` 侧边栏新增 `会员与积分` 菜单，统一跳转到 `/admin/billing`
- Billing Center 使用 `Tabs` 拆成两个视图：
  - `套餐与积分`
  - `积分明细`

页面职责：

- `套餐与积分`
  - 读取 `GET /billing/overview`
  - 并行读取 `GET /billing/catalog`
  - 展示当前订阅、钱包余额、低余额/续费异常告警
  - 展示套餐目录和充值包目录
  - 承载订阅 checkout、恢复订阅、取消订阅、购买充值包入口
- `积分明细`
  - 按需读取 `GET /billing/wallet-buckets`
  - 读取 `GET /billing/ledger`
  - 展示 bucket 来源摘要、积分流水、来源类型、余额变化，以及最近 activity
  - usage 类明细通过右侧 detail sheet 展开

#### 7.5.2 v1 组件拆分

建议新增 `src/cook-web/src/components/billing/`，至少包含：

- `BillingSidebarCard.tsx`
- `BillingAlertsBanner.tsx`
- `BillingOverviewHero.tsx`
- `BillingOverviewCards.tsx`
- `BillingOverviewShowcase.tsx`
- `BillingOverviewTab.tsx`
- `BillingCreditDetailsPanel.tsx`
- `BillingRecentActivitySection.tsx`
- `BillingUsageDetailSheet.tsx`
- `BillingCheckoutDialog.tsx`
- `BillingPingxxQrDialog.tsx`

组件约束：

- 表格、抽屉、对话框统一复用现有 `ui` 组件
- 详情查看沿用现有订单页的 `Sheet` 交互，不使用新窗口跳转
- 购买动作统一在 dialog 中确认，再调用 checkout API

#### 7.5.3 API 接入与前端类型

需要在 `src/cook-web/src/api/api.ts` 增加：

- `getBillingCatalog`
- `getBillingOverview`
- `getBillingWalletBuckets`
- `getBillingLedger`
- `syncBillingOrder`
- `checkoutBillingOrder`
- `checkoutBillingSubscription`
- `cancelBillingSubscription`
- `resumeBillingSubscription`
- `checkoutBillingTopup`
- `getAdminBillingSubscriptions`
- `getAdminBillingOrders`
- `adjustAdminBillingLedger`

需要在 `src/cook-web/src/types/billing.ts` 定义：

- `BillingPlan`
- `BillingTopupProduct`
- `BillingSubscription`
- `BillingWalletBucket`
- `BillingLedgerItem`
- `BillingOrderSummary`
- `CreatorBillingOverview`
- `BillingCheckoutResult`

前端数据获取策略：

- `getBillingCatalog` 和 `getBillingOverview` 在 `Overview` tab 首屏并行请求
- `getBillingWalletBuckets` 作为只读明细查询按需加载，不并入 `Overview` 首屏返回
- `getBillingLedger` 在 `Details` tab 激活时懒加载；order sync / checkout 由 Stripe result、Pingxx polling 和 checkout dialog 按需触发
- 写操作成功后只刷新受影响的 SWR key，不全页硬刷新

#### 7.5.4 Stripe 支付回跳

当前现有 Stripe 回跳页 `src/cook-web/src/app/payment/stripe/result/page.tsx` 是学员购课专用，成功后会跳到课程页，不适合 creator billing 直接复用。

v1 前端方案：

- 新增 `src/cook-web/src/app/payment/stripe/billing-result/page.tsx`
- 后端从 `HOST_URL` 派生 Stripe billing result URL
- billing result 页职责：
  - 从 query 读取 `bill_order_bid` / `session_id`
  - 先调用 `POST /billing/orders/{bill_order_bid}/sync`
  - 必要时允许用户重试 sync，并在成功后回跳 `/admin/billing`
  - 成功后跳回 `/admin/billing`
  - 待支付或失败时展示明确状态和重试入口

#### 7.5.5 v1.1 前端扩展

v1.1 继续沿用 `/admin/billing`，在同一路由上增加扩展 tab：

- `Entitlements`
- `Domains`
- `Reports`

当前实现状态：

- `src/cook-web/src/app/admin/billing/page.tsx` 当前运行时只保留 2-tab shell：`Plans`、`Details`
- creator 侧 live surface 收敛为 overview checkout、Pingxx polling、Stripe billing result sync，以及 details 页中的 wallet / ledger activity
- creator 侧 `Orders`、`Entitlements`、`Domains`、`Reports` 扩展 tab 当前不接线，也不宣称为 shipped UI
- `src/cook-web/src/app/admin/billing/admin/page.tsx` 现已扩展为 6-tab ops console：`Subscriptions`、`Orders`、`Exceptions`、`Entitlements`、`Domains`、`Reports`
- admin `Entitlements` tab 已接入 `GET /admin/billing/entitlements`，查看跨 creator 的有效权益快照
- admin `Domains` tab 已接入 `GET /admin/billing/domain-audits`，审核跨 creator 的自定义域名状态与 entitlement gate
- admin `Reports` tab 已接入 `GET /admin/billing/reports/usage-daily` 与 `GET /admin/billing/reports/ledger-daily`，查看跨 creator usage / ledger 汇总

页面职责：

- creator `/admin/billing`
  - `Plans`：展示 overview、catalog、alerts、checkout 与订单同步入口
  - `Details`：展示 wallet bucket 明细、ledger activity 与 usage detail sheet
- admin `/admin/billing/admin`
  - 保留 `Subscriptions`、`Orders`、`Exceptions`、`Entitlements`、`Domains`、`Reports` 六个 ops tab

#### 7.5.6 i18n 与状态展示

前端新增文案统一使用 `module.billing.*` 命名空间，至少覆盖：

- 页面标题和 tab 标题
- 订阅状态文案
- 支付状态文案
- 账本类型和来源类型文案
- 低余额、续费失败、宽限期结束提示
- checkout、cancel、resume、topup 的确认文案

状态展示约束：

- 前端不要直接展示数值码，统一映射为 i18n 文案
- API 返回如已带 `*_key`，前端优先用 key 渲染；否则按本地 code map fallback
- `billing_alerts` 优先使用 `message_key + message_params` 渲染，不直接消费后端拼接文案

## 8. 公共 API 与类型

### 8.1 v1 核心 API

- `GET /billing/catalog`
- `GET /billing/overview`
- `GET /billing/wallet-buckets`
- `GET /billing/ledger`
- `POST /billing/orders/{bill_order_bid}/sync`
- `POST /billing/orders/{bill_order_bid}/checkout`
- `POST /billing/orders/{bill_order_bid}/refund`
- `POST /billing/subscriptions/checkout`
- `POST /billing/subscriptions/cancel`
- `POST /billing/subscriptions/resume`
- `POST /billing/topups/checkout`
- `POST /order/stripe/webhook`
- `POST /callback/pingxx-callback`
- `GET /admin/billing/subscriptions`
- `GET /admin/billing/orders`
- `POST /admin/billing/ledger/adjust`

核心接口说明：

- `GET /billing/catalog`：读取 `bill_products`，输出 `plans[]` 与 `topups[]`
- `GET /billing/overview`：返回 `wallet`、`subscription`、`billing_alerts`、`trial_offer`，同时支撑 sidebar 会员卡、Billing Center 顶部 summary 和免费试用卡片
- `GET /billing/wallet-buckets`：按 creator 返回积分来源 bucket 列表，字段至少包括 `category`、`source_type`、`source_bid`、`available_credits`、`effective_from`、`effective_to`、`priority`、`status`，默认按实际扣减顺序排序
- `GET /billing/ledger`：按时间倒序分页返回账本流水
- `POST /billing/orders/{bill_order_bid}/sync`：按 `bill_order_bid` 和 provider reference 主动同步支付状态
- `POST /billing/orders/{bill_order_bid}/checkout`：对已创建的待支付订单继续发起 provider checkout
- `POST /billing/orders/{bill_order_bid}/refund`：creator 对已支付 billing 订单发起退款；当前批次仅 Stripe 支持，Pingxx 返回 `unsupported`
- `POST /billing/subscriptions/checkout`：新开订阅、升级补差或恢复订阅
- `POST /billing/subscriptions/cancel` / `POST /billing/subscriptions/resume`：creator 取消或恢复订阅；manual trial subscription 不支持 cancel/resume；退款成功后如有关联订阅，当前批次会同步把订阅标记为 `canceled`
- `POST /billing/topups/checkout`：在当前有效套餐周期内发起一次性充值支付
- checkout 接口统一返回 `bill_order_bid`、`provider`、`payment_mode`、`status`
- Stripe checkout 返回 redirect URL 或 checkout session 信息；Pingxx topup 和 subscription order 都返回一次性 charge 所需 payload
- `POST /order/stripe/webhook` / `POST /callback/pingxx-callback`：继续作为 provider 回调入口；负责验签、归一化、按订单状态机推进 `bill_orders`、推进 `bill_subscriptions`，把最近摘要覆盖写入关联 `bill_orders.metadata`，并更新关联 provider raw snapshot
- `GET /admin/billing/orders`：后台运营侧查询 creator billing 订单
- `POST /admin/billing/ledger/adjust`：后台人工调整积分，必须写入 `credit_ledger_entries`

### 8.2 v1.1 扩展 API

- `GET /admin/billing/domain-audits`
- `GET /admin/billing/entitlements`
- `GET /admin/billing/reports/usage-daily`
- `GET /admin/billing/reports/ledger-daily`

扩展接口说明：

- `GET /admin/billing/domain-audits`：按后台分页查看跨 creator 的域名绑定审核数据，支持 `creator_bid`、`status`、`page_index`、`page_size`
- `GET /admin/billing/entitlements`：按后台分页查看跨 creator 的有效权益快照，支持 `creator_bid`、`page_index`、`page_size`
- `GET /admin/billing/reports/usage-daily`：按后台分页查看跨 creator usage 日汇总，支持 `creator_bid`、`date_from`、`date_to`、`page_index`、`page_size`、`timezone`
- `GET /admin/billing/reports/ledger-daily`：按后台分页查看跨 creator ledger 日汇总，支持 `creator_bid`、`date_from`、`date_to`、`page_index`、`page_size`、`timezone`
- `GET /api/runtime-config`：在保留现有全局配置字段的同时，追加 `entitlements`、`branding`、`domain` 三个 v1.1 扩展结果；若 branding 命中，会同步覆盖顶层 logo/home 字段以兼容现有前端初始化逻辑

### 8.3 DTO 投影

说明：

- `BillingPlan` 和 `BillingTopupProduct` 是 `bill_products` 的展示层投影，不是底层独立表
- `BillingTrialOffer` 也是 `bill_products` 的展示层投影，但只用于 overview 免费卡片，不进入自助购买 catalog
- v1 的 `CreatorBillingOverview` 返回钱包、订阅、告警和 `trial_offer`
- `BillingWalletBucket` 是 `credit_wallet_buckets` 的只读投影，不并入 `CreatorBillingOverview`
- billing order DTO 如需暴露 provider 调试信息，优先读取 `bill_orders.metadata` 的最近一次摘要；更完整的 provider 原始对象从 `order_pingxx_orders` / `order_stripe_orders` 的 billing raw snapshot 查看，不设计 append-only 事件历史
- `entitlements`、`branding`、`domains` 属于 v1.1 扩展输出
- `usage_type` / `usage_scene` 的数值来源于 `metering.consts`
- billing 相关状态、类型、metric 的数值来源于未来的 `service/billing/consts.py`

```ts
type BillingPlan = {
  product_bid: string;
  product_code: string;
  product_type: 'plan';
  display_name: string;
  description: string;
  billing_interval: 'day' | 'month' | 'year';
  billing_interval_count: number;
  currency: string;
  price_amount: number;
  credit_amount: number;
  auto_renew_enabled: boolean;
};

type BillingTopupProduct = {
  product_bid: string;
  product_code: string;
  product_type: 'topup';
  display_name: string;
  description: string;
  currency: string;
  price_amount: number;
  credit_amount: number;
};

type BillingSubscription = {
  subscription_bid: string;
  product_bid: string;
  product_code: string;
  status: 'draft' | 'active' | 'past_due' | 'paused' | 'cancel_scheduled' | 'canceled' | 'expired';
  billing_provider: string;
  current_period_start_at: string | null;
  current_period_end_at: string | null;
  grace_period_end_at: string | null;
  cancel_at_period_end: boolean;
  next_product_bid: string | null;
  last_renewed_at: string | null;
  last_failed_at: string | null;
};

type BillingWalletBucket = {
  wallet_bucket_bid: string;
  category: 'subscription' | 'topup';
  source_type: 'subscription' | 'topup' | 'gift' | 'refund' | 'manual';
  source_bid: string;
  available_credits: number;
  effective_from: string;
  effective_to: string | null;
  priority: number;
  status: 'active' | 'exhausted' | 'expired' | 'canceled';
};

type BillingLedgerItem = {
  ledger_bid: string;
  wallet_bucket_bid: string;
  entry_type: 'grant' | 'consume' | 'refund' | 'expire' | 'adjustment' | 'hold' | 'release';
  source_type: 'subscription' | 'topup' | 'gift' | 'usage' | 'refund' | 'manual';
  source_bid: string;
  idempotency_key: string;
  amount: number;
  balance_after: number;
  expires_at: string | null;
  consumable_from: string | null;
  metadata: {
    usage_bid?: string;
    usage_scene?: 'debug' | 'preview' | 'production';
    provider?: string;
    model?: string;
    metric_breakdown?: Array<{
      billing_metric: 'llm_input_tokens' | 'llm_cache_tokens' | 'llm_output_tokens' | 'tts_request_count' | 'tts_output_chars' | 'tts_input_chars';
      raw_amount: number;
      unit_size: number;
      credits_per_unit: number;
      rounding_mode: 'ceil' | 'floor' | 'round';
      consumed_credits: number;
    }>;
  };
  created_at: string;
};

type CreatorBillingOverview = {
  creator_bid: string;
  wallet: {
    available_credits: number;
    reserved_credits: number;
    lifetime_granted_credits: number;
    lifetime_consumed_credits: number;
  };
  subscription: BillingSubscription | null;
  billing_alerts: Array<{
    code: string;
    severity: 'info' | 'warning' | 'error';
    message_key: string;
    message_params?: Record<string, string | number>;
    action_type?: 'checkout_topup' | 'resume_subscription' | 'open_orders';
    action_payload?: Record<string, string | number>;
  }>;
};

type BillingCheckoutResult = {
  bill_order_bid: string;
  provider: 'stripe' | 'pingxx';
  payment_mode: 'subscription' | 'one_time';
  status: 'init' | 'pending' | 'paid' | 'failed' | 'unsupported';
  redirect_url?: string;
  checkout_session_id?: string;
  payment_payload?: Record<string, unknown>;
};

type BillingEntitlements = {
  branding_enabled: boolean;
  custom_domain_enabled: boolean;
  priority_class: 'standard' | 'priority' | 'vip';
  analytics_tier: 'basic' | 'advanced' | 'enterprise';
  support_tier: 'self_serve' | 'business_hours' | 'priority';
};

type CreatorBrandingConfig = {
  logo_wide_url: string | null;
  logo_square_url: string | null;
  favicon_url: string | null;
  home_url: string | null;
};
```

## 9. 测试与上线关注点

### 9.1 当前批次（Figma `方案1` + 可联调 MVP）必测

- `/admin` 是否按 Figma `方案1` 浅色稿补齐会员卡和 `会员与积分` 导航
- `/admin/billing` 三个 tab 是否能按真实接口加载和切换
- `GET /billing/overview` 是否同时满足 sidebar 会员卡和 Billing Center summary
- Stripe 套餐 checkout、Stripe topup checkout 成功后，`bill_orders`、`bill_subscriptions`、`credit_wallets`、`credit_wallet_buckets`、`credit_ledger_entries` 是否同步更新
- Pingxx topup 与 subscription_start / renewal order 是否可正常 checkout / sync / webhook，并保持周期推进与 grant 幂等
- `POST /billing/orders/{bill_order_bid}/sync` 和 webhook 重复调用时，是否不会重复 grant 积分
- 继续复用 `/api/order/stripe/webhook`、`/api/callback/pingxx-callback` 后，billing 分流和 legacy `/order` 支付回调是否都通过 route 级回归
- `GET /billing/wallet-buckets`、`GET /billing/ledger`、`GET /billing/orders` 的排序、分页和 DTO 字段是否与前端类型一致
- `/payment/stripe/billing-result` 是否先 sync 再回跳 `/admin/billing`
- 旧 `/admin/orders`、`/admin/dashboard` 与学员 `/payment/stripe/result` 是否未回归

### 9.2 v1 完整目标必测

- 套餐购买、充值包购买、自动续费、失败重试、取消自动续费、恢复订阅
- `production` / `preview` / `debug` 三场景 creator 归属是否正确
- 多个学生并发学习同一 creator 课程时，Celery 串行扣减是否仍然准确
- `free > subscription > topup` 的 bucket 扣减优先级是否严格生效
- 同一 bucket category 下是否按最早到期优先、再按最早创建优先
- 一条 usage 超过单个 bucket 余额时，是否能拆分扣减多个 bucket，并在单条 usage consume ledger 的 `metadata.bucket_breakdown[]` 中保留可追溯明细
- LLM `input/cache/output` 三维扣分是否准确
- TTS `按次` 与 `按字数` 两种 metric 是否准确
- webhook 幂等、乱序到达、sync 补偿、防重复发放或重复扣分
- 最近一次 provider 摘要是否只覆盖写入关联 `bill_orders.metadata`，同时同步更新 provider raw snapshot
- 找不到关联订单的 webhook 是否按 ignore 处理且不落库存档
- bucket 过期后是否停止参与 admission / settlement，并生成 `expire` ledger
- `credit_wallets`、`credit_wallet_buckets` 与 `credit_ledger_entries` 三者是否保持一致
- 旧 `/order` 学员购课流程是否未被破坏
- `CELERY_TASK_ALWAYS_EAGER=1` 时 billing 集成测试可同步执行
- worker 不运行时，系统能输出明确告警或降级行为，而不是静默漏任务

### 9.3 v1.1 必测

- 权益快照是否随套餐变化正确生效
- 自定义域名绑定、校验、停用流程
- usage 日报表和 ledger 日报表是否可 rebuild 且能对齐真相源

### 9.4 主要风险

- 国内通道不提供 provider-managed recurring 时，平台自管 renewal order、补单继续支付与订阅过期切换是否仍保持一致
- provider webhook 乱序或重复回调导致的状态覆盖问题
- 费率 wildcard fallback 配置错误导致的错误扣分
- 报表层聚合与真相源不一致时的 rebuild 成本

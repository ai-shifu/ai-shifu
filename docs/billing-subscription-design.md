# Billing 设计文档

更新日期：2026-04-02

## 1. 文档目标

### 1.1 v1 核心计费目标

v1 只解决最小可上线的 creator billing 闭环：

- 创作者购买套餐和充值包
- 套餐自动续费
- 学员 `production`、作者 `preview`、作者 `debug` 三类场景统一扣创作者积分
- LLM 按 `input/cache/output` 三维扣分
- TTS 同时支持 `按次` 和 `按字数` 两种费率模型
- 支付、订阅、钱包、账本、费率、续费排期形成完整真相源

### 1.2 v1.1 扩展目标

v1.1 再补充下列扩展能力：

- 创作者权益快照
- 自定义域名绑定
- 按天 usage/ledger 报表聚合
- 基于权益的 branding、domain、analytics、priority、concurrency 扩展输出

### 1.3 本文冻结的关键决策

- 计费主体固定为 `creator_bid`
- 课程学习、预览、调试的 LLM/TTS 消耗都由课程所属创作者承担
- 商品目录统一使用 `billing_products` 单表，API 仍按 `plans[]` / `topups[]` 投影
- 支付持久化统一使用 `billing_orders` + `billing_provider_events`
- 钱包快照与账本真相源分离：`billing_wallets` 只做余额快照，`billing_ledger_entries` 才是不可变真相源
- `bill_usage + billing_ledger_entries` 是结算真相源；日报表只是报表层聚合，不参与扣费真相判断
- 旧的学员购课 `/order` 流程继续保留，不与 creator billing 混表

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
| `7101` | `llm_input_tokens` |
| `7102` | `llm_cache_tokens` |
| `7103` | `llm_output_tokens` |
| `7104` | `tts_request_count` |
| `7105` | `tts_output_chars` |
| `7106` | `tts_input_chars`，保留给后续特殊 provider 合同 |

#### 2.2.5 类型与存储约定

- 所有业务 ID 统一使用 `String(36)`，命名为 `*_bid`
- 所有状态、类型、场景、metric 字段统一使用 `SmallInteger` 编码，不在库里直接存英文状态串
- 金额统一使用 `BIGINT` 保存最小货币单位，例如分
- 积分统一使用 `BIGINT`
- provider、model、reference id 等短文本按现有仓库风格使用 `String(32/64/100/255)`
- 扩展载荷优先 `JSON`，仅在 provider 原始对象体积或兼容性要求下退回 `Text`

## 3. v1 核心表

### 3.1 `billing_products`

角色：目录真相源；不是账务真相源；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `product_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Billing product business identifier` | 商品业务 ID |
| `product_code` | `String(64)` | `not null, default="", unique=True` | 稳定编码，用于配置和对外联调 | `Billing product code` | 商品稳定编码 |
| `product_type` | `SmallInteger` | `not null, index=True` | `7111=plan; 7112=topup; 7113=grant; 7114=custom` | `Billing product type code` | 商品类型编码 |
| `billing_mode` | `SmallInteger` | `not null` | `7121=recurring; 7122=one_time; 7123=manual` | `Billing mode code` | 计费模式编码 |
| `billing_interval` | `SmallInteger` | `not null, default=0` | `7131=none; 7132=month; 7133=year` | `Billing interval code` | 套餐周期编码 |
| `billing_interval_count` | `Integer` | `not null, default=0` | 周期倍数，月套餐常见为 `1` | `Billing interval count` | 周期倍数 |
| `display_name_i18n_key` | `String(128)` | `not null, default=""` | i18n key | `Display name i18n key` | 展示名称翻译 key |
| `description_i18n_key` | `String(128)` | `not null, default=""` | i18n key | `Description i18n key` | 描述翻译 key |
| `currency` | `String(16)` | `not null, default="CNY"` | ISO 4217，例如 `CNY`/`USD` | `Currency code` | 货币编码 |
| `price_amount` | `BIGINT` | `not null, default=0` | 最小货币单位 | `Product price amount` | 商品价格 |
| `credit_amount` | `BIGINT` | `not null, default=0` | 发放积分数量 | `Credit amount` | 商品附带积分数 |
| `allocation_interval` | `SmallInteger` | `not null, default=7141` | `7141=per_cycle; 7142=one_time; 7143=manual` | `Credit allocation interval code` | 积分发放节奏 |
| `auto_renew_enabled` | `SmallInteger` | `not null, default=0` | `0=no; 1=yes` | `Auto renew enabled flag` | 是否允许自动续费 |
| `entitlement_payload` | `JSON` | `nullable=True` | v1 可留空，v1.1 用于权益扩展 | `Entitlement payload` | 权益扩展载荷 |
| `metadata` | `JSON` | `nullable=True` | 自定义展示、运营标记等 | `Billing product metadata` | 商品扩展元数据 |
| `status` | `SmallInteger` | `not null, default=7151, index=True` | `7151=active; 7152=inactive` | `Billing product status code` | 商品状态 |
| `sort_order` | `Integer` | `not null, default=0` | 列表排序，越小越靠前 | `Sort order` | 排序值 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 唯一索引：`product_code`
- 关键索引：`product_bid`、`product_type + status`

与其他表关系：

- `billing_subscriptions.product_bid`
- `billing_subscriptions.next_product_bid`
- `billing_orders.product_bid`

本表职责与边界：

- 统一承载套餐、充值包、赠送包、定制包目录
- `product_type=plan` 才允许进入订阅流程
- `product_type=topup` 必须是一次性支付，不创建 subscription

### 3.2 `billing_subscriptions`

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
| `metadata` | `JSON` | `nullable=True` | provider 辅助字段、迁移兼容标记 | `Billing subscription metadata` | 订阅扩展元数据 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 建议唯一索引：`creator_bid + status in active-like set` 由业务约束保证同一创作者仅一个活跃主订阅
- 关键索引：`subscription_bid`、`creator_bid + status`

与其他表关系：

- 引用 `billing_products.product_bid`
- 被 `billing_orders.subscription_bid`、`billing_renewal_events.subscription_bid` 关联

本表职责与边界：

- 只表示套餐订阅合同，不表示一次性充值
- `cancel_scheduled` 表示当前周期仍有效，但未来不再自动续费
- `next_product_bid` 只用于未来生效的套餐切换，不立即替换 `product_bid`

### 3.3 `billing_orders`

角色：支付动作真相源；不是 webhook 真相源；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `billing_order_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Billing order business identifier` | 支付动作单业务 ID |
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
| `metadata` | `JSON` | `nullable=True` | provider 原始关键引用、return url、补偿标记 | `Billing order metadata` | 支付动作扩展元数据 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 关键索引：`billing_order_bid`、`creator_bid + status`、`provider_reference_id`

与其他表关系：

- 关联 `billing_products.product_bid`
- 关联 `billing_subscriptions.subscription_bid`
- 被 `billing_provider_events.billing_order_bid` 和 `billing_ledger_entries.source_bid` 使用

本表职责与边界：

- 一次 checkout、一笔续费、一笔 topup、一笔退款，各自对应一条 `billing_orders`
- v1 不引入 `payment_attempts` 子表；支付重试通过创建新的 `billing_orders` 完成
- `billing_orders` 记录的是业务支付状态，不负责 webhook 幂等

### 3.4 `billing_provider_events`

角色：provider 事件审计与幂等真相源；不是订单真相源；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `provider_event_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Billing provider event business identifier` | provider 事件业务 ID |
| `billing_order_bid` | `String(36)` | `not null, default="", index=True` | 关联支付动作单 | `Billing order business identifier` | 关联支付动作单 ID |
| `subscription_bid` | `String(36)` | `not null, default="", index=True` | 订阅事件可回填 | `Billing subscription business identifier` | 关联订阅 ID |
| `creator_bid` | `String(36)` | `not null, default="", index=True` | 创作者维度索引 | `Creator business identifier` | 创作者业务 ID |
| `payment_provider` | `String(32)` | `not null, default="", index=True` | `stripe` / `pingxx` | `Payment provider name` | 支付 provider |
| `provider_event_id` | `String(255)` | `not null, default=""` | provider 原始事件 ID | `Provider event identifier` | provider 事件 ID |
| `provider_reference_id` | `String(255)` | `not null, default="", index=True` | checkout/charge/invoice/subscription 等引用 | `Provider reference identifier` | provider 参考 ID |
| `event_type` | `String(64)` | `not null, default="", index=True` | 直接存 provider 事件名 | `Provider event type` | provider 事件类型 |
| `status` | `SmallInteger` | `not null, default=7321, index=True` | `7321=received; 7322=processed; 7323=ignored; 7324=failed` | `Provider event status code` | 事件处理状态 |
| `payload` | `JSON` | `nullable=True` | 原始 webhook / sync 响应体 | `Provider event payload` | provider 原始载荷 |
| `error_code` | `String(255)` | `not null, default=""` | 内部或 provider 错误码 | `Event error code` | 事件错误码 |
| `error_message` | `String(255)` | `not null, default=""` | 处理失败信息 | `Event error message` | 事件错误信息 |
| `processed_at` | `DateTime` | `nullable=True` | 成功或失败处理结束时间 | `Processed timestamp` | 处理完成时间 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 唯一索引：`payment_provider + provider_event_id`
- 关键索引：`provider_reference_id`、`billing_order_bid`

与其他表关系：

- 关联 `billing_orders.billing_order_bid`
- 关联 `billing_subscriptions.subscription_bid`

本表职责与边界：

- 负责 webhook 去重、重放、审计
- 该表不决定支付是否成功，支付真相仍以 `billing_orders.status` 为准

### 3.5 `billing_wallets`

角色：余额快照；不是扣费真相源；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `wallet_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Billing wallet business identifier` | 钱包业务 ID |
| `creator_bid` | `String(36)` | `not null, default="", unique=True` | 一创作者一钱包 | `Creator business identifier` | 创作者业务 ID |
| `available_credits` | `BIGINT` | `not null, default=0` | 当前可用积分 | `Available credits` | 可用积分 |
| `reserved_credits` | `BIGINT` | `not null, default=0` | hold 后冻结积分 | `Reserved credits` | 冻结积分 |
| `lifetime_granted_credits` | `BIGINT` | `not null, default=0` | 累计发放积分 | `Lifetime granted credits` | 累计发放积分 |
| `lifetime_consumed_credits` | `BIGINT` | `not null, default=0` | 累计消耗积分 | `Lifetime consumed credits` | 累计消耗积分 |
| `last_settled_usage_id` | `BIGINT` | `not null, default=0, index=True` | 最近结算到的 `bill_usage.id` | `Last settled usage record id` | 最近已结算 usage 主键 |
| `version` | `Integer` | `not null, default=0` | 乐观锁版本号 | `Wallet version` | 钱包版本号 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 唯一索引：`creator_bid`
- 关键索引：`wallet_bid`、`last_settled_usage_id`

与其他表关系：

- 被 `billing_ledger_entries.wallet_bid` 关联

本表职责与边界：

- 仅做余额快照和快速读模型
- 钱包数值必须由账本结果推导和更新，禁止直接手改余额

### 3.6 `billing_ledger_entries`

角色：积分账本真相源；不是快照；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `ledger_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Billing ledger business identifier` | 账本业务 ID |
| `creator_bid` | `String(36)` | `not null, default="", index=True` | 所属创作者 | `Creator business identifier` | 创作者业务 ID |
| `wallet_bid` | `String(36)` | `not null, default="", index=True` | 归属钱包 | `Billing wallet business identifier` | 钱包业务 ID |
| `entry_type` | `SmallInteger` | `not null, index=True` | `7401=grant; 7402=consume; 7403=refund; 7404=expire; 7405=adjustment; 7406=hold; 7407=release` | `Billing ledger entry type code` | 账本分录类型 |
| `source_type` | `SmallInteger` | `not null, index=True` | `7411=subscription; 7412=topup; 7413=gift; 7414=usage; 7415=refund; 7416=manual` | `Billing ledger source type code` | 分录来源类型 |
| `source_bid` | `String(36)` | `not null, default="", index=True` | 对应业务单号，如 order/subscription/usage | `Ledger source business identifier` | 来源业务 ID |
| `idempotency_key` | `String(128)` | `not null, default="", index=True` | 统一幂等键；usage 扣分需带 metric 维度 | `Ledger idempotency key` | 分录幂等键 |
| `amount` | `BIGINT` | `not null, default=0` | 正数增加可用余额，负数减少可用余额 | `Ledger amount` | 分录金额 |
| `balance_after` | `BIGINT` | `not null, default=0` | 写入后可用余额快照 | `Balance after entry` | 分录后余额 |
| `expires_at` | `DateTime` | `nullable=True, index=True` | 仅 grant 类分录会有到期时间 | `Entry expiration timestamp` | 积分到期时间 |
| `consumable_from` | `DateTime` | `nullable=True` | 仅需延迟可用时使用 | `Consumable from timestamp` | 开始可消费时间 |
| `metadata` | `JSON` | `nullable=True` | 必须支持 `usage_bid`、`usage_scene`、`provider`、`model`、`metric_breakdown[]` | `Billing ledger metadata` | 分录元数据 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 关键索引：`ledger_bid`、`creator_bid + created_at`、`source_type + source_bid`
- 建议唯一约束：`creator_bid + idempotency_key`，由业务侧生成稳定幂等 key，避免重复入账

与其他表关系：

- 关联 `billing_wallets.wallet_bid`
- `source_bid` 可对应 `billing_orders`、`billing_subscriptions` 或 `bill_usage.usage_bid`

本表职责与边界：

- 所有发放、扣减、退款、过期、人工调整都必须落账
- usage 扣分分录的 `idempotency_key` 应为 `usage_bid + billing_metric + entry_type`
- 非 usage 分录由业务侧生成稳定幂等键，如 `billing_order_bid + entry_type`
- `metadata.metric_breakdown[]` 用于保存 LLM 三维或 TTS metric 的细分扣分来源

### 3.7 `billing_usage_rates`

角色：费率真相源；不是账本；不是报表表。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `rate_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Billing usage rate business identifier` | 费率业务 ID |
| `usage_type` | `SmallInteger` | `not null, index=True` | `1101=LLM; 1102=TTS` | `Usage type code` | usage 类型 |
| `provider` | `String(32)` | `not null, default="", index=True` | provider 名称，可允许 `*` 作为 wildcard | `Provider name` | provider |
| `model` | `String(100)` | `not null, default="", index=True` | model 名称，可允许 `*` 作为 wildcard | `Provider model` | 模型名 |
| `usage_scene` | `SmallInteger` | `not null, index=True` | `1201=debug; 1202=preview; 1203=production` | `Usage scene code` | 场景编码 |
| `billing_metric` | `SmallInteger` | `not null, index=True` | `7101=llm_input_tokens; 7102=llm_cache_tokens; 7103=llm_output_tokens; 7104=tts_request_count; 7105=tts_output_chars; 7106=tts_input_chars` | `Billing metric code` | 计费 metric |
| `unit_size` | `Integer` | `not null, default=1` | 计费单位分母，如 `1000 tokens` | `Billing unit size` | 费率分母 |
| `credits_per_unit` | `BIGINT` | `not null, default=0` | 每个计费单位对应积分 | `Credits per unit` | 单位积分消耗 |
| `rounding_mode` | `SmallInteger` | `not null, default=7421` | `7421=ceil; 7422=floor; 7423=round` | `Rounding mode code` | 取整模式 |
| `effective_from` | `DateTime` | `not null, index=True` | 生效开始时间 | `Effective from timestamp` | 生效开始时间 |
| `effective_to` | `DateTime` | `nullable=True, index=True` | 生效结束时间 | `Effective to timestamp` | 生效结束时间 |
| `status` | `SmallInteger` | `not null, default=7151, index=True` | `7151=active; 7152=inactive` | `Billing usage rate status code` | 费率状态 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 关键索引：`usage_type + provider + model + usage_scene + billing_metric + effective_from`

与其他表关系：

- 结算时与 `bill_usage` 联合匹配
- 结算结果写入 `billing_ledger_entries`

本表职责与边界：

- LLM 默认要求同一 provider/model/scene 至少配置三条 metric：`7101/7102/7103`
- TTS 默认只启用一种主 metric：`7104` 或 `7105`
- 如果找不到精确 model，可按 `model="*"` 或 `provider="*"` fallback

### 3.8 `billing_renewal_events`

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
- 关键索引：`subscription_bid + event_type + scheduled_at`、`status + scheduled_at`

与其他表关系：

- 关联 `billing_subscriptions.subscription_bid`
- 成功执行后通常会生成新的 `billing_orders`

本表职责与边界：

- 负责续费、失败重试、周期结束取消、未来降级和 reconcile 排期
- Worker 必须依赖 `status` 做幂等抢占，不允许同一排期被并发重复执行

## 4. v1.1 扩展表

### 4.1 `billing_entitlements`

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
| `max_concurrency` | `Integer` | `not null, default=1` | 允许并发上限 | `Max concurrency` | 并发上限 |
| `analytics_tier` | `SmallInteger` | `not null, default=7711` | `7711=basic; 7712=advanced; 7713=enterprise` | `Analytics tier code` | 分析能力等级 |
| `support_tier` | `SmallInteger` | `not null, default=7721` | `7721=self_serve; 7722=business_hours; 7723=priority` | `Support tier code` | 支持等级 |
| `feature_payload` | `JSON` | `nullable=True` | 细粒度 feature 开关 | `Entitlement feature payload` | 权益扩展载荷 |
| `effective_from` | `DateTime` | `not null, index=True` | 生效开始 | `Effective from timestamp` | 生效开始时间 |
| `effective_to` | `DateTime` | `nullable=True, index=True` | 生效结束 | `Effective to timestamp` | 生效结束时间 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 关键索引：`creator_bid + effective_to`、`source_type + source_bid`

与其他表关系：

- 来源于 `billing_products` 的 entitlement payload 或后台人工调整

本表职责与边界：

- 只在 v1.1 引入
- 如果 v1 只做计费闭环，可直接由套餐商品推导默认权益而不落这张表

### 4.2 `billing_domain_bindings`

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

- 与 `billing_entitlements` 联动，只有启用自定义域名权益的 creator 才允许生效

本表职责与边界：

- 只在 v1.1 引入
- v1 阶段不应让主链路依赖它

### 4.3 `billing_daily_usage_metrics`

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
| `billing_metric` | `SmallInteger` | `not null, index=True` | 见 `7101-7106` | `Billing metric code` | 计费 metric |
| `raw_amount` | `BIGINT` | `not null, default=0` | 原始用量汇总 | `Raw amount` | 原始用量 |
| `record_count` | `BIGINT` | `not null, default=0` | usage 记录数 | `Record count` | 记录条数 |
| `consumed_credits` | `BIGINT` | `not null, default=0` | 当天扣除积分汇总 | `Consumed credits` | 消耗积分 |
| `window_started_at` | `DateTime` | `not null` | 聚合窗口开始 | `Window start timestamp` | 聚合窗口开始时间 |
| `window_ended_at` | `DateTime` | `not null` | 聚合窗口结束 | `Window end timestamp` | 聚合窗口结束时间 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 建议唯一索引：`stat_date + creator_bid + shifu_bid + usage_scene + usage_type + provider + model + billing_metric`

与其他表关系：

- 从 `bill_usage` 和 `billing_ledger_entries` 增量汇总而来

本表职责与边界：

- 只用于 dashboard、运营分析和快查
- 如与账本不一致，以账本和原始 usage 为准并触发 rebuild

### 4.4 `billing_daily_ledger_summary`

角色：账本日报表聚合；只用于报表；v1.1 才引入。

| 字段名 | SQL/ORM 类型 | 约束/默认值/索引 | 状态/类型说明 | DB Comment(English) | 说明(中文) |
| --- | --- | --- | --- | --- | --- |
| `daily_ledger_summary_bid` | `String(36)` | `not null, default="", index=True` | 业务 ID | `Daily ledger summary business identifier` | 账本日摘要业务 ID |
| `stat_date` | `String(10)` | `not null, default="", index=True` | `YYYY-MM-DD` | `Statistic date` | 统计日期 |
| `creator_bid` | `String(36)` | `not null, default="", index=True` | 创作者维度 | `Creator business identifier` | 创作者业务 ID |
| `entry_type` | `SmallInteger` | `not null, index=True` | `7401=grant; 7402=consume; 7403=refund; 7404=expire; 7405=adjustment; 7406=hold; 7407=release` | `Billing ledger entry type code` | 分录类型 |
| `source_type` | `SmallInteger` | `not null, index=True` | `7411=subscription; 7412=topup; 7413=gift; 7414=usage; 7415=refund; 7416=manual` | `Billing ledger source type code` | 来源类型 |
| `amount` | `BIGINT` | `not null, default=0` | 当天同类分录金额汇总 | `Ledger amount total` | 汇总金额 |
| `entry_count` | `BIGINT` | `not null, default=0` | 当天同类分录条数 | `Ledger entry count` | 分录条数 |
| `window_started_at` | `DateTime` | `not null` | 聚合窗口开始 | `Window start timestamp` | 聚合窗口开始时间 |
| `window_ended_at` | `DateTime` | `not null` | 聚合窗口结束 | `Window end timestamp` | 聚合窗口结束时间 |

主键 / 唯一索引 / 关键索引：

- 主键：`id`
- 建议唯一索引：`stat_date + creator_bid + entry_type + source_type`

与其他表关系：

- 从 `billing_ledger_entries` 增量汇总而来

本表职责与边界：

- 只用于后台统计和账务报表
- 如与明细账本不一致，以 `billing_ledger_entries` 为准

## 5. 现有代码改造清单

### 5.1 支付与订单域

当前支付主流程位于 `src/api/flaskr/service/order/funs.py`，特点是：

- 面向学员购课，而不是 creator billing
- 通过 `order_orders`、`order_pingxx_orders`、`order_stripe_orders` 三张旧表落库
- Pingxx 和 Stripe 已有 shared adapter 抽象，但持久化仍是 provider-specific

v1 的改造要求：

- 旧 `/order` API 和旧订单表全部保留，不做迁移或重构
- 新 billing 不复用 `order_*` 表，只复用并扩展 `service/order/payment_providers/` 的 adapter 层
- billing 侧新增独立 `service/billing/` 代码层：
  - `models.py`
  - `consts.py`
  - `catalog.py`
  - `subscription.py`
  - `settlement.py`
  - `admission.py`
  - `routes.py`
  - `tasks.py`
  - `reconcile.py`
  - `renewal.py`

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
- `debug` 和 `preview` 在常量层被放进 `BILL_USAGE_SCENE_NON_BILLABLE`
- `record_llm_usage` / `record_tts_usage` 会根据 `usage_scene` 自动推导 `billable`

必须改造的点：

- 把 “`debug` / `preview` 一律 non-billable” 从 metering 常量中移除
- 改成 `production`、`preview`、`debug` 三种 scene 都允许计费
- 是否真正扣费不再由 metering 常量决定，而由 billing service 的 admission / settlement 规则决定
- `record_llm_usage` / `record_tts_usage` 继续只负责原始 usage 落库，不直接承担 creator 账务逻辑
- 结算层新增 `creator ownership resolver`，把 `shifu_bid -> creator_bid` 固化给 billing settlement 使用

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
- usage 落库成功后，由 settlement 消费 `bill_usage` 并写入 `billing_ledger_entries`
- v1 不承诺 creator 并发隔离；并发限制与 priority 统一放到 v1.1 的 entitlement/runtime enforcement

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

### 5.5 现有后台线程模式替换

当前仓库存在 ad-hoc 线程后台模式，例如 `src/api/flaskr/service/shifu/shifu_publish_funcs.py` 的 `threading.Thread(...)`。

v1 约束：

- billing 新增异步任务不允许继续沿用这种线程模式
- 续费、重试、对账、结算 replay、低余额提醒统一走 Celery
- 旧业务暂不强制迁移到 Celery，但 billing 域从第一版开始必须统一

## 6. Celery 接入与基础设施

### 6.1 接入目标

Celery 是 billing v1 必做基础设施，原因是 billing 至少需要：

- 周期续费
- 失败重试
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

### 6.3 Celery 配置

v1 需要补充以下环境变量和配置项：

| 配置项 | 用途 |
| --- | --- |
| `CELERY_BROKER_URL` | Redis broker 地址 |
| `CELERY_RESULT_BACKEND` | 结果后端，默认可与 broker 同源 Redis |
| `CELERY_TASK_ALWAYS_EAGER` | 测试环境同步执行任务 |
| `BILLING_RENEWAL_CRON` | 续费排期调度表达式 |
| `BILLING_RECONCILE_CRON` | provider reconcile 调度表达式 |
| `BILLING_LOW_BALANCE_CRON` | 低余额扫描调度表达式 |
| `BILLING_DAILY_AGGREGATE_CRON` | 日汇总调度表达式，v1.1 才启用 |

### 6.4 Worker / Beat 分工

- `celery-worker`
  - 执行 renewal、retry、reconcile、settlement replay、low balance alert
  - v1.1 再执行 domain verify、daily aggregate、rebuild
- `celery-beat`
  - 只负责调度任务
  - 不承载业务逻辑

### 6.5 v1 必做 Tasks

| Task Name | 作用 | 最小 payload |
| --- | --- | --- |
| `billing.run_renewal_event` | 执行一次续费排期事件 | `renewal_event_bid`, `subscription_bid`, `creator_bid` |
| `billing.retry_failed_renewal` | 对失败续费进行重试 | `renewal_event_bid`, `billing_order_bid`, `provider_reference_id` |
| `billing.reconcile_provider_reference` | 对账或补偿同步 provider 状态 | `payment_provider`, `provider_reference_id`, `billing_order_bid` |
| `billing.replay_usage_settlement` | 重放 usage 结算 | `creator_bid`, `usage_bid` 或 `usage_id_start/usage_id_end` |
| `billing.send_low_balance_alert` | 扫描并通知低余额 creator | `creator_bid` 或批量扫描窗口 |

### 6.6 v1.1 扩展 Tasks

| Task Name | 作用 | 最小 payload |
| --- | --- | --- |
| `billing.aggregate_daily_usage_metrics` | 生成 usage 日聚合 | `stat_date`, `creator_bid` 可选 |
| `billing.aggregate_daily_ledger_summary` | 生成 ledger 日聚合 | `stat_date`, `creator_bid` 可选 |
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

## 7. 结算、支付与接口

### 7.1 支付与订阅

- `GET /billing/catalog` 读取 `billing_products`，但 API 返回仍按 `plans[]` / `topups[]` 投影
- `POST /billing/subscriptions/checkout` 只能购买 `product_type=plan`
- `POST /billing/topups/checkout` 只能购买 `product_type=topup`
- `billing_orders` 是统一支付动作单；Stripe/Pingxx 业务编排一致，差异只放在 shared provider adapter
- `billing_provider_events` 负责 webhook 去重和重放，不单独引入 `payment_attempts`
- 自动续费和失败重试由 `billing_renewal_events` 驱动，成功后生成新的 `billing_orders`

### 7.2 扣分与结算

- 学员正式学习 `production`、作者 `preview`、作者 `debug` 统一扣课程所属创作者积分
- LLM 一条 usage 默认按三条费率结算：
  - `7101=llm_input_tokens`
  - `7102=llm_cache_tokens`
  - `7103=llm_output_tokens`
- TTS 一条 usage 默认只命中一种主费率：
  - `7104=tts_request_count`
  - 或 `7105=tts_output_chars`
- 结算真相源为：
  - 原始 usage：`bill_usage`
  - 积分真相：`billing_ledger_entries`
  - 余额快照：`billing_wallets`
- 结算幂等 key 应以 `bill_usage.usage_bid + billing_metric` 为核心，避免重复扣分

### 7.3 现有接口如何改造

- 旧 `/order` 保持不变，只说明“不复用其表结构”
- 新 `/billing` 接口继续独立
- `/billing/webhooks/stripe`、`/billing/webhooks/pingxx` 统一通过 shared provider adapter 解析，再更新 billing 域状态
- `/api/config` 在 v1 继续保持全局配置输出，不承载 creator-scoped branding

### 7.4 内部支付接口契约

```ts
interface BillingPaymentProviderAdapter {
  create_checkout(input: {
    billing_order_bid: string;
    creator_bid: string;
    product_bid: string;
    payment_provider: string;
    channel: string;
    success_url?: string;
    cancel_url?: string;
  }): Promise<ProviderCheckoutResult>;

  create_recurring_subscription(input: {
    billing_order_bid: string;
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
    billing_order_bid: string;
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

### 7.5 前端实现方案

当前前端的已知事实：

- App Router 入口集中在 `src/cook-web/src/app/`
- 接口定义集中在 `src/cook-web/src/api/api.ts`
- 请求封装集中在 `src/cook-web/src/lib/request.ts`
- 运行时配置通过 `src/cook-web/src/lib/initializeEnvData.ts` 写入 `envStore`
- 管理端统一布局在 `src/cook-web/src/app/admin/layout.tsx`
- 现有订单管理页已经使用 `Table + Sheet + 本地状态/搜索参数` 的管理端交互模式

v1 前端不新建全局 billing store，默认采用：

- 读接口：SWR
- 写接口：统一 `api` 方法 + 成功后 `mutate`
- 页面局部状态：`useState`
- 公共类型：新增 `src/cook-web/src/types/billing.ts`

#### 7.5.1 v1 路由与页面结构

v1 采用单路由 Billing Center，避免一开始拆太多子页面。

- 新增 `src/cook-web/src/app/admin/billing/page.tsx`
- 在 `src/cook-web/src/app/admin/layout.tsx` 侧边栏新增 `Billing` 菜单
- Billing Center 使用 `Tabs` 拆成三个视图：
  - `Overview`
  - `Ledger`
  - `Orders`

页面职责：

- `Overview`
  - 读取 `GET /billing/overview`
  - 展示当前订阅、钱包余额、低余额/续费异常告警
  - 展示套餐目录和充值包目录
  - 承载升级、续费恢复、取消自动续费、购买充值包入口
- `Ledger`
  - 读取 `GET /billing/ledger`
  - 展示积分流水、来源类型、余额变化、时间筛选
- `Orders`
  - 读取 `GET /billing/orders`
  - 展示支付单、状态、provider、金额、失败信息
  - 通过 `GET /billing/orders/{billing_order_bid}` 打开详情抽屉

#### 7.5.2 v1 组件拆分

建议新增 `src/cook-web/src/components/billing/`，至少包含：

- `BillingAlertsBanner.tsx`
- `BillingOverviewCard.tsx`
- `BillingSubscriptionCard.tsx`
- `BillingCatalogCards.tsx`
- `BillingLedgerTable.tsx`
- `BillingOrdersTable.tsx`
- `BillingCheckoutDialog.tsx`
- `BillingOrderDetailSheet.tsx`

组件约束：

- 表格、抽屉、对话框统一复用现有 `ui` 组件
- 详情查看沿用现有订单页的 `Sheet` 交互，不使用新窗口跳转
- 购买动作统一在 dialog 中确认，再调用 checkout API

#### 7.5.3 API 接入与前端类型

需要在 `src/cook-web/src/api/api.ts` 增加：

- `getBillingCatalog`
- `getBillingOverview`
- `getBillingLedger`
- `getBillingOrders`
- `getBillingOrderDetail`
- `syncBillingOrder`
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
- `BillingLedgerItem`
- `BillingOrderSummary`
- `BillingOrderDetail`
- `CreatorBillingOverview`
- `BillingCheckoutPayload`

前端数据获取策略：

- `getBillingCatalog` 和 `getBillingOverview` 在 `Overview` tab 首屏并行请求
- `getBillingLedger` 和 `getBillingOrders` 在对应 tab 激活时懒加载
- 写操作成功后只刷新受影响的 SWR key，不全页硬刷新

#### 7.5.4 Stripe 支付回跳

当前现有 Stripe 回跳页 `src/cook-web/src/app/payment/stripe/result/page.tsx` 是学员购课专用，成功后会跳到课程页，不适合 creator billing 直接复用。

v1 前端方案：

- 新增 `src/cook-web/src/app/payment/stripe/billing-result/page.tsx`
- billing checkout 的 `success_url` / `cancel_url` 指向新的 billing result 页
- billing result 页职责：
  - 从 query 读取 `billing_order_bid` / `session_id`
  - 先调用 `POST /billing/orders/{billing_order_bid}/sync`
  - 再读取 `GET /billing/orders/{billing_order_bid}` 或 `GET /billing/overview` 刷新状态
  - 成功后跳回 `/admin/billing`
  - 待支付或失败时展示明确状态和重试入口

#### 7.5.5 v1.1 前端扩展

v1.1 继续沿用 `/admin/billing`，在同一路由上增加扩展 tab：

- `Entitlements`
- `Domains`
- `Reports`

页面职责：

- `Entitlements`
  - 展示当前权益快照、并发等级、优先级、分析等级、支持等级
- `Domains`
  - 展示域名绑定状态、校验 token、最近校验时间、证书状态
  - 发起域名绑定和重试校验
- `Reports`
  - 展示 usage 日汇总和 ledger 日汇总

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
- `GET /billing/ledger`
- `GET /billing/orders`
- `GET /billing/orders/{billing_order_bid}`
- `POST /billing/orders/{billing_order_bid}/sync`
- `POST /billing/subscriptions/checkout`
- `POST /billing/subscriptions/cancel`
- `POST /billing/subscriptions/resume`
- `POST /billing/topups/checkout`
- `POST /billing/webhooks/stripe`
- `POST /billing/webhooks/pingxx`
- `GET /admin/billing/subscriptions`
- `GET /admin/billing/orders`
- `POST /admin/billing/ledger/adjust`

核心接口说明：

- `GET /billing/catalog`：读取 `billing_products`，输出 `plans[]` 与 `topups[]`
- `GET /billing/overview`：v1 只返回 `wallet`、`subscription`、`billing_alerts`，告警允许实时计算返回
- `GET /billing/ledger`：按时间倒序分页返回账本流水
- `GET /billing/orders`：creator 自助查看自己的 billing 订单列表
- `GET /billing/orders/{billing_order_bid}`：creator 查看单笔 billing 订单详情
- `POST /billing/orders/{billing_order_bid}/sync`：按 `billing_order_bid` 和 provider reference 主动同步支付状态
- `POST /billing/subscriptions/checkout`：新开订阅、升级补差或恢复订阅
- `POST /billing/topups/checkout`：发起一次性充值支付
- `POST /billing/webhooks/stripe` / `POST /billing/webhooks/pingxx`：负责 `billing_provider_events` 幂等、`billing_orders` 状态推进、`billing_subscriptions` 推进和账本发放/扣回
- `GET /admin/billing/orders`：后台运营侧查询 creator billing 订单
- `POST /admin/billing/ledger/adjust`：后台人工调整积分，必须写入 `billing_ledger_entries`

### 8.2 v1.1 扩展 API

- `POST /admin/billing/domains/bind`
- `GET /admin/billing/domain-bindings`
- `GET /billing/entitlements`

扩展接口说明：

- `POST /admin/billing/domains/bind`：发起域名绑定和校验
- `GET /admin/billing/domain-bindings`：查看 creator 维度域名状态
- `GET /billing/entitlements`：读取 v1.1 扩展权益快照

### 8.3 DTO 投影

说明：

- `BillingPlan` 和 `BillingTopupProduct` 是 `billing_products` 的展示层投影，不是底层独立表
- v1 的 `CreatorBillingOverview` 只返回钱包、订阅和告警
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
  billing_interval: 'month' | 'year';
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

type BillingLedgerItem = {
  ledger_bid: string;
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

type BillingEntitlements = {
  branding_enabled: boolean;
  custom_domain_enabled: boolean;
  priority_class: 'standard' | 'priority' | 'vip';
  max_concurrency: number;
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

### 9.1 v1 必测

- 套餐购买、充值包购买、自动续费、失败重试、取消自动续费、恢复订阅
- `production` / `preview` / `debug` 三场景 creator 归属是否正确
- LLM `input/cache/output` 三维扣分是否准确
- TTS `按次` 与 `按字数` 两种 metric 是否准确
- webhook 幂等、replay、防重复发放或重复扣分
- 钱包快照与账本明细的一致性
- 旧 `/order` 学员购课流程是否未被破坏
- `CELERY_TASK_ALWAYS_EAGER=1` 时 billing 集成测试可同步执行
- worker 不运行时，系统能输出明确告警或降级行为，而不是静默漏任务

### 9.2 v1.1 必测

- 权益快照是否随套餐变化正确生效
- 自定义域名绑定、校验、停用流程
- usage 日报表和 ledger 日报表是否可 rebuild 且能对齐真相源

### 9.3 主要风险

- 国内通道是否支持真实 recurring；若不支持，必须显式返回 `unsupported`
- provider webhook 乱序或重复回调导致的状态覆盖问题
- 费率 wildcard fallback 配置错误导致的错误扣分
- 报表层聚合与真相源不一致时的 rebuild 成本

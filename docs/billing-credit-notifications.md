# 积分通知中心需求文档

更新时间：2026-05-20

## 目标

建立一份统一的创作者积分通知需求文档，避免积分提醒逻辑散落在验证码短信、人工发放、钱包查询或结算路径里。

v1 首个触达渠道是短信。但产品模型应按“通知中心”设计，使后续站内信、邮件、飞书等渠道可以复用同一套触发、去重、状态和运营审核规则。

本文档只描述需求，不直接引入 API、数据库表、任务、配置或前端类型变更。

## 现有参考

- `docs/billing-subscription-purchase-sms.md` 定义了当前 billing 异步短信模式：业务事实落库时记录通知意图，事务提交后入队，由 worker 调用供应商发送。
- `docs/operator-user-points-grant.md` 定义了人工积分发放语义，包括 `reward` 和 `compensation`。
- `docs/billing-subscription-design.md` 定义了钱包、余额桶、账本、余额桶过期和低余额提醒边界。

## 通知场景

### `credit_expiring`

在有效积分即将过期前通知创作者。

- 真相源：`credit_wallet_buckets`。
- 来源 ID：`wallet_bucket_bid`。
- 触发方式：定时扫描 active bucket，筛选 `effective_to` 落入配置提醒窗口的记录。
- v1 建议提醒窗口：`7d`、`3d`、`1d`、`0d`。
- 去重键：`credit_expiring:{wallet_bucket_bid}:{window}`。
- 内容变量：即将过期积分、过期时间、充值或订阅操作入口。
- 同一创作者在同一提醒窗口内有多个 bucket 到期时，应尽量合并成一条用户可见通知。

### `credit_granted`

积分成功发放后通知创作者。

- 真相源：`credit_ledger_entries`。
- 来源 ID：`ledger_bid`。
- 触发方式：grant ledger 和匹配 bucket 提交成功后，由事件触发。
- 覆盖发放来源：试用、付费套餐或充值包到账、人工奖励、人工补偿，以及未来活动发放。
- 去重键：`credit_granted:{ledger_bid}`。
- 内容变量：到账积分、发放来源标签、可用时的过期时间、积分详情或 billing 入口。
- 重复发放请求如果复用了既有 ledger，不得再次发送提醒。

### `low_balance`

可用积分较低时通知创作者。

- 真相源：`credit_wallets` 加当前可消费 bucket 状态。
- 来源 ID：`creator_bid`。
- 触发方式：定时扫描创作者钱包和 billing overview alert。
- 当前 billing v1 的低余额规则是 `available_credits <= BILL_LOW_BALANCE_THRESHOLD`，bootstrap 阈值为 `0`。
- 未来产品规则可以增加固定积分数、百分比或预计可用天数等阈值，但必须显式配置。
- 去重键：`low_balance:{creator_bid}:{threshold}:{date}`。
- 内容变量：当前可用积分、阈值标签、checkout 或订阅操作入口。

## 触发规则

- 事件触发型通知只能在业务状态提交成功后创建。v1 主要适用于 `credit_granted`。
- 扫描触发型通知由定时 worker 生成。v1 适用于 `credit_expiring` 和 `low_balance`。
- 路由 handler 不得直接发送短信。
- 支付供应商 adapter、验证码 helper、钱包只读 API 不应承载积分通知业务规则。
- 供应商失败可以重试。无手机号、退订、黑名单、重复抑制等跳过状态默认为终态，除非运营策略明确改变。

## 接收人规则

- 默认接收人是积分被发放、即将过期或低余额的创作者。
- 手机号从创作者用户账号资料中解析。
- 手机号标识必须沿用 auth 和用户查询流程里的统一规范化规则。
- 创作者没有可用手机号时，通知状态标记为 `skipped_no_mobile`。
- 创作者已退订、在黑名单中，或被运营策略禁发时，通知状态标记为跳过，不调用短信供应商。
- 国际化和时区格式化应优先使用用户语言和应用时区。

## 通知状态

每次通知尝试都应有持久状态记录，或等价的 metadata 记录，至少包含：

- 通知类型：`credit_expiring`、`credit_granted` 或 `low_balance`
- 触达渠道：v1 使用 `sms`
- creator BID 和目标 user BID
- 本次发送使用的手机号快照
- 来源类型和来源 ID
- 去重键
- 状态
- 请求、发送、更新时间
- 供应商响应摘要和错误码

必须支持的状态：

- `pending`：通知意图已创建，可以被处理
- `sent`：短信供应商已接受发送请求
- `skipped_no_mobile`：没有可用的接收手机号
- `skipped_opt_out`：接收人或运营策略阻止发送
- `suppressed_duplicate`：同一去重键已有已处理通知
- `failed_provider`：短信供应商失败，通知可以重试

## 运营后台需求

v1 需要一个只读为主的运营管理面：

- 按创作者、手机号、通知类型、渠道、状态、来源 ID、时间范围查询通知记录。
- 查看失败通知的供应商响应和错误码。
- 对 `failed_provider` 状态的通知执行重新入队。
- 查看通知被跳过的原因。
- 配置每类通知的启用状态、短信模板、提醒窗口和低余额阈值。
- 启用扫描型通知策略前，可以先 dry-run 统计预计触达人群数量。

运营操作不得修改 wallet、bucket 或 ledger 事实。重新入队只改变通知投递状态。

## 指标

按通知类型和渠道统计产品与运营指标：

- 生成通知数
- 发送成功数
- 供应商失败数
- 按原因分组的跳过数
- 重复抑制数
- 短信成本估算
- 通知后的转化，例如登录、checkout、充值、续费、课程创建或继续消耗积分

指标只用于报表分析。积分余额和消耗真相仍以 billing ledger 和 bucket 表为准。

## 边界

- 积分通知不负责发放、消耗、过期或调整积分。
- 积分事实仍以 `credit_ledger_entries`、`credit_wallet_buckets` 和 `credit_wallets` 为准。
- 余额桶过期仍由 `billing.expire_wallet_buckets` 负责。
- 低余额检测仍属于 billing 范畴，不应新增 runtime admission 错误码。
- 不复用 `/api/user/send_sms_code`、`/api/user/console_send_sms_code` 或验证码短信模板发送积分通知。
- 来源 billing 事实提交前，不得发送通知短信。

## 验收标准

- 三类 v1 通知类型均明确了触发真相源、来源 ID 和去重键。
- 文档清楚区分通知投递和积分账本变更。
- 文档明确区分 auth 验证码短信和积分通知短信。
- 文档在需求层定义跳过、失败、重复和重试行为。
- 文档引用现有 billing 短信、人工发放、过期和低余额设计，但不宣称新能力已经实现。

# 积分通知中心技术设计

更新时间：2026-05-21

## 目标

本文档基于 `docs/billing-credit-notifications.md`，描述积分通知中心的后续实现设计。v1 只落地短信渠道，但数据模型、任务和运营后台按通知中心抽象设计，后续可以扩展站内信、邮件、飞书等渠道。

本设计只说明未来实现方案，不表示相关数据库表、任务、API 或前端页面已经存在。

## 设计原则

- 积分事实和通知事实分离。积分余额、发放、扣减、过期仍以 `credit_ledger_entries`、`credit_wallet_buckets`、`credit_wallets` 为准。
- 通知状态独立持久化，不复用 `BillingOrder.metadata`、验证码短信状态或钱包只读接口。
- 业务事实 commit 后才能创建或发送通知。路由 handler、支付 provider adapter 和验证码 helper 不直接发送积分通知短信。
- 通知规则由运营平台配置；账务幂等、hardlimit 和 runtime 阻断语义由 billing 代码固定实现。
- v1 渠道为 `sms`，但通知记录必须保留 `channel` 字段。

## 当前系统衔接点

- 现有支付成功短信位于 `src/api/flaskr/service/billing/notifications.py`，采用“业务事实落库后标记通知意图，commit 后 enqueue，worker 发送并落状态”的异步模式。
- 现有低余额扫描任务为 `billing.send_low_balance_alert`，位于 `src/api/flaskr/service/billing/tasks.py`，当前主要产出候选结果，后续应升级为生成通知记录并入队。
- 现有余额桶过期任务为 `billing.expire_wallet_buckets`，只负责过期账务处理，不负责发送到期提醒。
- 现有短信供应商入口为 `send_sms_ali`。积分通知不得复用 `/api/user/send_sms_code`、`/api/user/console_send_sms_code` 或验证码短信模板。
- 现有配置读取优先使用 `src/api/flaskr/service/config` 的 `get_config`，v1 运营策略可先放在 `sys_configs`。

## 数据模型

新增统一通知记录表，建议命名为 `notification_records`。

### 字段

| 字段 | 说明 |
| --- | --- |
| `notification_bid` | 通知记录业务 ID |
| `notification_type` | `credit_expiring`、`credit_granted`、`low_balance` |
| `channel` | v1 固定为 `sms` |
| `creator_bid` | 积分所属创作者 |
| `target_user_bid` | 实际接收通知的用户 |
| `mobile_snapshot` | 本次投递解析到的手机号快照 |
| `source_type` | 来源类型，例如 `wallet_bucket`、`ledger`、`wallet` |
| `source_bid` | 来源业务 ID |
| `dedupe_key` | 幂等键 |
| `status` | 通知状态 |
| `template_code` | 本次发送使用的短信模板 code 快照 |
| `template_params_json` | 本次发送使用的模板变量快照 |
| `policy_snapshot_json` | 本次命中的运营策略快照 |
| `provider_response_json` | 供应商响应摘要 |
| `error_code` | 失败错误码 |
| `error_message` | 失败说明 |
| `requested_at` | 通知意图创建时间 |
| `attempted_at` | 最近一次尝试发送时间 |
| `sent_at` | 供应商接受发送请求时间 |
| `created_at` / `updated_at` | 记录创建与更新时间 |
| `deleted` | 软删除标记 |

### 索引

- `dedupe_key` 唯一索引，防止重复通知。
- `notification_bid` 唯一索引。
- `(status, notification_type, created_at)`，支撑 worker 拉取和运营筛选。
- `(creator_bid, created_at)`，支撑按创作者查询。
- `(source_type, source_bid)`，支撑从账务来源回查通知。

### 状态

| 状态 | 含义 | 是否可重试 |
| --- | --- | --- |
| `pending` | 通知意图已创建，等待 worker 处理 | 是 |
| `sent` | 短信供应商已接受发送请求 | 否 |
| `skipped_no_mobile` | 没有可用手机号 | 否 |
| `skipped_opt_out` | 退订、黑名单、频控或运营策略阻止发送 | 否 |
| `suppressed_duplicate` | 同一幂等键已有记录 | 否 |
| `failed_provider` | 供应商调用失败 | 是 |

如果创建通知时发现 `dedupe_key` 已存在，实现可以直接返回既有记录；只有需要审计重复尝试时，才额外写入 `suppressed_duplicate` 记录。

## 运营策略配置

v1 新增 `sys_configs` 配置 key：

```text
BILL_CREDIT_NOTIFICATION_SMS_CONFIG
```

配置值以 JSON 存储，但这是后端和配置表的持久化格式。运营后台不得直接提供 raw JSON 编辑器；配置读写接口和前端页面都应把该策略呈现为结构化表单，并对模板 code、窗口、阈值、频控、名单和预算做字段级校验。

默认结构如下，默认只保留固定余额阈值，不改变现有发送范围：

```json
{
  "enabled": false,
  "channel": "sms",
  "types": {
    "credit_expiring": {
      "enabled": false,
      "template_code": "",
      "windows": ["7d", "3d", "1d", "0d"],
      "merge_same_creator": true
    },
    "credit_granted": {
      "enabled": false,
      "template_code": ""
    },
    "low_balance": {
      "enabled": false,
      "template_code": "",
      "thresholds": [
        {
          "kind": "fixed",
          "value": "0"
        }
      ]
    }
  },
  "softlimit": {
    "enabled": false,
    "threshold": {
      "kind": "fixed",
      "value": "0"
    },
    "teacher_page_alert": true,
    "disable_debug": true,
    "sms_enabled": false
  },
  "frequency": {
    "per_mobile_per_day": 3,
    "per_creator_per_type_per_day": 1
  },
  "quiet_hours": {
    "enabled": false,
    "start": "22:00",
    "end": "09:00",
    "timezone": "Asia/Shanghai"
  },
  "blacklist": {
    "creator_bids": [],
    "mobiles": []
  },
  "budget": {
    "daily_sms_limit": 0,
    "dry_run_required": true
  }
}
```

`types.low_balance.thresholds[]` 支持 union 配置。固定阈值继续使用：

```json
{ "kind": "fixed", "value": "3" }
```

按日消耗估算可用天数使用：

```json
{
  "kind": "estimated_days",
  "days": 7,
  "lookback_days": 7,
  "min_consumed_days": 2,
  "fallback_fixed_value": "0"
}
```

`softlimit.threshold` v1 仍只接受 `{ "kind": "fixed", "value": "..." }`，避免自动日消耗估算影响老师端调试禁用语义。

### 配置边界

运营平台可以配置：

- 每类通知的启用状态。
- 短信模板 code 和模板变量映射。
- 到期提醒窗口。
- 低余额固定阈值、按可用天数提醒参数，以及 softlimit 固定阈值。
- 频控、免打扰、黑名单、退订和预算。
- dry-run、审批和失败重发。

运营平台不能配置：

- 阿里云 AccessKey、Secret、签名等供应商密钥。
- 验证码短信模板。
- 积分发放、扣减、过期、hardlimit 判定和账务幂等。
- `dedupe_key` 生成规则。
- runtime admission 错误码。

## 后端模块设计

新增 billing 内部服务模块，建议命名为 `src/api/flaskr/service/billing/credit_notifications.py`，负责：

- 读取并校验 `BILL_CREDIT_NOTIFICATION_SMS_CONFIG`。
- 根据通知类型构造 `dedupe_key`。
- 幂等创建 `notification_records`。
- 解析接收人和手机号。
- 判断退订、黑名单、频控、免打扰和预算。
- 构造短信模板变量。
- 调用 `send_sms_ali` 并更新通知状态。
- 提供 dry-run 和 requeue 能力给运营后台使用。

### 核心方法

| 方法 | 说明 |
| --- | --- |
| `load_credit_notification_policy()` | 读取、合并默认值并校验运营策略 |
| `stage_credit_granted_notification(ledger_bid)` | 积分发放成功后创建到账提醒 |
| `scan_credit_expiring_notifications(now)` | 扫描即将过期 bucket 并创建提醒 |
| `scan_low_balance_notifications(now)` | 扫描低余额创作者并创建提醒 |
| `deliver_credit_notification(notification_bid)` | 发送单条通知并落状态 |
| `requeue_credit_notification(notification_bid)` | 将 `failed_provider` 重置为 `pending` 并入队 |
| `dry_run_credit_notifications(policy)` | 返回预计触达人群、跳过原因和成本估算 |
| `resolve_creator_limit_state(creator_bid)` | 返回 `normal`、`softlimit`、`hardlimit` 和 `debug_allowed` |

## 触发流程

### `credit_granted`

1. 试用、付费到账、人工奖励、人工补偿或活动发放成功写入 `credit_ledger_entries` 和相关 bucket。
2. 同一事务内或事务后置流程调用 `stage_credit_granted_notification(ledger_bid)`。
3. 生成 `dedupe_key = credit_granted:{ledger_bid}`。
4. 事务 commit 后 enqueue `billing.send_credit_notification`。
5. worker 加载通知记录，解析手机号并发送短信。

重复发放请求如果复用既有 ledger，不得创建新的到账提醒。

### `credit_expiring`

1. Celery 定时任务 `billing.scan_credit_expiring_notifications` 按配置窗口扫描 active bucket。
2. 对每个命中窗口生成 `dedupe_key = credit_expiring:{wallet_bucket_bid}:{window}`。
3. 同一创作者同一窗口内多个 bucket 可合并为一条用户可见通知，但每个来源仍需可审计。
4. 成功创建 `pending` 记录后 enqueue 发送任务。

余额桶真正过期仍由 `billing.expire_wallet_buckets` 负责，提醒任务不改变 bucket 状态。

### `low_balance`

1. Celery 定时任务 `billing.scan_low_balance_notifications` 扫描创作者钱包，并逐条评估 `fixed` 与 `estimated_days` 阈值。
2. 固定阈值命中条件为 `available_credits <= value`，生成 `dedupe_key = low_balance:{creator_bid}:{threshold}:{date}`。
3. 自动阈值使用 `bill_daily_ledger_summary` 中 `entry_type=consume` 的已结算日聚合，只统计扫描日期前的完整自然日，消耗额取 `amount` 绝对值。
4. 自动阈值先按 `lookback_days` 汇总日消耗，再按有效消耗天数计算平均日消耗；没有有效日消耗汇总或平均日消耗为 `0` 时跳过该自动规则，不触发兜底发送。
5. 自动阈值命中条件为 `available_credits / avg_daily_consumption <= days`，生成 `dedupe_key = low_balance:{creator_bid}:estimated_days:{days}:lookback:{lookback_days}:{date}`。
6. 如果已有部分有效消耗历史但有效消耗天数少于 `min_consumed_days`，且配置了 `fallback_fixed_value`，则按固定阈值兜底，并沿用固定阈值 dedupe key。
7. 通知记录的模板参数快照保存 `threshold_kind`、`available_credits`、`trigger_days`、`lookback_days`、`avg_daily_consumption`、`estimated_remaining_days`。
8. dry-run 返回每条候选的平均日消耗、预计剩余可用天数、回看天数和跳过原因。
9. 成功创建 `pending` 记录后 enqueue 发送任务。
10. v1 可以保留旧 `billing.send_low_balance_alert` 任务名作为兼容入口，内部委托给新扫描逻辑。

低余额扫描只负责通知，不负责阻止请求；hardlimit 仍由 billing admission 判断。

低余额扫描任务应排在每日 ledger aggregate finalize 之后执行；扫描任务本身不主动 rebuild 日聚合。

## 发送流程

1. `billing.send_credit_notification` 接收 `notification_bid`。
2. worker 使用行锁加载通知记录，只处理 `pending` 或 `failed_provider`。
3. 如果策略已关闭、用户退订、命中黑名单、超出频控或预算，标记 `skipped_opt_out`。
4. 如果无法解析手机号，标记 `skipped_no_mobile`。
5. 如果处于免打扰时间，可延迟重新入队；如果策略要求不延迟，则标记跳过并记录原因。
6. 使用 `template_code` 和 `template_params_json` 调用 `send_sms_ali`。
7. 供应商成功后标记 `sent`，失败后标记 `failed_provider`，保存错误摘要。

## 运营后台接口

在现有 `/shifu/admin/operations` 下新增接口：

| 方法与路径 | 说明 |
| --- | --- |
| `GET /shifu/admin/operations/credit-notifications` | 查询通知记录 |
| `GET /shifu/admin/operations/credit-notifications/config` | 读取通知策略 |
| `POST /shifu/admin/operations/credit-notifications/config` | 更新通知策略 |
| `POST /shifu/admin/operations/credit-notifications/dry-run` | 预估命中人群、跳过原因和短信成本 |
| `POST /shifu/admin/operations/credit-notifications/{notification_bid}/requeue` | 重发 `failed_provider` 通知 |

列表筛选条件包括：

- 创作者 BID
- 目标用户 BID
- 手机号
- 通知类型
- 渠道
- 状态
- 来源类型和来源 ID
- 创建时间范围

运营接口只允许修改通知策略和通知投递状态，不得修改 wallet、bucket 或 ledger。

## 前端设计

运营平台新增“积分通知”页面，建议放在运营管理菜单下。页面包含：

- 通知记录列表和筛选。
- 失败详情查看。
- `failed_provider` 单条重发。
- 通知类型开关、短信模板 code、到期窗口、低余额阈值配置。
- 低余额阈值表单支持固定积分阈值和“按可用天数提醒”，不得暴露 raw JSON textarea。
- softlimit 阈值、老师端提醒、禁止调试策略配置。
- 频控、免打扰、黑名单、退订、预算配置。
- 策略配置必须是结构化表单，不提供 raw JSON 编辑入口。
- dry-run 结果展示，包括预计发送数、跳过数和成本估算。

老师端账务、个人中心和调试入口需要消费统一余额状态：

- `normal`：正常展示。
- `softlimit`：展示老师端提醒，前端禁用调试入口。
- `hardlimit`：展示余额耗尽提醒，学生端新内容生成和追问停止生成。

softlimit 采用前后端都拦截。前端负责禁用入口和展示提示，后端调试/预览类 API 也必须校验 `debug_allowed`，避免直接调用 API 绕过。

## Runtime 与 hardlimit 边界

- hardlimit 判定来自 billing 可消费余额，不能由运营平台配置。
- hardlimit 后学生端停止 LLM/TTS 等新内容生成，属于 runtime 行为，不通过异步通知任务补偿。
- softlimit 不影响学生端正常学习体验，只影响老师端提醒、短信触达和调试入口。
- 若调试/预览 API 因 softlimit 被拦截，应使用独立的老师端错误语义，不扩展学生端 runtime admission 错误码。

## 迁移与发布

1. 新增表和索引，默认不启用任何通知类型。
2. 新增配置 seed，`BILL_CREDIT_NOTIFICATION_SMS_CONFIG.enabled=false`。
3. 上线后台配置读取和 dry-run，先验证命中量和模板变量。
4. 开启 `credit_granted` 小流量，因为它是事件触发且来源最明确。
5. 开启 `credit_expiring` 和 `low_balance` 扫描任务，先 dry-run，再启用实际发送。
6. 开启 softlimit 老师端提示和调试拦截。
7. 根据发送成功率、供应商失败率、退订率和短信成本调整策略。

## 观测指标

按通知类型和渠道统计：

- 生成通知数。
- 发送成功数。
- 供应商失败数。
- 按原因分组的跳过数。
- 重复抑制数。
- 重发次数。
- 短信成本估算。
- 通知后的登录、checkout、充值、续费、课程创建或继续消耗积分转化。

指标只用于运营分析，不参与账务余额计算。

## 测试计划

### 后端单元测试

- `credit_granted`、`credit_expiring`、`low_balance` 三类通知 staging。
- `dedupe_key` 重复时不重复发送。
- 无手机号、退订、黑名单、频控和预算命中时跳过。
- provider 失败落 `failed_provider`，后台 requeue 后可再次发送。
- dry-run 返回预计发送数、跳过原因和成本估算。
- 运营接口权限校验和参数校验。

### 定时任务测试

- 到期窗口扫描只命中配置窗口内 active bucket。
- 低余额扫描按配置阈值命中创作者。
- 低余额自动阈值按 `bill_daily_ledger_summary` 计算平均日消耗和预计剩余天数。
- 没有有效日消耗汇总或平均日消耗为 `0` 时跳过自动阈值，不触发兜底发送；已有部分历史但有效消耗天数不足时，配置兜底值才按固定阈值判断。
- 自动阈值 dry-run 返回 `avg_daily_consumption`、`estimated_remaining_days`、`lookback_days` 和跳过原因。
- 历史已通知记录不会再次生成同一 `dedupe_key`。
- 旧 `billing.send_low_balance_alert` 兼容入口返回可观测结果。

### 账务边界测试

- 通知发送失败不影响积分发放、消耗和过期。
- 余额桶过期仍由 `billing.expire_wallet_buckets` 负责。
- hardlimit 仍由 billing admission 判断。

### 前端测试

- 运营菜单展示“积分通知”入口。
- 通知记录列表筛选、失败详情、重发按钮状态。
- 策略配置表单校验模板、窗口、固定阈值、按可用天数提醒参数和频控。
- 运营配置页不能出现 raw JSON textarea。
- dry-run 结果展示。
- softlimit 下老师端调试入口禁用；后端拦截时前端展示明确提示。

### 仓库校验

文档或实现完成后至少运行：

```bash
python scripts/check_repo_harness.py
```

如果实现涉及前端或后端共享契约，还需要补充对应 pytest 或前端测试。

## 验收标准

- 技术设计明确使用独立通知记录表承载三类积分通知状态。
- 技术设计明确 `sys_configs` 运营策略配置和不可配置边界。
- 技术设计明确三类通知的触发源、任务流、发送流和幂等键。
- 技术设计明确运营后台接口、前端页面和 softlimit 前后端拦截策略。
- 技术设计明确不复用验证码短信、不修改账务事实、不改变 hardlimit 账务边界。
- 测试计划覆盖后端 staging、worker、扫描任务、运营接口、前端页面和 softlimit 行为。

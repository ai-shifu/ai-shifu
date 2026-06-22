---
title: 老带新邀请奖励
status: implemented
owner_surface: shared
last_reviewed: 2026-06-11
canonical: true
---

# 老带新邀请奖励

## 背景

本文把飞书 wiki `AI 师傅老带新邀请奖励产品方案` 落成仓库内可执行的产品与技术设计。外部方案定义的第一版能力是：老用户邀请新用户完成国内手机号注册后，老用户获得 1 个月 199 元套餐权益，最多 12 个月；新用户只保留平台已有的 15 天免费 1000 积分福利。

仓库里已有这些相关基础能力：

- 用户注册和登录流程在 `src/api/flaskr/route/user.py`。
- 登录后的副作用通过 `src/api/flaskr/service/user/post_auth.py` 执行。
- 新老师试用初始化已经是 `src/api/flaskr/service/billing/auth_hooks.py` 里的 post-auth extension。
- 计费事实以 `bill_orders`、`bill_subscriptions`、`credit_wallet_buckets`、`credit_ledger_entries` 为准。
- 运营手动发放套餐已经通过 `src/api/flaskr/service/billing/manual_plan_grants.py` 创建 `manual + paid` 订单。
- 现有 `referral_reward_grants.py` 支持运营手动发放 referral reward credits，但它不表达邀请码、邀请关系绑定、注册触发自动奖励、权益队列或 12 个月上限。

## 当前实现状态

2026-06-09 的实现已覆盖本设计的核心 v1 链路：

- 后端新增 campaign-aware referral 表、活动规则、邀请码、邀请事件、关系绑定、奖励审计、post-auth 绑定和 billing reward helper。
- 前端新增老师邀请页、被邀请人落地页、登录 payload 透传、运营 referral 页面和共享 i18n 文案。
- 运营侧提供列表、详情、overview、状态更新和带备注的人工调整 API；人工调整复用审计化 status/adjustment payload，不直接删除 billing 事实。
- Reward grant 失败时先保留 relation/reward 行，并提供幂等 retry helper 修复缺失的 billing artifacts。

dev02 的活动配置、真实 product code 校验、真实注册合成用例和 DB 对账仍是发布验证步骤，不能用本地单测替代。

## 目标

- 给每个已注册国内用户一个不可编辑的专属邀请码和邀请链接。
- 支持邀请链接进入和注册前手动输入邀请码两种入口。
- 新国内手机号用户注册成功时，绑定到且只绑定到一个邀请人。
- 邀请人资格、新人资格、奖励上限、奖励产品、奖励周期和生效策略全部从活动配置表读取，不写死在邀请生命周期代码里。
- 首发活动中，每个有效邀请给邀请人自动发放 1 个月配置好的 199 元套餐权益，最多 12 个月。
- 第 13 个及之后的新用户仍可正常注册和绑定，但不再自动生成奖励，并在老用户侧展示联系团队的状态。
- 被邀请新用户只享受既有 15 天免费福利，不额外增加邀请新人福利。
- 奖励发放复用计费订单、订阅、积分桶和流水，避免 referral 域自建余额体系。
- 首发活动的 30 天权益周期、每周期 1000 积分、到期未用积分过期语义，通过 billing artifacts 表达。
- 给运营后台提供邀请关系、奖励状态、被邀请用户账号数据、异常处理和人工调整的可追踪能力。
- 记录活动效果判断需要的最小漏斗数据：邀请链接点击、注册页访问、邀请码输入、注册提交、邀请注册、奖励月数、被邀请用户使用、积分消耗和付费转化。

## 非目标

- 第一版不做海外邀请链路。
- 第一版不做多级分销、排行榜、裂变游戏等复杂玩法。
- 不支持用户自定义邀请码。
- 不支持用户注册后自行补填邀请码。
- 不做自动风控判定并自动取消奖励。
- 不对已消耗的异常奖励做自动追扣。
- 不新增支付渠道集成。
- 不在用户计费侧新增独立的 referral credits 产品族。

## 推荐方案

新增独立的 `service/referral` 域，负责活动配置、邀请码、邀请事件、邀请关系、奖励实例和异常处理。Referral 域读取当前有效活动与奖励规则，当邀请关系满足奖励条件时调用 billing reward helper。套餐权益、积分桶和流水仍以 billing 域为事实来源。

这个方案避免两个问题：

- 如果把邀请关系放进 `service/billing`，会把增长活动状态和计费状态混在一起，点击/注册漏斗也会变成计费关注点。
- 如果复用现有 `referral_reward_grants.py` 名称，虽然名字相近，但该路径只做运营手动 credit 发放，不能表达自动邀请绑定、权益排队、活动配置和奖励上限。

首发活动是飞书里的老带新方案，但数据模型不应只服务这一种活动。可变的业务规则放在活动配置和奖励规则表里；关系表和奖励表记录运行事实、配置快照和审计线索。

## 产品规则

### 参与资格

- 当前有效活动规则定义邀请人资格和被邀请人资格。
- 首发活动中，任意已注册国内用户都可以作为邀请人。
- 首发活动中，可奖励的新用户必须是国内手机号验证码注册产生的新账号。
- 已存在用户通过邀请链接登录时，不会被重新绑定，也不会产生奖励。
- 临时用户或游客升级为手机号账号时，只有最终手机号认证结果创建了新的真实账号才可计入邀请。
- 一个被邀请用户只能有一个邀请人。
- 自邀请必须拒绝。

### 邀请码与邀请链接

- 邀请码由后端生成，唯一、不可变、用户不可编辑。
- 邀请码按活动维度生成，同一用户在不同活动中可以拥有不同邀请码。
- 用户首次打开邀请页或运营查看邀请资料时，懒创建邀请码。
- 邀请链接使用公开前端 origin 构造，并携带邀请码，例如 `/invite/{invite_code}` 或 `/login?invite_code={invite_code}`。具体路由形态可在实现时调整，但后端只保存规范的邀请码，不保存完整链接。
- 被邀请人也可以在注册前手动输入邀请码。手动输入和邀请链接进入使用同一套校验、绑定和事件记录路径。
- 邀请上下文从邀请落地页或手动输入入口进入前端状态，并随 SMS 登录请求传到后端。
- 注册成功是唯一绑定时刻。注册后用户不能自行补填邀请码。
- 注册成功后如需调整邀请关系，只能由后台人工审计处理。

### 奖励规则

- 每个有效邀请注册最多创建一个奖励记录。
- 当前活动奖励规则定义奖励上限、奖励产品、奖励数量、积分数量、有效期和生效策略。
- 首发活动中，前 12 个有效邀请各奖励 1 个月配置的 199 元套餐权益。
- 首发活动中，第 13 个及之后的被邀请用户会继续绑定并进入统计，但不自动生成 billing reward。
- 奖励产品通过 reward rule 上的稳定产品 code 配置。首发预期产品是 199 元月套餐。启用前必须验证配置产品的价格、周期和积分数量符合活动口径。
- 如果邀请人没有任何有效权益窗口，奖励立即生效。
- 如果邀请人当前是免费或试用套餐，奖励排在当前免费或试用权益结束后生效，不提前叠加到当前周期可用积分。
- 如果邀请人已有同款奖励套餐，奖励按配置周期数顺延。
- 如果邀请人已有更高级套餐或年套餐，奖励排在当前付费权益结束后，作为配置的奖励权益生效。
- 付费权益优先于邀请权益，避免影响收入确认和用户已购买权益。
- 多个邀请奖励按获得时间顺序排队发放。
- 首发活动中，每个奖励周期为 30 天，通过普通 wallet bucket 发放 1000 积分；该 bucket 在 30 天周期结束时过期，未使用积分不结转。

### 被邀请人福利

- 被邀请人福利策略是活动配置项。
- 首发活动中，被邀请新用户只获得平台已有的新用户 15 天免费福利。
- 第一版 referral 系统不为被邀请人额外发放积分、套餐、优惠券或学习权益。

### 活动配置

首发上线需要创建一条有效活动配置和一条有效奖励规则。后续活动的文案、时间窗口、奖励上限、奖励产品、积分数量、积分有效期或被邀请人福利策略，不应依赖发版才能调整；但代码仍要校验配置的奖励是否可以安全发放。

首发活动配置：

- `campaign_code`：稳定 code，例如 `domestic_creator_invite_202606`。
- 邀请人资格：已注册国内用户。
- 被邀请人资格：新创建的国内手机号用户。
- 邀请路由模板：公开邀请落地页。
- 被邀请人福利策略：仅使用既有新用户试用。
- 奖励触发事件：邀请注册成功。
- 奖励目标：邀请人。
- 奖励类型：billing plan cycle。
- 奖励产品 code：配置的 199 元月套餐。
- 奖励周期数：1。
- 奖励积分数量期望：每周期 1000 积分。
- 奖励积分有效期：每周期 30 天。
- 邀请人奖励上限：12。
- 奖励生效策略：无任何有效权益窗口时立即生效；免费/试用、同套餐、更高级套餐或年套餐均在当前权益结束后顺延。

### 异常处理

第一版记录可疑上下文，但不自动取消奖励。运营可以人工标记邀请关系或奖励为异常。

可能的异常信号：

- 同一邀请人在短时间内出现大量注册。
- 同一 IP 或设备指纹出现大量注册。
- 被邀请账号呈现批量注册特征。
- 被邀请账号注册后被封禁。
- 运营判断为异常的其他情况。

运营动作：

- 奖励尚未发放时，可以取消奖励。
- 奖励已发放但未使用时，可以冻结或取消相关 reward bucket，并标记奖励记录。
- 奖励已使用时，只保留运营记录，不做自动追扣。
- 对注册后确需纠正的邀请关系，后台提供带审计备注的人工调整入口。

## 数据模型

新增后端模块 `src/api/flaskr/service/referral/`，包含 models、constants、DTO、routes、service 和 tests。

### `referral_campaigns`

每个 referral 活动一行。该表把活动业务配置从代码和运行期关系表中拆出来。

字段：

- `campaign_bid`：业务标识。
- `campaign_code`：稳定唯一 code，用于配置、路由、日志和修复脚本。
- `campaign_name`：运营可读名称。
- `campaign_status`：draft、active、paused、ended、archived。
- `feature_flag_key`：可选 rollout flag，活动运行前必须打开。
- `starts_at`、`ends_at`：可空活动时间窗口。
- `invite_route_template`：前端邀请链接模板。
- `inviter_eligibility`：JSON 规则快照，例如国内已注册用户。
- `invitee_eligibility`：JSON 规则快照，例如新国内手机号注册。
- `invitee_benefit_policy`：existing_trial_only、campaign_bonus、none。
- `rules_copy_i18n_key`：可选用户侧规则文案根 key。
- `metadata`：运营备注和未来展示配置。
- 标准 `deleted`、`created_at`、`updated_at`。

索引：

- unique `campaign_code`。
- `campaign_status + starts_at + ends_at`。

### `referral_campaign_reward_rules`

每个活动可有一条或多条奖励规则。首发活动只需要一条规则，但模型允许后续活动添加不同奖励类型或上限，而不改变关系存储。

字段：

- `reward_rule_bid`：业务标识。
- `campaign_bid`。
- `rule_code`：活动内稳定唯一 code。
- `rule_status`：draft、active、paused、ended。
- `trigger_event`：invited_registration。
- `reward_target`：inviter、invitee。
- `reward_type`：billing_plan_cycle。
- `reward_product_code`：稳定 billing product code。
- `reward_cycle_count`：每次触发发放的产品周期数。
- `reward_credit_amount`：可选的每周期积分数量期望。
- `reward_credit_validity_days`：可选的积分桶有效期。
- `reward_cap_scope`：per_inviter、per_campaign、none。
- `reward_cap_count`：可空整数上限。
- `reward_timing_policy`：immediate_extend_or_defer。
- `priority`。
- `starts_at`、`ends_at`：可选规则级时间窗口。
- `metadata`：配置的价格/积分期望、文案 key、运营备注。
- 标准 `deleted`、`created_at`、`updated_at`。

索引：

- unique `campaign_bid + rule_code`。
- `campaign_bid + rule_status + priority`。

### `referral_invite_codes`

每个邀请人在每个活动中一行。

字段：

- `invite_code_bid`：业务标识。
- `campaign_bid`。
- `inviter_user_bid`：用户业务标识。
- `invite_code`：唯一不可变公开 code。
- `status`：active、disabled。
- `generated_at`。
- 标准 `deleted`、`created_at`、`updated_at`。

索引：

- unique `invite_code`。
- unique active `campaign_bid + inviter_user_bid`。

### `referral_invite_events`

追加写事件表，用于最小活动漏斗分析。它覆盖邀请链接点击、注册页访问、手动输入邀请码和注册提交，不把所有事件都建模成 click。

字段：

- `event_bid`。
- `campaign_bid`。
- `event_type`：invite_link_clicked、registration_page_viewed、invite_code_entered、registration_submitted。
- `invite_code`：无效手动输入时可空。
- `inviter_user_bid`：邀请码解析成功前可空。
- `session_id`：前端生成的匿名 session 标识。
- `client_ip_hash`：单向 hash，不保存原始 IP。
- `user_agent_hash`：单向 hash，不保存原始 user agent。
- `landing_path`。
- `metadata`：输入来源、校验结果等非识别性事件细节。
- `created_at`。

后续统计任务可聚合该事件表。v1 保留原始事件行，便于审计和运营分析。

### `referral_invite_relations`

每个被邀请账号绑定一行。

字段：

- `relation_bid`。
- `campaign_bid`。
- `reward_rule_bid`：规则选择前可空。
- `invite_code`。
- `inviter_user_bid`。
- `invitee_user_bid`：active 时唯一。
- `invitee_mobile_snapshot`：注册时规范化手机号快照。
- `bound_at`。
- `registration_source`：phone。
- `reward_eligible`：boolean-like small integer。
- `relation_status`：registered、reward_generated、reward_pending_effective、reward_active、reward_ended、reward_skipped_cap、abnormal_reviewing、canceled。
- `abnormal_status`：normal、reviewing、confirmed_abnormal。
- `metadata`：落地页、session、客户端指纹、运营备注。
- 标准 `deleted`、`created_at`、`updated_at`。

索引：

- unique active `invitee_user_bid`。
- `campaign_bid + inviter_user_bid + bound_at`。
- `invite_code + bound_at`。
- `relation_status + created_at`。

### `referral_invite_rewards`

Referral 域的奖励审计表。计费、积分和有效期事实仍以 billing 为准；该表连接邀请关系、活动规则快照和 billing artifacts。

字段：

- `reward_bid`。
- `campaign_bid`。
- `reward_rule_bid`。
- `relation_bid`：可奖励关系唯一。
- `inviter_user_bid`。
- `invitee_user_bid`。
- `reward_sequence_index`：配置上限内的奖励序号。
- `reward_product_code`：发放时使用的产品 code 快照。
- `reward_cycle_count`：配置周期数快照。
- `reward_credit_amount`：配置积分数量快照。
- `reward_credit_validity_days`：配置积分有效期快照。
- `reward_cap_count`：配置上限快照。
- `reward_status`：generated、pending_effective、active、expired、frozen、canceled、skipped_cap。
- `billing_subscription_bid`。
- `bill_order_bid`。
- `wallet_bucket_bid`。
- `ledger_bid`。
- `effective_from`。
- `effective_to`。
- `credit_bucket_expires_at`。
- `operator_note`。
- 标准 `deleted`、`created_at`、`updated_at`。

索引：

- `campaign_bid + inviter_user_bid + reward_status`。
- `reward_rule_bid + inviter_user_bid`。
- `relation_bid`。
- `bill_order_bid`。
- `wallet_bucket_bid`。

## 后端流程

### 邀请资料

老师侧 API 放在 `/api/referral`：

- `GET /api/referral/invite-profile`
  - 返回 campaign code、邀请码、邀请链接、成功邀请数、已奖励数、剩余奖励数、奖励队列摘要和来自活动配置的规则说明。
- `POST /api/referral/invite-event`
  - 匿名或登录态都可调用，用于记录邀请链接点击、注册页访问、手动输入邀请码和注册提交事件。不得暴露邀请人隐私信息。

运营 API 放在现有 operations namespace：

- `GET /api/shifu/admin/operations/referrals`
- `GET /api/shifu/admin/operations/referrals/{relation_bid}`
- `POST /api/shifu/admin/operations/referrals/{relation_bid}/status`
- `POST /api/shifu/admin/operations/referrals/{relation_bid}/adjustment`
- `GET /api/shifu/admin/operations/referrals/overview`

### 注册绑定

扩展 `PostAuthContext`，增加可选 referral 字段：

- `invite_code`。
- `referral_session_id`。
- `referral_entry_source`：invite_link、manual_code。
- `client_ip_hash`。
- `user_agent_hash`。

SMS 登录时，从请求 payload 读取 `invite_code`、`referral_session_id`、`referral_entry_source`，只传入 post-auth context；路由层不直接绑定邀请关系。Referral post-auth handler 只在 `created_new_user = true` 时处理。

处理步骤：

1. 规范化并校验邀请码。
2. 加载邀请码与有效活动。
3. 根据有效活动规则评估邀请人和被邀请人资格。
4. 拒绝自邀请。
5. 插入 `referral_invite_relations`，并通过唯一约束保证 invitee user BID 只绑定一次。
6. 选择 invited-registration 触发的有效奖励规则。
7. 按规则配置的 cap scope 统计邀请人的既有奖励实例。
8. 未达到 cap 时，创建包含活动和规则快照的 reward row，并调用 billing reward grant。
9. 达到 cap 时，记录 `reward_skipped_cap`，不产生 billing side effects。

Post-auth handler 与现有 billing trial hook 一样是 best-effort：登录不能因为 referral 副作用失败而失败。重复插入和重试路径必须幂等，修复脚本可从 relation/reward row 补偿缺失的 billing artifacts。

### 计费发放

新增 referral plan reward 专用 helper，不复用运营 grant request shape：

```text
grant_referral_plan_reward(app, inviter_user_bid, relation_bid, reward_bid, reward_rule_snapshot)
```

该 helper 复用现有 `manual + paid` 订单和 `grant_paid_order_credits` 路径，但要支持 referral 奖励的生效策略：

- 没有任何有效权益窗口时立即生效。
- 当前是免费或试用套餐时，排到当前免费或试用权益结束后生效。
- 当前同款自营订阅使用奖励产品时，同套餐顺延。
- 当前更高级套餐或年套餐时，排到当前付费周期结束后生效。
- 首发奖励积分桶按配置保持 30 天过期。

Billing metadata 必须包含：

- `checkout_type = referral_invitation_reward`
- `grant_channel = referral_invitation`
- `campaign_bid`
- `campaign_code`
- `reward_rule_bid`
- `relation_bid`
- `reward_bid`
- `invitee_user_bid`
- `reward_sequence_index`

幂等性：

- provider reference：`referral-reward:{reward_bid}`。
- ledger idempotency 继续沿用 billing grant 路径：`grant:{bill_order_bid}`。
- 同一个 reward 重复调用时返回既有 billing artifacts。

## 前端流程

### 邀请人侧

在老师/后台区域增加“邀请好友”入口，不放在 learner course runtime 内。第一版展示：

- 邀请链接。
- 邀请码。
- 复制链接按钮。
- 已奖励月数和剩余奖励月数。
- 奖励状态或待生效队列。
- 当付费权益优先导致邀请奖励“已获得但待生效”时，明确展示 pending-effective 状态。
- 来自共享 i18n JSON 的活动规则说明。

达到配置上限时，展示自动奖励已满，并提示联系团队进一步沟通。

### 被邀请人落地页

新增轻量邀请落地页：

- 在登录完成前保存邀请码和 referral session id。
- 记录邀请链接点击和注册页访问事件。
- 允许用户在 SMS 登录前手动输入邀请码，并记录手动输入事件。
- SMS 登录时携带 invite code。
- 复用既有登录 UI 和手机号验证码语义。

被邀请人页面不能承诺额外邀请福利。

### 运营后台

在 `Admin -> Operations` 或相邻 operations tab 增加 referral 视图：

- overview metrics。
- 关系列表：邀请人、被邀请人手机号/user BID、注册时间、奖励状态、异常状态。
- 详情抽屉：billing order、subscription、wallet bucket、ledger、运营状态操作。
- 审计化人工调整入口，用于少数注册后必须取消或纠正关系的场景。

## API 形态

邀请人资料响应：

```json
{
  "campaign_code": "domestic_creator_invite_202606",
  "invite_code": "AB12CD34",
  "invite_link": "https://app.ai-shifu.cn/invite/AB12CD34",
  "successful_invite_count": 3,
  "rewarded_count": 3,
  "remaining_reward_count": 9,
  "reward_cap": 12,
  "reward_unit": "month",
  "reward_queue": [
    {
      "reward_bid": "reward_...",
      "status": "pending_effective",
      "reward_sequence_index": 3,
      "effective_from": "2026-06-08T00:00:00Z",
      "effective_to": "2026-07-08T00:00:00Z"
    }
  ]
}
```

SMS 登录请求扩展：

```json
{
  "mobile": "13800000000",
  "sms_code": "123456",
  "invite_code": "AB12CD34",
  "referral_session_id": "browser-generated-id",
  "referral_entry_source": "invite_link"
}
```

邀请事件请求：

```json
{
  "campaign_code": "domestic_creator_invite_202606",
  "event_type": "registration_page_viewed",
  "invite_code": "AB12CD34",
  "referral_session_id": "browser-generated-id",
  "landing_path": "/invite/AB12CD34"
}
```

运营关系列表项：

```json
{
  "relation_bid": "relation_...",
  "inviter_user_bid": "user_...",
  "invitee_user_bid": "user_...",
  "invitee_mobile": "13800000000",
  "invitee_registered_at": "2026-06-08T00:00:00Z",
  "bound_at": "2026-06-08T00:00:00Z",
  "relation_status": "reward_generated",
  "reward_status": "pending_effective",
  "campaign_code": "domestic_creator_invite_202606",
  "reward_rule_code": "inviter_monthly_plan_per_registration",
  "reward_sequence_index": 1,
  "bill_order_bid": "bill_..."
}
```

## 安全与隐私

- 只在运营确实需要的地方保存手机号快照；邀请人侧永不展示被邀请人手机号。
- 事件 IP 和 user agent 只保存 hash。
- 邀请码要足够不可猜。使用随机字节并做碰撞重试，不使用确定性的用户 ID。
- 匿名接口不能泄露邀请码属于哪个具体用户。
- 运营 API 复用现有 operator guard。

## 可观测性与统计

增加结构化日志：

- 邀请资料创建。
- 邀请事件记录。
- 邀请关系绑定。
- 奖励达到上限跳过。
- billing reward grant 成功或失败。
- 异常状态变化。

运营 overview 指标需要覆盖飞书活动统计要求：

- 邀请链接点击数。
- 注册页访问数。
- 邀请完成注册数。
- 每位老用户邀请人数。
- 有效奖励发放月数。
- 达到上限的邀请人数。
- 异常邀请数量。
- 被邀请用户后续使用、积分消耗和付费转化，这些指标从既有 usage、wallet、billing 表与 referral relation/event 做 join 得出。

日志使用后端已有 request ID。奖励修复脚本必须打印 relation 和 reward BID，方便运营用 DB 行对账。

## 验证

后端重点测试：

- 活动与奖励规则配置只加载时间窗口内的 active campaign。
- eligibility 和 cap 使用配置值，不使用硬编码常量。
- 邀请码生成唯一且不可变。
- 邀请码按 campaign 隔离。
- 邀请链接入口和手动输入邀请码入口都能把邀请上下文带到 SMS 登录。
- 邀请事件记录 link click、registration page view、manual code entry、registration submit，且不保存原始 IP/user agent。
- 带邀请码的 SMS 登录只绑定新手机号用户。
- 已有用户不会被重新绑定。
- 自邀请被拒绝。
- 首发活动前 12 个邀请注册生成奖励。
- 首发活动第 13 个注册跳过自动奖励，但注册成功。
- 修改测试活动的 cap 配置后，奖励行为随配置变化，不需要改代码。
- 重复 post-auth 重试幂等。
- billing helper 创建 `manual + paid` 订单 metadata 和关联 ledger。
- 首发活动奖励按权益队列创建 30 天 1000 积分 bucket；有当前权益窗口时先进入 reserved，到周期边界释放为当期 available，并在周期结束时过期未用积分。
- 更高级套餐或年套餐下，奖励延后到现有付费权益结束后生效。
- 运营异常动作更新 relation/reward 状态，不删除 billing truth。
- 运营 overview 能报告点击、注册页访问、注册、奖励月数、达到上限用户数、异常数、被邀请用户使用、被邀请用户积分消耗和被邀请用户付费转化。

前端重点测试：

- 邀请资料页展示链接、邀请码、复制动作、奖励数量和上限状态。
- 邀请落地页能把链接带来的邀请码和手动输入的邀请码都带到登录 payload。
- 邀请落地页说明 pending-effective 奖励和配置上限状态。
- 运营关系列表支持筛选并打开详情。
- 用户可见文案来自 `src/i18n`。

仓库检查：

- `python scripts/check_repo_harness.py` 校验文档和索引完整性。
- `cd src/api && pytest tests/service/user/ tests/service/referral/ tests/service/billing/ -q` 校验后端行为。
- 前端实现后运行 `cd src/cook-web && npm run type-check && npm run lint`。

## 发布

1. 后端 feature flag 默认关闭。
2. 在 dev02 seed 首发 campaign 和 reward rule，包含 reward product code、cap、eligibility、1000 积分和 30 天有效期配置。
3. 跑邀请链接注册的合成用例。
4. 跑手动输入邀请码注册的合成用例。
5. 查询 dev02 DB 的 relation、reward、billing order、subscription、wallet bucket、ledger。
6. 查询 dev02 event rows，确认 link click、registration page view、manual code entry、registration submit 都落表。
7. 启用运营列表可见。
8. 启用老师邀请入口。
9. 第一周每日监控邀请注册、奖励数量和异常活动。

## 事实来源

- 产品行为：本文。
- 实施执行：`docs/exec-plans/active/referral-invitation-rewards.md`。
- 活动配置值：`referral_campaigns` 和 `referral_campaign_reward_rules`。
- 计费产品和积分语义：`docs/billing-subscription-design.md`。
- 用户管理和运营约定：`docs/product-specs/operator-user-management.md`。

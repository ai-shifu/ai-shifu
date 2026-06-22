# 老带新邀请奖励实施计划

## Purpose / Big Picture

基于可配置 referral campaign，实现 AI 师傅第一版“老用户邀请新用户”奖励链路。老用户获得邀请码和邀请链接；新手机号注册用户可以在注册时绑定一个邀请人；首发活动中，每个有效邀请给邀请人发放 1 个月配置好的 199 元套餐权益，最多 12 个月。

## Progress

- [x] 2026-06-08 22:30 CST：阅读飞书方案，检查现有用户认证、post-auth、billing、运营手动套餐发放和运营 referral reward 路径。
- [x] 2026-06-08 22:45 CST：在 `docs/design-docs/referral-invitation-rewards.md` 中记录产品和技术设计。
- [x] 2026-06-08 23:25 CST：按反馈增加 campaign 和 reward rule 配置表，避免实现只面向单一需求硬编码。
- [x] 2026-06-09 16:15 CST：再次对照飞书需求，补齐手动输入邀请码、通用邀请事件、30 天积分过期、运营人工调整和活动统计覆盖。
- [x] 2026-06-09 17:10 CST：按协作要求把设计文档和本 ExecPlan 的正文改为中文；保留 `PLANS.md` 要求的英文 section 锚点。
- [x] 2026-06-09 17:45 CST：实现后端 referral domain models、migration、services、routes、post-auth hook、billing reward helper 和重点 tests。
- [x] 2026-06-09 17:48 CST：实现老师邀请页、被邀请人落地页、登录 payload 透传、前端 API/types 和共享 i18n 文案。
- [x] 2026-06-09 17:50 CST：实现运营 referral 监控页、列表/详情/overview/status API、人工 adjustment API 和 reward grant retry helper。
- [x] 2026-06-11 14:55 CST：按 dev02 对账反馈修正 billing reward helper：免费/试用等任何当前有效权益窗口均不提前加账，邀请奖励进入 renewal reserved 队列，到期后自动释放并顺延。
- [ ] 2026-06-08 22:45 CST：在 dev02 使用真实 billing product 配置和数据库行完成验证。

## Surprises & Discoveries

- `src/api/flaskr/service/billing/referral_reward_grants.py` 已存在，但它是运营手动 credit pool，不表达邀请码、被邀请人绑定、自动奖励或 12 个月上限。
- `src/api/flaskr/service/billing/manual_plan_grants.py` 已有有用的 `manual + paid` 订单编排模式，但当前语义是运营套餐发放和立即生效/升级。Referral 奖励需要同套餐顺延，以及在更高级套餐或年套餐结束后延后生效。
- `src/api/flaskr/service/user/post_auth.py` 是注册侧扩展点。它已被 billing trial bootstrap 使用，并且是 best-effort，不会把登录成功和副作用强绑定。
- 测试 fixture 产品 `creator-plan-monthly-pro` 代表 199 元月套餐，但启用功能前必须验证线上 catalog 的积分数量，因为飞书方案要求每 30 天周期 1000 积分。
- 初始设计过于贴近单个飞书活动。数据模型需要 campaign 和 reward rule 配置表，让 cap、product、route、eligibility、积分有效期和 timing policy 不通过改代码表达。

## Decision Log

- 新增 `src/api/flaskr/service/referral/` 域，负责活动配置、邀请码、邀请事件、关系绑定、奖励审计、修复脚本和运营 read model。
- 将可变活动业务配置放在 `referral_campaigns` 和 `referral_campaign_reward_rules`。运行期 invite、relation、reward 行引用这些配置行，并保留审计需要的快照。
- Billing 仍是套餐和积分事实来源。每个已发放奖励仍通过 billing order、subscription、wallet bucket 和 ledger entries 表达。
- 不复用现有运营 `referral_reward_grants.py` helper 承载自动邀请奖励；该 helper 保留为当前运营手动 credit 工具。自动邀请奖励上线后，是否重命名或合并这些 surface 可以单独清理。
- 扩展 `PostAuthContext`，加入可选 referral metadata；不要把邀请绑定逻辑直接写在 route handler 里。
- Post-auth 奖励生成保持 best-effort 和幂等；缺失 side effects 可从 `referral_invite_relations` 与 `referral_invite_rewards` 修复。
- 邀请事件只保存 hash 后的 IP 和 user agent，不保存原始值。
- Billing grant 与 relation/reward 创建解耦。先保存 referral 事实，再调用 billing；billing 失败时写入 `grant_error` 和 `last_failed_at`，后续通过 retry helper 幂等修复。

## Outcomes & Retrospective

本 PR 已完成一个受 campaign 配置和 feature flag 控制的 referral reward v1：

- 后端可以从 `referral_campaigns` 与 `referral_campaign_reward_rules` 读取活动、cap、产品、积分有效期和生效策略。
- SMS 新用户注册时，post-auth 会按邀请码绑定 relation，并在 cap 内生成 reward 和 billing artifacts；达到 cap 时保留关系但跳过 billing side effects。
- 老师侧可以查看邀请码/邀请链接/奖励数量；被邀请人侧可以通过链接或手动输入邀请码进入同一 SMS 登录 payload。
- 运营侧可以查看 overview、筛选关系列表、打开详情、标记异常、取消关系/奖励、冻结奖励并写入备注。
- 本地验证覆盖 py_compile、ruff、后端重点 pytest、前端 type-check、前端重点 jest 和 targeted lint。

尚未完成的是 dev02 发布验证：真实 product code、campaign/rule seed、真实注册合成用例、event rows 与 billing/order/subscription/wallet/ledger DB 对账仍需在环境配置后执行。

## Context and Orientation

开始实现前先读这些文件：

- 设计来源：`docs/design-docs/referral-invitation-rewards.md`。
- 计费设计：`docs/billing-subscription-design.md`。
- 用户认证规则：`src/api/AGENTS.md`、`src/api/flaskr/service/user/AGENTS.md`、`src/api/skills/user-auth-flows/SKILL.md`。
- 计费规则：`src/api/flaskr/service/billing/AGENTS.md`。
- 前端规则：`src/cook-web/AGENTS.md`、`src/cook-web/src/app/AGENTS.md`，以及被修改目录下最近的 `AGENTS.md`。

优先复用这些现有代码：

- `src/api/flaskr/route/user.py`：SMS 登录 payload 和 post-auth context。
- `src/api/flaskr/service/user/post_auth.py`：post-auth extension contract。
- `src/api/flaskr/service/billing/subscriptions.py`：paid order activation 和 `grant_paid_order_credits`。
- `src/api/flaskr/service/billing/manual_plan_grants.py`：手动 paid-order 编排模式。
- `src/api/flaskr/common/public_urls.py`：公开 origin URL 构造。
- `src/api/flaskr/service/shifu/admin_operations/route.py`：运营 route namespace 模式。
- `src/cook-web/src/lib/request.ts` 和 `src/cook-web/src/lib/api.ts`：前端请求栈。
- `src/i18n/*/modules/operations-user.json` 和 billing i18n modules：现有运营文案风格。

不要修改已经应用过的 Alembic migration。Referral 表需要新增 migration。

## Plan of Work

1. 新增 referral backend domain scaffold 和 campaign-aware 数据库 schema。
2. 新增 campaign activation 和 reward-rule evaluation helpers。
3. 新增 invite profile、invite event 和 relation binding helpers。
4. 扩展 SMS 登录 post-auth context，并加入 referral post-auth handler。
5. 新增 billing referral plan reward helper，支持顺延和延后生效。
6. 新增老师侧 referral APIs。
7. 新增运营侧 referral APIs 和 read models。
8. 增加后端重点测试，覆盖 campaign config、关系绑定、cap、billing artifacts 和运营状态变更。
9. 增加老师邀请页和被邀请人落地页。
10. 增加运营 referral 监控 UI。
11. 重新生成 i18n/type surface，并运行验证。
12. 在 feature flag 后面完成 dev02 验证。

## Concrete Steps

### 步骤 1：创建后端 Referral Domain

文件：

- 新建 `src/api/flaskr/service/referral/AGENTS.md`。
- 新建 `src/api/flaskr/service/referral/__init__.py`。
- 新建 `src/api/flaskr/service/referral/consts.py`。
- 新建 `src/api/flaskr/service/referral/models.py`。
- 新建 `src/api/flaskr/service/referral/dtos.py`。
- 新建 `src/api/flaskr/service/referral/service.py`。
- 新建 `src/api/flaskr/service/referral/routes.py`。
- 新建 `src/api/tests/service/referral/`。

实现要求：

- 在 referral 域内定义本地 status/type constants，不放进 billing constants。
- 增加模型：
  - `ReferralCampaign`
  - `ReferralCampaignRewardRule`
  - `ReferralInviteCode`
  - `ReferralInviteEvent`
  - `ReferralInviteRelation`
  - `ReferralInviteReward`
- 遵循现有模型约定，使用 `String(36)` 业务 ID、soft delete、`SmallInteger` 状态字段和 JSON metadata。
- 增加 campaign code、campaign rule code、invite code 和 active invitee binding 的唯一约束。

验证：

- 从 `src/api` 生成新 Alembic migration。
- 手动检查 migration 的表名、索引和注释。
- 增加模型测试，插入 campaign、reward rule、invite code、relation、reward 行，并验证 invitee 唯一绑定约束。

### 步骤 2：实现 Campaign 和 Reward Rule Helpers

文件：

- 修改 `src/api/flaskr/service/referral/service.py`。
- 修改 `src/api/flaskr/service/referral/dtos.py`。
- 增加 `src/api/tests/service/referral/test_campaign_config.py`。

实现要求：

- 只加载 active、处于配置时间窗口内且 rollout flag 已打开的 campaign。
- 按 trigger event 和 priority 选择 active reward rules。
- 对首发规则评估配置化的邀请人和被邀请人资格。
- 返回 rule snapshot，包含 product code、cycle count、cap scope、cap count、credit amount、credit validity、timing policy 和 copy keys。
- seed 或文档化 dev02 验证用的首发 campaign row 和 reward-rule row。

验证：

- inactive、paused、expired 或 flag-disabled campaign 不生成可用邀请资料。
- 测试数据里修改 cap 后，奖励行为随配置变化，不需要改代码。
- 奖励产品期望不合法时，grant 前失败。

### 步骤 3：实现 Invite Code 和 Profile Helpers

文件：

- 修改 `src/api/flaskr/service/referral/service.py`。
- 修改 `src/api/flaskr/service/referral/dtos.py`。
- 增加 `src/api/tests/service/referral/test_invite_profile.py`。

实现要求：

- 生成不可变随机邀请码，按 campaign 隔离，并做碰撞重试。
- `GET /api/referral/invite-profile` 按当前 active campaign 懒创建邀请资料。
- 使用公开 origin helper 构造邀请链接，不硬编码 hostname。
- 返回已奖励数、剩余奖励数、cap 和奖励队列摘要。
- 邀请人侧响应不暴露被邀请人手机号或账号详情。

验证：

- 多次加载 profile 返回稳定的邀请码。
- 同一用户在不同 campaign 下可以拥有不同邀请码。
- 邀请链接使用配置或请求 public origin。
- disabled invite code 不作为可用 code 返回。

### 步骤 4：记录邀请事件

文件：

- 修改 `src/api/flaskr/service/referral/service.py`。
- 修改 `src/api/flaskr/service/referral/routes.py`。
- 增加 `src/api/tests/service/referral/test_invite_events.py`。

实现要求：

- 增加 `POST /api/referral/invite-event`。
- 接收 event type、invite code、landing path、frontend session id 和 entry source。
- 记录 invite link click、registration page view、manual invite-code entry 和 registration submit 事件。
- 能解析邀请码时，从邀请码解析 campaign 并保存 `campaign_bid`。
- 持久化前 hash IP 和 user agent。
- 只返回 success 状态和必要时生成的 referral session id。
- 匿名调用不得泄露邀请人账号数据。

验证：

- 有效邀请码能记录每种支持的 event type。
- 无效邀请码返回非识别性的通用错误或 no-op 响应，按设计选择实现。
- 不持久化原始 IP 和原始 user agent。

### 步骤 5：扩展 PostAuthContext 和 SMS 登录 Payload

文件：

- 修改 `src/api/flaskr/service/user/post_auth.py`。
- 修改 `src/api/flaskr/route/user.py`。
- 增加或更新 `src/api/tests/service/user/` 下测试。

实现要求：

- 在 `PostAuthContext` 增加可选 `invite_code`、`referral_session_id`、`referral_entry_source`、`client_ip_hash`、`user_agent_hash`。
- SMS 登录从 payload 读取 `invite_code`、`referral_session_id`、`referral_entry_source`。
- 路由只把 referral 字段传给 post-auth context，不直接绑定关系。
- 保持既有 temp-user 和 verification-code 行为。

验证：

- 既有 SMS 登录测试继续通过。
- 新测试确认 SMS 登录会把 referral metadata 传给 post-auth handlers。
- 链接带来的邀请码和手动输入的邀请码进入同一 post-auth 路径。
- 已有用户携带邀请码登录不会触发新绑定。

### 步骤 6：增加 Referral Post-Auth Handler

文件：

- 新建 `src/api/flaskr/service/referral/auth_hooks.py`。
- 确保该模块被 service extension 注册路径 import。
- 增加 `src/api/tests/service/referral/test_post_auth_binding.py`。

实现要求：

- 注册 `run_post_auth_extensions` extension。
- 只在 `created_new_user = true` 且存在 invite code 时执行。
- 拒绝自邀请。
- 从 invite code 加载 campaign 和 reward rule，并评估配置化 eligibility 与 cap。
- 每个 invitee 创建一个 active relation。
- 按配置的 cap scope 统计既有 reward。
- 未达到 cap 时创建 reward row。
- 超过 cap 的有效邀请标记为 skipped，不产生 billing side effects。
- Referral 处理错误不能导致登录失败；日志必须包含足够 BID 供修复。

验证：

- 新被邀请用户创建 relation 和 reward。
- 已有用户登录不创建 relation。
- 重复 post-auth 重试返回既有 relation/reward。
- 超过 cap 的邀请创建 skipped 状态 relation。

### 步骤 7：增加 Billing Referral Plan Reward Helper

文件：

- 新建 `src/api/flaskr/service/billing/referral_plan_rewards.py`。
- 修改 `src/api/flaskr/service/billing/api.py` 导出 helper。
- 增加 `src/api/tests/service/billing/test_referral_plan_rewards.py`。

实现要求：

- 从 reward rule snapshot 加载 reward product。
- Grant 前验证 product 是 active plan，且符合配置的活动期望。
- 创建幂等 `manual + paid` billing order，provider reference 为 `referral-reward:{reward_bid}`。
- 使用 metadata `checkout_type = referral_invitation_reward`。
- 在 billing metadata 中包含 campaign 和 reward-rule BID。
- 复用 `grant_paid_order_credits`。
- 无任何有效权益窗口时立即生效。
- 邀请人当前为免费或试用套餐时，奖励排到当前权益结束后生效，不提前叠加到当前周期可用积分。
- 当前同款自营订阅使用 reward product 时，同套餐顺延。
- 更高级套餐或年套餐结束后延后生效。
- 首发奖励保持配置的 30 天 credit-bucket 过期语义。
- 返回 subscription、order、wallet bucket、ledger BID 给 referral service。

验证：

- 无订阅用户立即得到 active reward。
- 同一 reward 重复调用幂等。
- 免费或试用套餐用户的邀请奖励先进入 reserved renewal 队列，到期事件执行后才释放为下一周期 available。
- 已有同套餐订阅顺延一个周期。
- 已有更高级套餐或年套餐保持当前付费套餐，记录 deferred reward。
- 首发奖励创建 1000 积分 bucket，并在 30 天周期边界过期。
- Ledger/order metadata 包含 relation 和 reward BID。

### 步骤 8：将 Reward Artifacts 写回 Referral Rows

文件：

- 修改 `src/api/flaskr/service/referral/service.py`。
- 增加 `src/api/tests/service/referral/test_reward_generation.py`。

实现要求：

- Billing grant 成功后，更新 `referral_invite_rewards` 的 billing artifact BID、effective windows、campaign snapshot、reward-rule snapshot、credit amount 和 credit expiry。
- Relation 创建后 billing grant 失败时，reward 保留为可修复的 pending/failed 状态，并写入 error metadata。
- 增加 repair helper，扫描 pending reward rows 并重试 billing grant。

验证：

- 成功 reward row 关联 billing artifacts。
- Billing 调用失败时 relation 保留且 reward 可重试。
- Repair helper 修复 pending reward 时不重复创建 relation 或 order。

### 步骤 9：增加老师 Referral APIs

文件：

- 修改 `src/api/flaskr/service/referral/routes.py`。
- 确保 route 注册到 `/api/referral`。
- 增加 `src/api/tests/service/referral/test_referral_routes.py`。

实现要求：

- `GET /api/referral/invite-profile` 需要登录用户。
- `POST /api/referral/invite-event` 支持匿名使用。
- 响应使用共享 response envelope。
- 增加 feature flag 检查，默认可禁用。

验证：

- 已登录用户 profile 返回 invite code 和 link。
- Profile 响应包含 campaign code、配置 cap、剩余奖励数和规则文案 key。
- 未登录 profile 被拒绝。
- Event endpoint 不需要登录。
- Event endpoint 记录手动输入邀请码时不暴露邀请人账号数据。
- Feature disabled 时返回配置好的 disabled error 或 no-op。

### 步骤 10：增加运营 Referral APIs

文件：

- 修改 `src/api/flaskr/service/shifu/admin_operations/route.py`，或在该 namespace 下增加独立 referral route module，避免单文件过大。
- 在 `src/api/flaskr/service/referral/` 下增加 referral read model helpers。
- 按现有模式，在 `src/api/flaskr/service/referral/dtos.py` 或 `src/api/flaskr/service/shifu/admin_dtos.py` 增加 DTO。
- 增加 `src/api/tests/service/referral/` 测试，以及 `src/api/tests/service/shifu/` 下 route permission 测试。

实现要求：

- 增加 overview metrics route。
- 增加 relation list route，支持 campaign、邀请人 keyword、被邀请人 keyword、reward status、abnormal status、创建时间筛选。
- 增加 relation detail route，包含 billing artifacts。
- 增加带审计的 relation adjustment route，用于少数注册后纠正或取消关系的场景。
- 增加 abnormal reviewing、cancel、freeze、note 的状态更新 route。
- 真实访问控制使用现有 operator permission guard。

验证：

- 非运营用户被拒绝。
- 运营可以 list、filter、查看详情、更新异常状态，并记录带备注的关系调整。
- Overview 包含 clicks、registration page visits、invited registrations、capped inviters、reward months、abnormal counts、invited-user usage、invited-user credit consumption、invited-user paid conversion。
- 状态更新不删除 billing truth。

### 步骤 11：增加前端 API 和 Types

文件：

- 修改 `src/cook-web/src/api/api.ts`。
- 在现有前端 API 层创建或修改 referral API wrappers。
- 如果拆分更清晰，增加 `src/cook-web/src/types/referral.ts`。
- 更新 `src/i18n/zh-CN`、`src/i18n/en-US`、`src/i18n/fr-FR` 下 JSON。

实现要求：

- 复用共享 request stack。
- 增加 creator invite profile 和 invite-event endpoints。
- 增加 operator referral endpoints。
- 所有用户可见文案放进 i18n JSON。

验证：

- API endpoint string 测试包含新 routes。
- TypeScript type-check 通过。

### 步骤 12：增加老师邀请页

文件：

- 在 `src/cook-web/src/app/admin/` 的老师/后台区域增加 route。
- 组件放在 route 附近；如果会复用，再放到 `src/cook-web/src/components/`。
- 只更新现有老师/后台导航路径。
- 增加页面渲染和复制动作测试。

实现要求：

- 展示邀请链接、邀请码、复制动作、活动规则文案、已奖励数、剩余奖励数、队列摘要和 cap 状态。
- 付费权益优先导致奖励待生效时，说明“已获得但待生效”。
- 不展示被邀请人隐私数据。
- 使用与 billing/operations 页面一致的克制后台样式。

验证：

- 页面覆盖 loading、success、empty、disabled、cap 状态。
- 复制动作使用生成的链接。
- 所有文案通过 i18n 解析。

### 步骤 13：增加被邀请人落地页

文件：

- 在 `src/cook-web/src/app/` 下增加 invite route。
- 在注册前流程增加手动输入邀请码入口。
- 修改现有 login/SMS 调用点，携带保存的 invite code 和 referral session id。
- 增加 payload 传递测试。

实现要求：

- 从 route/query 读取 invite code。
- 同一 referral session 下记录一次邀请链接点击和注册页访问。
- SMS 登录前接受手动输入邀请码，并记录 code-entry 事件。
- SMS 登录时保留 invite code。
- 不展示额外被邀请人奖励承诺。

验证：

- 落地页保存 invite context。
- 手动输入邀请码保存的 invite context 与链接入口一致。
- SMS 登录 payload 包含 invite code。
- 登录成功后清理 stale invite context。

### 步骤 14：增加运营 Referral UI

文件：

- 增加 `src/cook-web/src/app/admin/operations/referrals/` 页面。
- 更新 operations 菜单 route/nav。
- 在新页面附近增加测试。

实现要求：

- 展示 campaign-aware overview metrics、filters、table、pagination、detail sheet 和 abnormal status actions。
- 展示被邀请人注册时间、手机号、账号 ID、奖励状态、生效队列和 billing artifacts。
- 如果已有用户详情和 billing artifacts 路由，关系行链接到这些现有页面。
- 表格保持密集且与现有 operations 页面一致。

验证：

- Operator guard 生效。
- 筛选项调用预期 API params。
- Detail sheet 展示 relation、invitee 和 billing artifact 字段。
- Overview metrics 与飞书活动统计清单一致。
- 状态动作确认后发送预期 payload。

### 步骤 15：增加修复/诊断 helper

文件：

- 在 `src/api/flaskr/service/referral/service.py` 下增加 `retry_pending_referral_rewards`。
- 对 billing grant 失败后保留 relation/reward 行并通过 dry-run/retry 修复的路径增加测试。

实现要求：

- 扫描 pending/failed reward rows。
- 幂等重试 billing grant。
- 打印 relation、reward、order、ledger 和 error 字段。
- 支持 dry-run。
- v1 先提供 service helper；如果需要在环境里批量执行，再接入现有 CLI command surface。

验证：

- Dry run 报告 pending rewards 且不写数据。
- Retry 修复一个 pending reward 时不重复创建 billing rows。

## Validation and Acceptance

后端验收：

- Active campaign 和 reward-rule config 控制 eligibility、cap、reward product、credit validity 和 timing policy。
- 邀请链接和手动输入邀请码在 SMS 注册前进入同一个绑定路径。
- 新 SMS 注册 invitee 为邀请人创建一个 relation 和一个 reward。
- 首发活动中，前 12 个有效邀请产生 12 个奖励月。
- 首发活动中，第 13 个有效 invitee 继续注册并绑定，但不创建自动 billing reward。
- 配置较小 cap 的测试活动会在该 cap 处跳过，不需要改代码。
- Reward billing artifacts 可在 `bill_orders`、`bill_subscriptions`、`credit_wallet_buckets`、`credit_ledger_entries` 中看到。
- 首发 reward bucket 每 30 天周期发放 1000 积分；有当前权益窗口时先 reserved，到周期边界释放为当期 available，并在周期结束时过期未用积分。
- 已有用户不会被邀请链接重新绑定。
- 被邀请账号不会获得 referral-specific 额外福利。
- 运营 API 可以追踪邀请人、被邀请人、relation、reward、order、subscription、bucket 和 ledger。
- 运营 overview 可以通过 referral events 加现有 billing/usage 表报告活动漏斗和下游使用/转化指标。

前端验收：

- 老师邀请页展示邀请码、链接、复制动作、奖励数量、待生效状态和 cap 文案。
- 邀请落地页和手动输入邀请码入口都能把 invite context 传到 SMS 登录。
- 运营 referral 页面支持列表、筛选、详情和异常动作。
- 用户可见文案都在共享 i18n JSON。

命令：

- `python scripts/build_repo_knowledge_index.py`
- `python scripts/check_repo_harness.py`
- `cd src/api && pytest tests/service/referral/ tests/service/user/ tests/service/billing/ -q`
- `cd src/cook-web && npm run type-check`
- `cd src/cook-web && npm run lint`

Dev02 验证：

- 只有在 reward product code 已配置且验证后，才启用 referral feature flag。
- Seed dev02 的首发 campaign 和 reward-rule rows。
- 跑邀请链接注册合成用例。
- 跑手动输入邀请码注册合成用例。
- 查询 dev02 DB 的 relation、reward、billing order、subscription、wallet bucket 和 ledger。
- 查询 dev02 event rows，确认 link click、registration page visit、manual code entry、registration submit 都落表。
- 确认老师邀请页和运营 referral 页面展示同一份奖励状态。

## Idempotence and Recovery

- 邀请码生成唯一且不可变。重复 profile 调用返回同一个 code。
- 邀请码按 campaign 生成，因此活动配置变化不需要重写已有 invite rows。
- 对不应重复计数的 event type，邀请事件记录按 frontend session 幂等。
- 关系绑定使用唯一 invitee key。重复 post-auth 调用返回既有 relation。
- 奖励生成每个 relation 一个 reward row，并保存 campaign/rule 快照以便修复。
- Billing grant 使用 provider reference `referral-reward:{reward_bid}` 和 ledger idempotency `grant:{bill_order_bid}`。
- Billing 副作用失败时保留 pending/failed reward rows 供修复。
- 修复命令幂等，并打印所有相关业务 ID。
- 异常状态更新保留原始行并记录运营备注。

## Interfaces and Dependencies

后端：

- 新增 campaign-aware referral tables 和 Alembic migration。
- 首发 campaign 与 reward-rule seed，或文档化运营配置步骤。
- 新增 `/api/referral` 老师/匿名 endpoints。
- 新增 `/api/shifu/admin/operations/referrals` 运营 endpoints。
- 扩展 `PostAuthContext` 可选字段。
- 新增 referral plan rewards billing helper。
- Referral event table 覆盖 link clicks、registration page views、manual code entry、registration submit。
- Feature flag 加数据库 campaign/reward-rule 配置。环境配置可以保存默认 launch campaign code，但业务值应在 `referral_campaigns` 和 `referral_campaign_reward_rules`。

前端：

- 老师邀请页。
- 被邀请人落地页。
- 注册前手动输入邀请码入口。
- 登录 payload 传递。
- 运营 referral 页面。
- 共享 i18n 增量。

运营：

- 配置的 reward product 必须代表预期 199 元月奖励。
- Campaign 变更应作为数据变更审计，不隐藏在代码常量里。
- Dev02 发布验证必须检查真实 DB 状态，不只看测试。
- 现有运营手动 `referral_reward` grant 继续可用，不能被静默改造成自动邀请奖励。

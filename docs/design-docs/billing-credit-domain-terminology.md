---
title: Billing Credit Domain Terminology
status: accepted
owner_surface: backend
last_reviewed: 2026-07-29
canonical: true
---

# Billing Credit Domain Terminology

## 目的

本文定义 AI-Shifu 积分与计费体系的产品术语、代码映射和 Billing-R
重构边界。本文的产品定义以以下本地资料为依据：

- `积分术语表.md`
- `积分变更审计.md`
- `AI-Shifu 套餐订购与预购方案.md`
- `AI-Shifu-积分系统代码审查与重构建议-2026-07-27.md`

本文优先表达产品规则，再单独说明当前代码映射。后续代码重构不得把当前
实现细节反向解释成产品规则。

## 产品术语

| 产品术语 | 英文术语 | 产品定义 | 当前代码映射 |
| --- | --- | --- | --- |
| 积分 | Credits | 平台虚拟货币。老师购买、获得并消耗积分。 | `CreditLedgerEntry.amount`、bucket 积分字段、wallet 快照字段 |
| 积分账户 | Credit Account | 存放老师所有积分的账户。 | `CreditWallet`。代码暂保留 `Wallet` 命名，不做大规模重命名。 |
| 积分桶 | Credit Bucket | 当前实现中承载一批积分来源、余额、可用窗口和消费优先级的技术投影。 | `CreditWalletBucket` |
| 账本 | Ledger | 积分变动审计记录。 | `CreditLedgerEntry`。长期方向是 append-only ledger，加显式 grant/allocation 状态。 |
| 积分套餐 | Plan | 面向老师的周期性订阅商品。每个周期提供套餐积分。 | `BillingProduct.product_type=plan`、subscription order、subscription bucket |
| 积分包 | Credit Pack | 一次性购买的积分商品。积分包积分不因订阅失效而过期。 | `BillingProduct.product_type=topup`、topup order、topup bucket |
| 订阅 | Subscription | 老师与积分套餐之间的合同关系。 | `BillingSubscription` |
| 续订 | Renew | 购买同档下一周期。 | renewal order、renewal event |
| 升级 | Upgrade | 切换到高档套餐。立即升级时旧套餐剩余积分合并到新套餐周期。 | `subscription_upgrade` order、preorder absorption path |
| 降级 | Downgrade | 预购低档套餐，到当前周期结束后生效。 | preorder metadata、downgrade effective renewal event |
| 预购 | Pre-order | 提前购买下一周期套餐。续订和降级均可作为预购生效。 | paid order with preorder metadata |
| 自动续订 | Auto-renew | 系统自动续订。 | renewal task / provider renewal settings |

中文产品文档和用户文案中不应把“老师”泛称为“创作者”，不应把“积分包”称为
“充值包”，不应把“续订”称为“续费/续购”。

## 积分类型

| 积分类型 | 产品规则 | 当前代码映射 |
| --- | --- | --- |
| 套餐积分 | 与当前套餐周期绑定。周期结束未用完的套餐积分过期，不累计到下个周期。立即升级时，旧套餐剩余积分合并到新套餐周期。赠送积分如果来自 0 元套餐订单，本质上也是套餐积分。 | `CREDIT_BUCKET_CATEGORY_SUBSCRIPTION` |
| 积分包积分 | 一次性购买后进入积分账户。积分包积分本身不过期；没有有效积分套餐时冻结/不可消耗；恢复有效积分套餐后解冻/恢复可消耗。 | `CREDIT_BUCKET_CATEGORY_TOPUP` |

正常付费用户的消耗顺序是：

```text
套餐积分 -> 积分包积分
```

试用/历史免费积分属于实现兼容点，不是新的产品主分类。当前新老师试用
bootstrap 写入 subscription-category bucket；历史 `free` bucket 仍可能存在，
后续审计或迁移时必须按实际持久化类别识别。

## 积分生命周期与审计动词

| 生命周期动词 | 产品含义 | 审计展示方向 | 当前实现落点 |
| --- | --- | --- | --- |
| 充值 | 积分进入老师的积分账户。 | 正向变动，如购买积分套餐、购买积分包。 | grant ledger、bucket available/reserved 增加、wallet snapshot 刷新 |
| 消耗 | 使用积分完成学习、调试或预览中的任务。 | 负向变动，关联操作人和具体操作。 | usage settlement、consume ledger、bucket consumed 增加 |
| 过期 | 套餐周期结束后，未用完的套餐积分过期。 | 负向系统变动。 | expire ledger、subscription bucket available 减少、expired 增加 |
| 冻结 | 没有有效积分套餐时，积分包积分不可用。冻结不是扣除，余额仍归老师所有。 | 可展示为不可用/冻结状态，不应减少拥有的积分包余额。 | 当前主要由 eligibility/admission 投影表达，尚无独立 frozen mutation。 |
| 解冻 | 恢复有效积分套餐后，积分包积分恢复可用。 | 可展示为恢复可用状态，不应重复充值。 | 当前主要由 eligibility/admission 投影表达，尚无独立 unfrozen mutation。 |
| 退还 | 任务失败或纠正时返还积分。 | 正向变动，尽量关联原消耗记录。 | refund ledger、bucket/wallet adjustment path |
| 合并 | 立即升级时，旧套餐剩余积分并入新套餐周期。 | 正向或 realignment 事件，体现升级透明度。 | upgrade transition、bucket realignment、grant/expire handling |

用户购买入口不使用 top-up / recharge 语义；但“充值”可以用于生命周期和审计语境，
表示积分已经进入积分账户。

## 套餐订购与预购积分规则

- 新购积分套餐：支付成功后立即开始新订阅周期，并充值该周期套餐积分。
- 续订预购：当前周期不变；到期切换时旧周期套餐积分过期，新周期套餐积分充值。
- 降级预购：当前周期不变；到期切换时旧周期套餐积分过期，新套餐周期开始。
- 立即升级：新套餐立即生效，旧套餐剩余积分合并到新套餐周期。
- 积分包：独立购买；是否可消耗取决于当前是否存在有效积分套餐。

## 当前实现映射与重构注意事项

当前系统会用多张表共同表达一份积分事实：

| 实体 | 当前职责 | 重构注意事项 |
| --- | --- | --- |
| `BillingOrder` | 支付和购买事实，包括预购 metadata。 | 继续作为 paid evidence 和订单快照来源。 |
| `BillingSubscription` | 当前套餐合同和周期窗口。 | 周期推进应逐步收口到统一 transition service。 |
| `BillingRenewalEvent` | 周期边界任务、续订、重试和补偿事件。 | 终态事件不得被普通 lifecycle sync 覆盖。 |
| `CreditWallet` | 积分账户的 available/reserved 快照。 | 这是投影，必须能由 bucket/allocation 重新计算。 |
| `CreditWalletBucket` | 当前实现的余额、来源、有效窗口和优先级投影。 | 长期方向是 allocation/cycle 更清晰，避免跨订单/跨周期复用。 |
| `CreditLedgerEntry` | 审计流水，同时临时承载部分 grant 当前状态。 | 长期方向是 ledger append-only，当前状态迁出到显式模型。 |

积分包冻结/解冻是后续 R3/R5 的重要边界：产品规则是积分包积分不过期，
订阅失效时只是冻结。当前代码中 topup bucket 仍可能带有 subscription-window
字段；后续修改周期过期、bucket expiration 或 allocation 模型时，必须把这些字段
视为可消费资格窗口，而不是积分包所有权过期。由于当前没有确认真实线上错账风险，
该项并入 R3/R5，不单独作为当前 correctness PR。

Runtime admission 当前语义应保持：

- `server.billing.creditInsufficient`：没有任何处于有效期内、可消费且余额大于 `0` 的 bucket。
- `server.billing.subscriptionInactive`：没有有效订阅，但存在仍有余额且需要有效订阅才能消费的 bucket，例如套餐积分或积分包积分。

## Billing-R 重构边界

Billing-R 系列必须按可独立合入的小 PR 推进。每个 PR 合入后都必须保持系统安全，
不能留下“必须等下一个 PR 才正确”的中间状态。

### R0：术语与领域边界

- 定义产品术语和当前代码映射。
- 明确哪些代码命名暂不重命名。
- 明确审计和后续 allocation/ledger 方向。
- 不改变 runtime 行为。

### R1：Credit Mutation / Grant Transition

- 引入低层积分状态转换 helper。
- 返回结构化结果，包括 expected amount、moved amount、completed、failure reason。
- 先迁移 reserved grant activation 等小路径，再逐步覆盖 reserve、void、absorb、expire、refund、consume。
- 除非单独说明，不改变事务归属和业务行为。

### R2：不变量审计与诊断

- 先建立只读诊断模型，不继续扩散事故专用 repair。
- 覆盖 wallet/bucket 汇总不一致、bucket 金额不守恒、overdue reserved grant、expire projection drift、subscription-cycle/bucket-window mismatch。
- 证据不足的异常进入 manual review，不自动修复。

### R3：Cycle Transition

- 统一 subscription 周期推进、due reserved grants 激活、旧周期套餐积分过期、积分包冻结/解冻资格、renewal event 终态。
- 按调用入口逐步迁移，避免 renewal 和 repair 走出不同语义。

### R4：事务与并发协议

- 明确事务归属、锁顺序、可重试冲突和 fail-closed 场景。
- MySQL 双会话并发测试、deadlock retry、wallet CAS retry、settlement lock 行为统一归入这里。

### R5：Allocation Model And Append-Only Ledger

- 引入显式 `CreditGrant` 或 `CreditAllocation` 状态。
- 把 grant 当前状态从 ledger metadata 中迁出。
- 新 allocation 不再依赖 subscription-aligned `effective_to` 表达积分包所有权过期。
- 停止新数据跨订单、跨周期复用 pooled bucket。
- 历史 pooled bucket 保持兼容读取，不一次性迁移全部历史。

## 测试要求

| 变更类型 | 验证要求 |
| --- | --- |
| R0 docs-only | `python scripts/check_repo_harness.py` 和文档 review。 |
| 行为不变 helper 抽取 | targeted billing tests + full `tests/service/billing/`。 |
| 真实写路径迁移 | 对应业务回归、full billing tests；如影响 repair 候选，再跑 dry-run。 |
| 周期转换变更 | 续订、预购、升级、过期、campaign bonus、referral renewal、repair dry-run/apply 回归。 |
| 数据模型变更 | migration review、兼容读、dual-write/backfill 计划、合入后 dry-run/audit。 |

## 非目标

- 不一次性重写 billing。
- 不立即把所有 `Wallet` 符号重命名为 `Account`。
- 不把 Event Sourcing 作为第一步。
- 不一次性迁移全部历史 ledger 和 bucket。
- 不把 Redis 锁作为最终正确性保障。
- 不对证据不足的数据做自动修复；必须进入 manual review。

# 运营任务优先级总表（本地）

> 本文件只排优先级，不展开需求明细。具体方案、字段、验收点继续看：
> - `.codex-local/operator-management-optimization-plan.md`
> - `.codex-local/需求和优化.md`

更新时间：2026-06-16
当前状态：最新 `main` 已包含 PR 1851、1852、1853、1854、1855、1857、1858、1861、1863、1869、1877，以及订单页首轮瘦身和运营用户详情页首轮瘦身。`P0` 追问页剩余体验收口已完成待合入，创作者兑换码后续结构与性能优化已在分支 `refactor/streamline-creator-redemption-code-admin-flows` 完成待合入。

## 排期原则

- 先做已确认有遗留价值、范围清晰、能独立成 PR 的任务。
- 优先收口运营主流程里的体验缺口，再做更大范围的结构抽象。
- 先处理已有代码遗留风险，再做新增能力或长期通用化。
- 观察型任务后置，避免和明确收益的优化项争抢优先级。

## P0：下一步最适合直接开工

| 顺序 | 任务 | 建议分支 / PR | 来源 |
| --- | --- | --- | --- |
| 0 | 创作者兑换码后续结构与性能优化 | `refactor/streamline-creator-redemption-code-admin-flows` | `.codex-local/operator-management-optimization-plan.md`：创作者兑换码遗留风险 |

## P1：近期应继续排队的结构 / 规则任务

| 顺序 | 任务 | 建议分支 / PR | 来源 |
| --- | --- | --- | --- |
| 1 | 活动 / 兑换码 `ops_state` 规则共享化 | `refactor/promotion-ops-state-rules` | `.codex-local/需求和优化.md`：运营后台通用能力沉淀 |
| 2 | 积分通知页后续性能和体验项 | `feat/operator-credit-notification-followups` | `.codex-local/需求和优化.md`：积分通知页后续优化记录 |
| 3 | 创作者数据看板追问详情轻量缓存观察项 | `feat/creator-dashboard-followup-cache-observe` | 旧 roadmap 观察项 + `.codex-local/需求和优化.md` |

## P2：中后期效率能力

| 顺序 | 任务 | 建议分支 / PR | 来源 |
| --- | --- | --- | --- |
| 4 | 活动关联订单导出 | `feat/operator-promotion-order-export` | `.codex-local/需求和优化.md`：活动与兑换码页导出能力 |
| 5 | 兑换码使用记录导出 | `feat/operator-coupon-usage-export` | `.codex-local/需求和优化.md`：活动与兑换码页导出能力 |
| 6 | 一单一码子码按筛选结果导出 | `feat/operator-coupon-code-export` | `.codex-local/需求和优化.md`：活动与兑换码页导出能力 |

## P3：长期通用化 / 可选优化

| 顺序 | 任务 | 建议分支 / PR | 来源 |
| --- | --- | --- | --- |
| 7 | 后台页面通用化优化计划（搜索字段 builder / 列表状态 hook / 概览卡片行为统一） | 待定 | `.codex-local/admin-shared-ui-unification-plan.md` |
| 8 | 创作者课程下拉远程搜索 | `feat/creator-redemption-course-search` | `.codex-local/operator-management-optimization-plan.md`：创作者兑换码遗留风险 |
| 9 | 子码后端文件导出接口 | `feat/creator-redemption-export-api` | `.codex-local/operator-management-optimization-plan.md`：创作者兑换码遗留风险 |

## 最近已完成，可不再作为优先级候选

- 课程管理服务拆分：PR 1877 已合入 main。
- 运营用户详情页首轮瘦身：已落在最新 main。
- 订单页首轮瘦身：已落在最新 main。
- 运营搜索区统一。
- 运营表格、空态、更多菜单统一。
- 运营时间选择组件统一。
- 课程基础定价按站点 / 支付渠道配置化。
- 运营大页面首轮拆文件。
- 促销活动主列表 tab 拆分。
- 运营用户管理积分列。
- 运营用户管理积分发放。
- 用户积分明细补充课程 / 消耗类型 / 消耗场景。
- 用户积分明细 SQL 分页筛选优化。
- 活动 / 兑换码细筛选。
- 活动 / 兑换码启停确认和编辑态规则说明。
- 运营后台分页增强组件。
- 运营后台搜索区布局骨架组件。
- 运营后台概览卡片骨架组件。
- 追问页剩余体验收口：已完成，PR 1923 已提。

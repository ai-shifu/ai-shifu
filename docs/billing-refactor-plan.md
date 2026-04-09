# Billing Refactor Plan

更新日期：2026-04-09

## 目标

- 保留当前已经可用的 billing 能力和对外 contract，不为了回退到旧 MVP 叙述而强行删除现有功能。
- 收口范围，明确哪些能力是 `active`、`default_disabled`、`internal_only`。
- 拆分 billing 超大文件，禁止子模块继续跨文件依赖 `_private` helper。
- 删除无调用残留、重复拼装逻辑和低价值源码文本断言测试。

## 当前执行原则

- 代码存在且有真实 creator/admin/runtime 入口的能力继续保留。
- 默认配置关闭或不进入主路径的能力保留代码，但必须在 capability manifest 和 UI 上明确标识为 `default_disabled`。
- task / CLI / 运维补偿能力归类为 `internal_only`。
- 没有调用点、没有路由、没有 task、没有 CLI 引用的残留直接删除。

## 执行分期

### Phase 1: Capability Truth Source

- [x] 新增统一的 billing capability registry。
- [x] 为 `GET /api/billing` 增加 `capabilities` 返回字段。
- [x] 前端接入 bootstrap/capability 类型与状态展示。
- [ ] 在 creator/admin UI 上补齐更完整的能力状态说明与测试。
- [x] 将本次收口计划迁移到仓库根 `tasks.md`。

### Phase 2: Backend File Split

- [x] 抽出 `charges.py` 并让 aggregate/settlement 复用公开函数。
- [x] 拆出 `queries.py`，承载 loader、pagination、filter normalizer。
- [x] 拆出 `serializers.py`，承载 creator/admin DTO 序列化与状态映射。
- [x] 拆出 `read_models.py`，承载 overview、wallet、ledger、orders、reports、admin list builders。
- [x] 拆出 `trials.py`，承载 new creator trial 逻辑。
- [x] 拆出 `checkout.py`，承载 checkout / refund / sync / reconcile。
- [x] 拆出 `subscriptions.py`，承载 subscription lifecycle、renewal event、grant/apply。
- [x] 拆出 `webhooks.py`，承载 Stripe/Pingxx billing webhook 处理。
- [x] 改写 `routes.py`、`tasks.py`、`cli.py`、`renewal.py`、`callback.py`、`order/funs.py` 的 import，去掉对 `_private` helper 的跨模块依赖。
- [x] 将 `funcs.py` 压缩为兼容导出层，并控制在 1200 行以内。
- [x] 将 shared scalar/date/json helper 收敛到 `primitives.py`，并移除 duplicated loader/value wrapper。

### Phase 3: Frontend/Test Cleanup

- [x] 拆分 `BillingOverviewTab.tsx` 为容器和展示组件。
- [x] 删除未使用的 `BillingPlaceholderSection`。
- [x] 清理 billing 前端无意义 re-export 和多余 memoization。
- [x] 将源码文本断言测试替换为 route/url_map/行为测试。
- [x] 合并 billing 相关 migration 为 core/extension 两阶段。

## 非目标

- 不修改当前 active route 的响应语义和主要 DTO 字段。
- 不引入新的 billing 专属万能 abstraction。
- 不为了“看起来更小”而移除已经接入并可用的 creator/admin 功能。

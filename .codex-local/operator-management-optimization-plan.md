# 运营管理优化计划（本地文档）

> 本文档仅用于本地跟踪，不提交远端。后续每完成一个 PR，都先回查本文件，确认对应任务是否完成，再进入下一项。
> 通用需求与优化池已移到 `.codex-local/需求和优化.md`，后续本地需求类记录优先集中放在 `.codex-local/` 下。

## 当前分支背景

- 起始分析分支：`feat/operator-management-optimization-audit`
- 目标范围：运营管理全部页面与相关前后端能力
- 运营管理入口：后台侧边栏 `运营管理`
- 当前插队功能分支：`feat/creator-course-redemption-codes`
- 插队功能范围：创作者订单页新增课程兑换码创建和列表入口，并补充运营优惠活动创建者展示。

## 总体原则

- 优先低风险、展示层统一；后做后端拆分和性能优化。
- 每个 PR 尽量只解决一类问题，避免展示、业务、后端重构混在一起。
- 每完成一个 PR，必须回查本文档：
  - 对应任务是否完成
  - 是否有遗留项
  - 是否需要新增后续优化项
- 本地文档不提交远端，除非用户明确要求。

## 当前优先级（2026-06-16）

> 当前排期以 `.codex-local/operator-task-priority-roadmap.md` 为主，这里只保留摘要，方便从总计划文档直接回查。

1. `P0` 创作者兑换码后续结构与性能优化（当前分支已完成，待合入）
2. `P1` 活动 / 兑换码 `ops_state` 规则共享化
3. `P1` 积分通知页后续性能和体验项
4. `P1` 创作者数据看板追问详情轻量缓存观察项
5. `P2` 活动与兑换码导出能力
6. `P3` 后台页面进一步通用化抽象

## PR 1：搜索区统一

- 建议分支名：`feat/operator-admin-filter-unification`
- 优先级：最高
- 风险：低
- 目标：统一运营管理搜索区，不改业务逻辑。

### 任务清单

- [x] 课程管理搜索区接入或对齐 `AdminFilter`
- [x] 用户管理搜索区接入或对齐 `AdminFilter`
- [x] 订单管理搜索区接入或对齐 `AdminFilter`
- [x] 优惠/活动管理搜索区接入或对齐 `AdminFilter`
- [x] 积分通知管理搜索区接入或对齐 `AdminFilter`
- [x] 抽公共可清空输入框，替代页面内重复 `ClearableTextInput`
- [x] 统一搜索、重置、展开、收起按钮样式和布局
- [x] 统一字段 label 宽度、行距、第二行对齐
- [x] 保持接口参数、请求时机、筛选逻辑不变

### 自查遗留

- [x] 课程详情子页面局部 `ClearableTextInput` 已替换为 `AdminClearableInput`，并一并覆盖课程积分消耗、用户积分流水里的复用入口。
- [x] `AdminFilter` 对 label 冒号和三列布局已改成运营页面显式启用，避免影响后台订单页、数据看板等既有使用方。

### 验收重点

- [x] 搜索结果与改造前一致
- [x] 重置逻辑与改造前一致
- [x] 展开/收起布局在各页面一致
- [x] 输入框和日期组件均支持清空
- [x] CN/COM 联系方式文案口径不被破坏

## PR 2：表格、空态、更多菜单统一

- 建议分支名：`feat/operator-admin-table-actions-unification`
- 优先级：高
- 风险：中低
- 目标：统一运营管理表格和行操作展示，减少重复拼装。

### 任务清单

- [x] 强化 `AdminTableShell`，支持 sticky 操作列空态
- [x] 避免页面手写易漂移的 `emptyColSpan`
- [x] 统一 loading、empty、footer、pagination 展示
- [x] 抽公共 `AdminRowActions` 或 `AdminMoreMenu`
- [x] 替换重复的 `DropdownMenu + MoreHorizontal`
- [x] 统一表格内 tooltip、省略、hover 展示
- [x] 统一操作列宽度、固定列阴影、hover 样式

### 自查遗留

- [x] 主运营列表和课程/用户详情页的 `emptyColSpan` 已改为列配置或命名常量，动态列保留显式命名常量。
- [x] 主运营列表、订单 tab、课程详情 tab 的分页优先走 `AdminTableShell.pagination`，弹窗分页也通过同一入口配置。
- [x] 主运营列表的更多菜单已统一接入 `AdminRowActions`，保留各菜单项的禁用/隐藏业务条件。
- [x] 表格文本省略继续复用 `AdminTooltipText`，sticky 操作列空态统一沉淀到 `AdminTableShell.stickyActionEmpty`。

### 验收重点

- [x] 空态列数不再依赖魔法数字
- [x] 更多菜单样式一致
- [x] 菜单禁用态、loading 态清晰
- [x] 表格 tooltip 展示一致
- [x] 用户、课程、订单、活动、积分通知页面无明显 UI 回归

## PR 3：时间选择组件统一

- 建议分支名：`feat/operator-admin-time-picker-unification`
- 优先级：中
- 风险：低到中
- 目标：把积分通知里的业务时间选择组件沉淀为可复用的运营后台时间选择组件。

### 任务清单

- [x] 评估 `CreditNotificationQuietTimeSelect` 是否适合泛化
- [x] 抽通用运营后台时间选择组件
- [x] 保持积分通知短信配置页现有业务行为不变
- [x] 统一时间选择器视觉、hover、选中态和对齐
- [x] 补充或调整对应前端测试

### 自查遗留

- [x] 积分通知免打扰时间选择已改用 `AdminTimeSelect`，原页面私有 `CreditNotificationQuietTimeSelect` 已删除。
- [x] 优惠码/兑换码活动开始、结束时间弹窗内的原生 `type="time"` 已替换为同一 `AdminTimeSelect`。
- [x] 促销活动开始/结束时间的日期范围与确认按钮禁用逻辑保持不变；本 PR 仅统一时间输入视觉和选择方式。

### 验收重点

- [x] 积分通知免打扰时间配置行为不变
- [x] 默认选中时间正确
- [x] 组件样式与运营后台一致
- [x] 没有引入搜索区或表格无关改动

## PR 4：运营大页面拆文件

- 建议分支名：`refactor/operator-management-page-split`
- 优先级：高
- 风险：低到中
- 目标：降低大文件维护和 review 成本，不改业务逻辑。

### 任务清单

- [x] 拆 `src/cook-web/src/app/admin/operations/promotions/page.tsx`
- [x] 拆优惠码弹窗
- [x] 拆活动弹窗
- [x] 拆使用记录/兑换记录弹窗
- [x] 拆 promotion 工具函数和类型辅助
- [x] 拆 `src/cook-web/src/app/admin/operations/page.tsx`
- [x] 拆课程统计卡片
- [x] 拆课程搜索区
- [x] 拆课程表格
- [x] 拆复制课程弹窗
- [x] 拆转移创作者弹窗
- [x] 拆 Prompt 查看弹窗

### 当前拆分记录

- [x] `promotions/page.tsx` 已拆出表单弹窗、记录弹窗、状态确认弹窗、日期时间选择器、共享工具和类型辅助；优惠码/活动两个列表 tab 的主状态与表格渲染仍留在页面文件，避免本 PR 继续扩大 props 面。
- [x] `operations/page.tsx` 已拆出课程统计卡片、搜索区、课程表格、Prompt 查看弹窗、复制课程弹窗、转移创作者弹窗和共享工具。

### 验收重点

- [x] 业务行为不变
- [x] 接口调用不变
- [x] 文案不变
- [x] 测试覆盖仍通过
- [x] 单文件行数明显下降

## PR 5：促销活动主列表 tab 继续拆分

- 建议分支名：`refactor/operator-promotion-tabs-split`
- 优先级：中
- 风险：中
- 目标：在 PR 4 已拆出弹窗和工具函数的基础上，继续拆 `promotions/page.tsx` 内优惠码/兑换码活动两个主列表 tab，降低页面文件复杂度。

### 任务清单

- [x] 拆优惠码 tab 展示组件
- [x] 拆兑换码活动 tab 展示组件
- [x] 保持请求逻辑、筛选状态、分页状态、弹窗状态优先留在父页面
- [x] 保持列宽 storage key、自动列宽、手动拖拽行为不变
- [x] 保持更多菜单、启停、编辑、查看子码、使用记录、兑换记录入口不变
- [x] 避免本 PR 同时重构接口请求和状态管理

### 风险说明

- 优惠码和活动列表与页面级筛选、分页、loading、error、启停确认、编辑弹窗和记录弹窗联动较多。
- 本 PR 建议只拆展示层，把事件通过回调回传父页面；不要下放请求逻辑，避免重复请求、页码错乱或弹窗刷新行为变化。
- 如果 props 面过大，优先拆纯表格行/表头子组件，而不是强行把完整 tab 状态迁走。

### 验收重点

- [x] 两个 tab 的请求时机不变
- [x] 筛选、重置、分页行为不变
- [x] 表格列宽和拖拽行为不变
- [x] 行操作入口和弹窗联动不变
- [x] 促销活动页面测试通过

## PR 6：后端服务拆分、性能和审计检查

- 建议分支名：`refactor/operator-management-backend-services`
- 优先级：中
- 风险：中高
- 目标：降低后端大文件风险，检查运营接口性能和审计覆盖。

### 任务清单

- [ ] 拆 `src/api/flaskr/service/shifu/admin.py` 中运营课程逻辑
- [ ] 拆运营用户逻辑
- [ ] 拆运营订单逻辑
- [ ] 拆运营积分消耗逻辑
- [x] 拆 `/admin/operations/**` 路由到独立 route 模块
- [ ] 统一运营接口参数校验：分页、时间、状态、关键词
- [ ] 检查课程列表模糊搜索性能
- [ ] 检查用户列表联系方式/昵称搜索性能
- [ ] 检查订单列表时间和状态筛选性能
- [ ] 检查优惠码 code/name 搜索性能
- [ ] 检查积分通知记录筛选性能
- [ ] 检查发放积分审计日志
- [ ] 检查发放套餐审计日志
- [ ] 检查转移课程创作者审计日志
- [ ] 检查复制课程审计日志
- [ ] 检查活动启停审计日志
- [ ] 检查短信配置保存审计日志
- [ ] 检查通知重发审计日志

### 验收重点

- [ ] 接口响应结构不变
- [ ] 现有前端无需改接口即可运行
- [ ] 后端测试通过
- [ ] 本地后端服务重启或重建后可用
- [ ] `curl http://localhost:8080/api/runtime-config` 验证通过

### 后端接口拆分细化计划

#### PR6-A：路由拆分

- 建议分支名：`refactor/operator-management-backend-services`
- 状态：已完成
- 风险：低
- 目标：只拆 `/admin/operations/**` route 注册层。
- 范围：
  - [x] 从 `src/api/flaskr/service/shifu/route.py` 迁出运营管理路由。
  - [x] 新增独立 route adapter：`src/api/flaskr/service/shifu/admin_operations/route.py`。
  - [x] 保持 URL、入参、出参、业务服务函数不变。
  - [x] 不拆 `src/api/flaskr/service/shifu/admin.py` 业务逻辑。

#### PR6-B：积分通知后端服务拆分

- 建议分支名：`refactor/operator-credit-notification-services`
- 状态：已完成，PR 1852 已合入 main
- 风险：低
- 目标：先拆低耦合、薄封装的积分通知运营服务。
- 范围：
  - [x] `get_operator_credit_notification_overview`
  - [x] `list_operator_credit_notifications`
  - [x] `get_operator_credit_notification_detail`
  - [x] `get_operator_credit_notification_config`
  - [x] `update_operator_credit_notification_config`
  - [x] `sync_operator_credit_notification_template`
  - [x] `list_operator_credit_notification_templates`
  - [x] `dry_run_operator_credit_notifications`
  - [x] `requeue_operator_credit_notification`
- 验收重点：
  - [x] 通知记录列表、搜索、分页、详情行为不变。
  - [x] 短信配置读取、保存、模板同步行为不变。
  - [x] 通知重发接口行为不变。

#### PR6-C：用户发放和用户积分服务拆分

- 建议分支名：`refactor/operator-user-credit-services`
- 状态：已完成，PR 1853 已合入 main
- 风险：中
- 目标：拆用户详情内发放和积分流水相关服务。
- 范围：
  - [x] 发放积分
  - [x] 发放套餐
  - [x] 拉新奖励
  - [x] 用户 grant bootstrap
  - [x] 用户积分流水
  - [x] 用户积分消耗详情
- 验收重点：
  - [x] 用户详情页发放入口正常。
  - [x] 发放积分、发放套餐、拉新奖励表单和确认弹窗行为不变。
  - [x] 用户积分流水筛选、分页、详情行为不变。
  - [x] 后端相关测试通过：`cd src/api && pytest tests/service/shifu/test_admin_credit_notifications.py tests/service/shifu/test_admin_users.py -q`

### 自查遗留

- [x] 已新增 `src/api/flaskr/service/shifu/admin_operations/user_credits.py`，迁出用户发放和用户积分相关入口函数。
- [ ] `user_credits.py` 当前仍复用并 import `src/api/flaskr/service/shifu/admin.py` 内的私有 helper；这是为了控制 PR6-C 范围，只做入口层拆分，不在同一 PR 连带搬迁大量 helper。
- [ ] 后续继续拆 PR6-D / PR6-E 或做用户积分结构优化时，再逐步把用户积分账本、发放校验、消耗上下文和消耗明细 helper 下沉到独立模块，避免 `admin.py` 与 `user_credits.py` 长期强耦合。

#### PR6-D：用户列表和用户详情服务拆分

- 建议分支名：`refactor/operator-user-management-services`
- 状态：已完成，PR 1858 已合入 main
- 风险：中
- 目标：拆用户列表、用户详情和用户聚合信息加载逻辑。
- 范围：
  - [x] 用户概览
  - [x] 用户列表
  - [x] 用户详情
  - [x] 用户联系方式、登录方式、注册来源、付费金额、学习信息聚合
- 验收重点：
  - [x] 用户搜索、筛选、分页行为不变。
  - [x] 用户详情基础信息和统计信息展示不变。
  - [x] CN/COM 联系方式展示口径不被破坏。

### PR6-D 自查遗留

- [x] 已新增 `src/api/flaskr/service/shifu/admin_operations/users.py`，迁出用户概览、用户列表、用户详情入口函数。
- [x] 路由层 `src/api/flaskr/service/shifu/admin_operations/route.py` 已改为从 `admin_operations.users` 引入用户管理入口函数。
- [x] 用户管理测试 `src/api/tests/service/shifu/test_admin_users.py` 已改为覆盖新模块入口。
- [x] `users.py` 已改为通过 `src/api/flaskr/service/shifu/admin_operations/user_support.py` 引用稳定导出名，避免直接 import `admin.py` 私有 helper。
- [ ] 后续 PR6-E / PR6-F 或用户管理性能优化时，可再逐步把联系方式、登录、注册来源、付费、学习信息聚合 helper 从兼容导出下沉到独立模块，降低 `admin.py` 与用户管理模块长期强耦合。

#### PR6-E：课程管理服务拆分

- 建议分支名：`refactor/operator-course-management-services`
- 状态：已完成，PR 1877 已合入 main
- 风险：高
- 目标：最后拆课程管理相关服务，避免高耦合逻辑过早引入风险。
- 范围：
  - [x] 课程概览
  - [x] 课程列表
  - [x] 课程详情
  - [x] 课程用户
  - [x] 课程积分消耗
  - [x] 课程追问
  - [x] 课程评分
  - [x] 章节详情
  - [x] 复制课程
  - [x] 转移创作者
- 验收重点：
  - [x] 课程列表、搜索、分页行为不变。
  - [x] 课程详情各 tab 行为不变。
  - [x] 课程复制、转移创作者行为不变。
  - [x] MySQL 兼容和时间序列化逻辑不被破坏。

### PR6-E 当前拆分记录

- [x] 新增 `src/api/flaskr/service/shifu/admin_operations/courses.py`，迁出课程运营入口和课程专用 helper。
- [x] `src/api/flaskr/service/shifu/admin.py` 保留兼容导出，避免旧 import 路径和现有测试一次性大改。
- [x] `src/api/flaskr/service/shifu/admin_operations/route.py` 的课程运营路由改为直接引入课程运营模块。
- [x] 为旧 `flaskr.service.shifu.admin.*` monkeypatch 路径保留兼容同步，降低测试和本地排查脚本迁移风险。
- [ ] 后续可在单独 PR 中逐步把测试 import / monkeypatch 路径迁到 `admin_operations.courses`，再移除兼容同步层。

#### PR6-F：性能和审计检查

- 建议分支名：`refactor/operator-management-audit-hardening`
- 状态：已完成，PR 1869 已合入 main
- 风险：中高
- 目标：独立检查性能和审计，不和纯拆文件混在一起。
- 范围：
  - [x] 统一分页、时间、状态、关键词参数校验。
  - [x] 检查用户列表联系方式/昵称搜索性能。
  - [x] 检查订单列表时间和状态筛选性能。
  - [x] 检查优惠码 code/name 搜索性能。
  - [x] 检查积分通知记录筛选性能。
  - [x] 检查发放积分、发放套餐、课程转移、课程复制、活动启停、短信配置保存、通知重发审计日志。

##### 本次纳入范围

- 共性参数校验收口：
  - 分页
  - 时间范围
  - 状态值
  - 关键词入参
- 关键审计日志补齐与核对：
  - 发放积分
  - 发放套餐
  - 转移课程创作者
  - 复制课程
  - 活动启停
  - 短信配置保存
  - 通知重发
- 明显性能热点的小步修复：
  - 用户列表联系方式 / 昵称搜索
  - 订单列表时间 / 状态筛选
  - 优惠码 `code/name` 搜索
  - 积分通知记录筛选
- 对应后端测试补齐或修正
- 保持现有接口出参、前端调用方式、业务口径不变

##### 本次不纳入范围

- 课程管理服务拆分
- 课程列表模糊搜索性能专项
- 用户、订单、课程页新的前端交互改版
- 运营通用组件继续抽象
- 导出类新能力
- 接口协议或字段语义调整
- 与本次 audit 无关的页面体验优化

##### 后续继续优化项

- [ ] 课程列表模糊搜索性能专项排查，独立评估是否需要额外 SQL/索引优化。
- [ ] 用户管理页 B 版请求时间优化：概览缓存、更多快捷筛选 SQL 下推、更多补数聚合化。
- [ ] 订单列表筛选若仍有体感瓶颈，继续补 explain / 索引与查询口径复查。
- [ ] 优惠码 `code/name` 搜索若仍偏慢，评估结构化字段或索引优化，不在本 PR 内做模型迁移。
- [ ] 积分通知记录筛选若仍偏慢，评估进一步聚合或预计算方案。

### 当前拆分记录

- [x] 已新增 `src/api/flaskr/service/shifu/admin_operations/route.py`，将 `/admin/operations/**` 路由从 `src/api/flaskr/service/shifu/route.py` 迁出。
- [x] 本轮保持业务服务函数、接口路径、请求参数和响应结构不变；仅更新 route 层归属和对应测试 mock 路径。
- [x] 已新增 `src/api/flaskr/service/shifu/admin_operations/credit_notifications.py`，将积分通知运营服务薄封装从 `src/api/flaskr/service/shifu/admin.py` 迁出；route 直接依赖新模块，底层仍复用 billing notification 能力。
- [x] 已新增 `src/api/flaskr/service/shifu/admin_operations/user_credits.py`，将用户发放、拉新奖励、用户积分流水和用户积分消耗详情入口从 `src/api/flaskr/service/shifu/admin.py` 迁出。
- [ ] `src/api/flaskr/service/shifu/admin.py` 中课程管理、用户基础信息、订单相关逻辑和大量共享 helper 仍未拆分，后续需要按领域继续拆。

## 插队功能 PR：创作者课程兑换码

- 分支名：`feat/creator-course-redemption-codes`
- 状态：已完成，PR 1851 已合入 main。
- 风险：中
- 说明：该需求不属于原 6 个运营管理优化 PR 的主线，但复用了运营优惠活动的兑换码能力，并补充了运营优惠活动列表字段，因此记录到本地优化文档中，后续回查时避免遗漏。

### 业务目标

- 创作者可以在后台订单页创建自己课程的兑换码。
- 共享权限用户不可以给共享课程创建兑换码。
- 创建入口放在订单页 `开通导入` 前，风格与开通导入一致。
- 订单页增加 tab：`订单记录 / 兑换码`。
- 兑换码列表只展示当前创作者为自己已发布课程创建的兑换码批次。
- 一单一码支持查看子码和导出子码。
- 已用/总量支持打开兑换记录。
- 通用和一单一码都需要支持编辑。
- 通用和一单一码都需要支持启用 / 停用，入口放到“更多”内。
- 运营管理优惠活动的兑换码和活动列表补充创建者列。

### 已完成清单

- [x] 订单页新增 `订单记录 / 兑换码` tab。
- [x] 创建兑换码入口已放在开通导入前。
- [x] 创建弹窗已拆为 `src/cook-web/src/app/admin/orders/CreatorRedemptionCodeDialog.tsx`。
- [x] 创作者兑换码 tab 已拆为 `src/cook-web/src/app/admin/orders/CreatorRedemptionCodesTab.tsx`。
- [x] 创建弹窗课程字段使用已发布课程下拉单选，文案为“课程 / 请选择已发布课程”。
- [x] 兑换码类型不预设默认值。
- [x] 兑换码类型说明气泡分行解释“通用”和“一单一码”。
- [x] 后端创建接口强制限定当前创作者自己的已发布课程。
- [x] 后端列表接口只返回当前创作者创建且课程属于自己的兑换码。
- [x] 后端使用记录和子码接口复用运营查询能力，但先校验创作者和课程归属。
- [x] 通用和一单一码操作列都展示“更多”；一单一码额外支持导出子码。
- [x] 兑换码列表操作列表头使用 sticky right 表头样式，横向滚动时固定。
- [x] 子码列、导出子码、兑换记录弹窗已接入。
- [x] 运营优惠活动兑换码列表增加创建者列。
- [x] 运营优惠活动活动列表增加创建者列。
- [x] 弹窗补充隐藏 `DialogDescription`，避免 Radix Dialog 可访问性 warning。
- [x] 用户可见文案走 `src/i18n/**`，未新增硬编码中文。
- [x] 新增/调整前后端测试覆盖权限、列表隔离、弹窗、导出和表格展示。

### 本轮追加需求清单

- [x] 创作者兑换码后端补详情接口，返回当前创作者有权限访问的兑换码详情。
- [x] 创作者兑换码后端补编辑接口，复用运营兑换码编辑规则，并先校验创作者和课程归属。
- [x] 创作者兑换码后端补启用 / 停用接口，复用运营启停规则，并先校验创作者和课程归属。
- [x] 前端 `CreatorRedemptionCodeDialog` 支持编辑模式。
- [x] 编辑模式下保持高风险字段只读：兑换码类型、优惠方式、优惠值、通用码 code、适用课程；允许编辑名称、数量、生效时间。
- [x] 一单一码编辑数量时沿用运营端规则：不能低于已使用数量，增加数量时生成新增子码。
- [x] 创作者兑换码列表“更多”菜单补“编辑”和“启用 / 停用”。
- [x] 启用 / 停用使用确认弹窗，成功后刷新当前列表页。
- [x] 补充后端权限、编辑、启停测试。
- [x] 补充前端编辑、启停菜单和接口调用测试。

### 本分支内可直接优化

- [x] 复用现有运营兑换码编辑、启停服务逻辑，避免为创作者侧复制一套业务规则。
- [x] 详情 / 编辑 / 启停接口都统一走同一个创作者归属校验，减少权限遗漏风险。
- [x] 创作者侧详情接口只返回当前行编辑需要的数据，不新增大范围查询。
- [x] 操作列菜单统一使用 `AdminRowActions`，保持与运营管理更多菜单一致。

### 暂不放入本分支的优化

- [ ] 创作者课程下拉远程搜索：当前需要调整课程选择交互和接口搜索口径，建议后续独立做。
- [ ] 子码后端文件导出接口：当前前端分页导出可用；新增文件导出接口会扩大后端返回形态和下载链路，建议后续按真实数据量决定。
- [ ] 兑换码列表结构化课程字段 / 索引优化：当前 `Coupon.filter` 存 JSON 字符串，想彻底优化需要模型字段或迁移，建议后续单独做。

### 已验证

- [x] `cd src/api && pytest tests/service/promo/test_admin_promotions.py tests/service/billing/test_legacy_boundary_contracts.py -q`
- [x] `cd src/cook-web && npm test -- src/app/admin/orders/CreatorRedemptionCodesTab.test.tsx src/app/admin/orders/CreatorRedemptionCodeDialog.test.tsx src/app/admin/orders/page.test.tsx src/app/admin/operations/promotions/page.test.tsx --runInBand`
- [x] `cd src/cook-web && npm run type-check`
- [x] `cd src/cook-web && npm run lint -- --file src/app/admin/orders/CreatorRedemptionCodesTab.tsx --file src/app/admin/orders/CreatorRedemptionCodesTab.test.tsx --file src/app/admin/orders/CreatorRedemptionCodeDialog.tsx --file src/app/admin/orders/CreatorRedemptionCodeDialog.test.tsx --file src/app/admin/orders/page.tsx --file src/app/admin/orders/page.test.tsx --file src/app/admin/operations/promotions/PromotionRecordDialogs.tsx --file src/app/admin/operations/promotions/page.test.tsx`
- [x] `git diff --check`
- [x] `python scripts/check_architecture_boundaries.py`

### 遗留风险和后续优化

- [ ] `src/cook-web/src/app/admin/orders/page.tsx` 仍偏大，后续建议单独拆订单记录 tab：
  - `OrdersListTab.tsx`
  - `OrdersFilter.tsx`
  - `OrdersTable.tsx`
  - `useOrdersList.ts`
- [x] `src/api/flaskr/service/promo/admin.py` 的 creator redemption 入口已迁到 `creator_redemption.py`，`admin.py` 仍保留 operator 主链路。
- [ ] 子码导出沿用运营端分页拉取方式；当前可接受，后续若单批子码量很大，再考虑后端导出接口。
- [ ] 创作者课程下拉当前仍是打开弹窗后分页拉已发布课程；后续若创作者课程量很大，再改远程搜索。
- [ ] 创作者兑换码列表当前受限于 `Coupon.filter` JSON 字符串结构，彻底性能优化需要后续模型字段或迁移支持。
- [ ] `OrdersPage` 测试仍有 React `act(...)` warning，当前不阻塞功能，后续做订单页拆分时一并收敛测试写法。
- [ ] 提交前必须确认 `.codex-local/`、`.codex-backups/` 等本地文件不进入提交。

### 当前分支收口（`refactor/streamline-creator-redemption-code-admin-flows`）

- [x] `CreatorRedemptionCodesTab` 已拆为列表 hook、筛选区、表格展示三个层次。
- [x] `CreatorRedemptionCodeDialog` 已拆出课程加载 hook 与表单校验 / payload 组装 helper。
- [x] `OrdersPage` 的创作者兑换码入口状态已抽到 `useCreatorRedemptionEntry`。
- [x] creator redemption 列表的本地 view-model / 行操作规则已抽离，避免 JSX 内继续堆业务判断。
- [x] `promo/admin.py` 里的 creator redemption 入口已做最小薄拆，迁到 `promo/creator_redemption.py`，保持外部 API 出口不变。

## 执行顺序

1. `feat/operator-admin-filter-unification`
2. `feat/operator-admin-table-actions-unification`
3. `feat/operator-admin-time-picker-unification`
4. `refactor/operator-management-page-split`
5. `refactor/operator-promotion-tabs-split`
6. `refactor/operator-management-backend-services`

### 插队记录

- `feat/creator-course-redemption-codes`：当前插队功能分支，完成后不改变原 PR6 拆分主线；后续继续 PR6 时需要回查本节遗留风险。

## 每个 PR 完成后的固定检查

- [ ] 回查本文档，勾选已完成项
- [ ] 确认是否有未完成项需要移到后续 PR
- [ ] 检查是否误提交本地文档或临时文件
- [ ] 跑对应范围的最小测试
- [ ] 推送前执行分支上下文检查：`sync`、`report`、`pre-pr-review`、`pre-push-check`

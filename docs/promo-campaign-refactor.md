# 促销活动表重构技术方案（promo campaign refactor）

## 背景

当前促销相关能力分散在两套表/模型中：

- **Coupon 体系（较新风格）**：`promo_coupons`、`promo_coupon_usages`（见 `src/api/flaskr/service/promo/models.py`）
- **活动/优惠体系（旧风格）**：`active`、`active_user_record`（见 `src/api/flaskr/service/active/models.py`，并在下单流程与后台订单列表中使用）

两套体系在命名、字段风格与语义上不一致，给后续扩展（多促销组合、审计、统计、运营配置）带来维护成本。

## 目标

1. **统一促销域前缀**：将“促销活动/方案”统一收敛到 `promo_` 域，避免同时维护 `active_*` 与 `promo_*` 两套体系。
2. **对齐表设计规范**：表名使用 `<domain>_<plural>`，业务键统一 `*_bid` 并加索引；软删除、时间戳字段风格统一。
3. **明确语义**：将“每次下单都生成记录”的表命名为 `*_applications`（应用记录），避免使用 `usage`（更偏“券被使用一次”语义）。
4. **可演进**：在不引入外键约束的前提下，为未来扩展（适用范围/门槛/叠加规则）预留结构。

## 非目标

- 不在本次改造中设计完整的促销引擎（叠加、互斥、最优解、规则 DSL）。
- 不在本次改造中改动前端/CMS 交互；以后台与下单链路数据一致性为先。

## 最终表名方案

- `promo_campaigns`：促销活动/方案定义表（替代现有 `active`）
- `promo_campaign_applications`：促销方案订单级应用记录（每次下单生成，替代现有 `active_user_record`）
- `promo_coupons`：优惠券/折扣码定义（保持现状）
- `promo_coupon_usages`：优惠券/折扣码使用记录（保持现状）

> 说明：本方案沿用现有 `promo_*` 前缀（代码中已存在并在迁移里出现），避免引入新的 `promotion_*` 前缀体系。

## 表结构定义（建议）

### 1) `promo_campaigns`（促销活动/方案）

| 字段 | 类型 | 索引 | 默认值 | 说明 |
|---|---|---:|---|---|
| `id` | BIGINT | PK |  | 自增主键 |
| `campaign_bid` | VARCHAR(36) | ✅ | `''` | Campaign 业务键 |
| `shifu_bid` | VARCHAR(36) | ✅ | `''` | 作用对象（当前等价于 `active_course` 的实际用法） |
| `name` | VARCHAR(255) |  | `''` | 名称 |
| `description` | TEXT |  | `''` | 描述 |
| `join_type` | SMALLINT |  | `2101` | 2101=auto, 2102=event, 2103=manual |
| `status` | SMALLINT | ✅ | `0` | 0=inactive, 1=active |
| `start_at` | DATETIME | ✅ | `now()` | 生效开始时间 |
| `end_at` | DATETIME | ✅ | `now()` | 生效结束时间 |
| `discount_type` | SMALLINT |  | `701` | 701=fixed, 702=percent（与 coupon 常量复用） |
| `value` | DECIMAL(10,2) |  | `0.00` | 折扣值（按 `discount_type` 解释） |
| `channel` | VARCHAR(36) |  | `''` | 渠道（可选） |
| `filter` | TEXT |  | `''` | 扩展条件（建议存 JSON 字符串） |
| `deleted` | SMALLINT | ✅ | `0` | 0=active, 1=deleted |
| `created_at` | DATETIME |  | `now()` | 创建时间 |
| `created_user_bid` | VARCHAR(36) | ✅ | `''` | 创建人 |
| `updated_at` | DATETIME |  | `now()` | 更新时间 |
| `updated_user_bid` | VARCHAR(36) | ✅ | `''` | 更新人 |

建议索引：
- 单列索引：`campaign_bid`、`shifu_bid`、`status`、`start_at`、`end_at`、`deleted`
- 可选复合索引：`(shifu_bid, status, start_at, end_at)`（用于快速查找可用促销）

不创建 DB 外键约束（遵循现有规范）。

### 2) `promo_campaign_applications`（订单级应用记录）

| 字段 | 类型 | 索引 | 默认值 | 说明 |
|---|---|---:|---|---|
| `id` | BIGINT | PK |  | 自增主键 |
| `campaign_application_bid` | VARCHAR(36) | ✅ | `''` | Application 业务键（替代 `record_id`） |
| `campaign_bid` | VARCHAR(36) | ✅ | `''` | 关联 `promo_campaigns.campaign_bid` |
| `order_bid` | VARCHAR(36) | ✅ | `''` | 订单业务键 |
| `user_bid` | VARCHAR(36) | ✅ | `''` | 用户业务键 |
| `shifu_bid` | VARCHAR(36) | ✅ | `''` | Shifu 业务键 |
| `campaign_name` | VARCHAR(255) |  | `''` | 名称快照（便于后台展示） |
| `discount_type` | SMALLINT |  | `701` | 快照（可选） |
| `value` | DECIMAL(10,2) |  | `0.00` | 快照（可选） |
| `discount_amount` | DECIMAL(10,2) |  | `0.00` | 本次订单实际抵扣金额（替代旧表 `price`） |
| `status` | SMALLINT | ✅ | `4101` | 4101=applied, 4102=voided/failed |
| `deleted` | SMALLINT | ✅ | `0` | 软删除 |
| `created_at` | DATETIME |  | `now()` | 创建时间 |
| `updated_at` | DATETIME |  | `now()` | 更新时间 |

建议索引：
- 单列索引：`campaign_application_bid`、`campaign_bid`、`order_bid`、`user_bid`、`shifu_bid`、`status`、`deleted`
- 可选复合索引：
  - `(order_bid, deleted)`：订单详情/后台列表常用
  - `(campaign_bid, user_bid, status, deleted)`：避免重复应用/便于统计
- 可选唯一约束（按业务是否允许同订单重复应用同 campaign 决定）：`UNIQUE(order_bid, campaign_bid, deleted)`

## 旧表到新表字段映射

### `active` → `promo_campaigns`

| 旧字段 | 新字段 | 说明 |
|---|---|---|
| `active_id` | `campaign_bid` | 建议直接复用原值，避免额外映射 |
| `active_name` | `name` |  |
| `active_desc` | `description` |  |
| `active_join_type` | `join_type` |  |
| `active_status` | `status` |  |
| `active_start_time` | `start_at` |  |
| `active_end_time` | `end_at` |  |
| `active_discount_type` | `discount_type` | 复用 coupon 常量值（701/702）或做映射 |
| `active_discount`/`active_price` | `value` | 需确认旧逻辑（折扣值 vs 抵扣金额）后择一映射 |
| `active_filter` | `filter` |  |
| `active_course` | `shifu_bid` | 当前下单流程用其作为 course/shifu 标识 |
| `created`/`updated` | `created_at`/`updated_at` | 类型转换（TIMESTAMP → DATETIME） |

### `active_user_record` → `promo_campaign_applications`

| 旧字段 | 新字段 | 说明 |
|---|---|---|
| `record_id` | `campaign_application_bid` | 建议直接复用原值 |
| `active_id` | `campaign_bid` |  |
| `active_name` | `campaign_name` | 快照字段 |
| `user_id` | `user_bid` | 命名对齐新规范 |
| `order_id` | `order_bid` | 命名对齐新规范 |
| `price` | `discount_amount` | 旧逻辑里为抵扣金额（下单计算时累加后从 payable_price 扣减） |
| `status` | `status` | 4101/4102 延续现有常量 |
| `created`/`updated` | `created_at`/`updated_at` |  |

## 应用层改造点（代码层面）

1. 下单链路（当前在 `src/api/flaskr/service/order/funs.py`）：
   - 用 `promo_campaigns` 替代 `Active` 查询可用促销
   - 用 `promo_campaign_applications` 替代 `ActiveUserRecord` 写入/回查应用记录
   - 将抵扣字段从 `price` 语义统一为 `discount_amount`
2. 后台订单展示（当前在 `src/api/flaskr/service/order/admin.py`）：
   - `_load_order_activities` 替换为 `_load_order_campaign_applications`（命名建议），读取新表并输出 DTO
3. Service 模块组织：
   - 方案 A：保留 `service/active`，内部切换到新表并逐步迁移命名（短期改动小）
   - 方案 B：新增 `service/promo_campaign`（或扩展 `service/promo`），将 campaign 逻辑并入促销域（长期更清晰）

## 迁移与发布策略（推荐分阶段）

### Phase 0：准备
- 盘点线上 `active`/`active_user_record` 的真实字段含义与取值（尤其是 `active_discount_type`、`active_discount`、`active_price` 的关系）。

### Phase 1：新增表（不影响线上）
- Alembic 创建 `promo_campaigns`、`promo_campaign_applications`（不删旧表）。
- 新增 SQLAlchemy models（先不替换业务读写）。

### Phase 2：数据回填
- 通过一次性脚本或迁移脚本将旧表数据回填到新表：
  - `campaign_bid`/`campaign_application_bid` 直接复用旧表 UUID 值，避免额外映射表。
  - 对缺失字段（如 `deleted`、`*_user_bid`）统一写默认值。

### Phase 3：切换读路径（可选 dual-write）
- 先切换后台查询与订单详情读取到新表。
- 下单写入阶段可短期 dual-write（新表写入 + 旧表写入）以降低回滚成本。

### Phase 4：切换写路径与清理
- 完全切换后，确认无旧表读取，再停止写旧表。
- 保留旧表一段观察期后再删除（单独迁移）。

### 回滚策略
- 若 Phase 3/4 出现问题，可快速切回旧表（dual-write 可保证数据不丢）。

## 验证与测试

- 单测：覆盖“下单触发自动促销”“订单超时使促销应用记录失效”“后台展示促销抵扣项”等关键路径。
- 集成测试：对比同一订单在旧表与新表的抵扣金额一致性。
- 数据校验：抽样对比 `active_user_record.price` 与新表 `discount_amount` 的总和是否一致。

## 待确认问题（Open Questions）

1. `active_discount_type/active_discount/active_price` 的业务语义与计算方式（是否与 coupon 常量完全一致）。
2. 是否允许同一订单重复应用同一个 `campaign_bid`（决定是否加 UNIQUE 约束）。
3. campaign 的“作用对象”是否长期仅限 `shifu_bid`，还是需要扩展为多 target（类目/SKU/用户分群等）。

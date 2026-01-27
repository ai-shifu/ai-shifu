# Redis Hard Dependency Removal (Redis 可选化改造)

目标：
- 未配置/不可用 Redis 时：系统可运行，使用**服务器内存缓存**（非持久）+ **数据库存储**（持久）替代关键能力。
- 配置并可用 Redis 时：启用 Redis 缓存/分布式锁等机制。
- 通过 provider 形式解耦具体实现，避免业务代码直接依赖 `redis_client`。

## Checklist

- [x] 定义 `CacheProvider` 接口（get/set/setex/getex/delete/incr/ttl/lock）
- [x] 实现 `InMemoryCacheProvider`（带 TTL + 本地锁）
- [x] 让 Redis 初始化可选化：未配置/连接失败时自动降级且不影响启动
- [x] 配置读取缓存（`service/config/funcs.py`）改用 provider（无 Redis 时使用内存缓存；DB 仍为来源）
- [x] Token 存储改用 provider：无 Redis 时使用数据库 `user_token` 表实现过期与滑动续期
- [x] 手机/邮箱验证码校验改造：无 Redis 时从 `user_verify_code` 表校验有效期并标记已使用
- [x] 发送频控/封禁（IP/手机号/邮箱）改造：无 Redis 时使用内存缓存（可接受单实例语义）
- [x] Google OAuth state 存储改造：无 Redis 时使用内存缓存或数据库（按可用性选择）
- [x] Shifu 权限缓存改造：无 Redis 时使用内存缓存
- [x] 运行脚本相关分布式锁改造：无 Redis 时使用本地锁
- [x] Feishu tenant token 缓存改造：无 Redis 时使用内存缓存
- [x] 移除所有 docker-compose 中的 Redis service/depends_on/环境变量
- [x] 更新相关文档/示例配置（说明 Redis 为可选项）
- [x] 更新/新增测试用例，确保 `pytest` 通过

---

# Profile Variable Tables Refactor (用户变量表规范化与瘦身)

目标：
- 将“变量定义/用户变量值”两类数据落到**两张新表**：`profile_variable_definitions`、`profile_variable_values`
- 表命名与字段命名对齐现行规范：业务 id 用 `*_bid`，软删用 `deleted`，时间用 `created_at/updated_at`
- **仅保留必要字段**：定义表只保留 `is_hidden`（不再存 type/remark/options/i18n/颜色等）；值表保留业务 id，且**不做 UNIQUE**

非目标（本方案明确不做）：
- 不再支持“枚举/选项型变量”的选项存储（原 `profile_item_value` / `profile_item_i18n`）
- 不再支持自定义变量标题/备注/颜色/排序等（原 `profile_remark/profile_color_setting/profile_index/...`）

## 最终表结构

### `profile_variable_definitions`
- `id` BIGINT PK AI
- `variable_bid` VARCHAR(32) NOT NULL DEFAULT '' INDEX
- `shifu_bid` VARCHAR(32) NOT NULL DEFAULT '' INDEX
  - 约定：`''` 表示 system scope；非空表示该 shifu 下的自定义变量
- `variable_key` VARCHAR(255) NOT NULL DEFAULT '' INDEX
- `is_hidden` SMALLINT NOT NULL DEFAULT 0 INDEX
- `deleted` SMALLINT NOT NULL DEFAULT 0 INDEX
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP

建议索引：
- `INDEX(variable_bid)`
- `INDEX(shifu_bid)`
- `INDEX(variable_key)`
- `INDEX(deleted)`
- （可选）`UNIQUE(shifu_bid, variable_key, deleted)`：防止同一 shifu 下存在多个“活跃同名变量”

### `profile_variable_values`
- `id` BIGINT PK AI
- `variable_value_bid` VARCHAR(32) NOT NULL DEFAULT '' INDEX  (业务 id，按约束保留)
- `user_bid` VARCHAR(32) NOT NULL DEFAULT '' INDEX
- `shifu_bid` VARCHAR(32) NOT NULL DEFAULT '' INDEX
  - 约定：`''` 表示全局/系统范围的取值；非空表示该 shifu 范围取值
- `variable_bid` VARCHAR(32) NOT NULL DEFAULT '' INDEX
- `variable_key` VARCHAR(255) NOT NULL DEFAULT '' INDEX  (保留用于回退与快速查询)
- `variable_value` TEXT NOT NULL DEFAULT ''
- `deleted` SMALLINT NOT NULL DEFAULT 0 INDEX
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP

不做 UNIQUE 的读取约定（统一在代码侧实现）：
- “当前值”按 `deleted=0` 且 `ORDER BY id DESC` 取最新一条
- 读取顺序：优先匹配 `shifu_bid=<current>`，再回退 `shifu_bid=''`（兼容历史全局值）

## 数据迁移与兼容策略

1. 新增表 + 回填：
   - `profile_item` → `profile_variable_definitions`
     - `variable_bid = profile_id`
     - `shifu_bid = parent_id`
     - `variable_key = profile_key`
     - `is_hidden = is_hidden`
     - `deleted = (status==1?0:1)`
     - `created_at/updated_at = created/updated`
   - `user_profile` → `profile_variable_values`
     - `user_bid = user_id`
     - `variable_bid = profile_id`（为空则 `''`）
     - `variable_key = profile_key`
     - `variable_value = profile_value`
     - `shifu_bid = ''`（旧表不区分 shifu，只能先回填为全局值）
     - `deleted = (status==1?0:1)`
     - `created_at/updated_at = created/updated`
     - `variable_value_bid`：迁移时生成 32 位业务 id

2. 代码改造阶段采用“双读/单写”：
   - 先写新表（definitions/values），读取优先新表，缺失时回退旧表，确保灰度期间可回滚
   - 待稳定后移除旧表读路径，最后 drop 旧表（新 migration）

3. 业务能力变化：
   - 所有变量视为“文本变量”
   - 前端变量管理页需移除/隐藏“枚举变量/选项编辑”能力；后端相关接口同步下线或改为 no-op

## Checklist

- [x] 输出技术方案与任务清单（本文件）
- [ ] 与产品/前端确认：枚举变量/备注/颜色/排序等能力是否可完全下线
- [x] 新增 SQLAlchemy models：`ProfileVariableDefinition`、`ProfileVariableValue`
- [x] Alembic migration：创建两张新表（符合 `*_bid/deleted/created_at/updated_at`）
- [x] Alembic data migration：从旧表回填新表（含 `variable_value_bid` 生成）
- [x] 修复 Alembic 多 heads：新增 merge migration 并保证回填兼容缺失列
- [x] 后端服务改造：profiles/learn/shifu/user/profile 等读写切到新表（双读/单写）
- [x] 前端改造（Cook Web）：移除 option 相关 UI 与接口调用，适配返回结构变化
- [x] 清理：下线旧接口/删除旧表与旧模型（新 migration，注意不要改已应用 migration）
- [x] 测试：补齐单测/回归用例，确保 `pytest` 与 `pre-commit run -a` 通过

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

# Promotion Campaign Table Refactor (促销活动表重构)

目标：
- 将现有 `active` / `active_user_record` 促销逻辑统一到 `promo_` 域，表名与字段命名对齐现行规范。
- 明确“每次下单生成记录”的语义：使用 `promo_campaign_applications`（application）而非 `usage`（usage 更偏券码一次性使用语义）。
- 保持 `promo_coupons` / `promo_coupon_usages` 不变，减少改动面。

技术方案：
- `docs/promo-campaign-refactor.md`

## Checklist

### Phase 0 - 方案与对齐

- [x] 明确业务语义：每次下单生成促销应用记录（order-level application）
- [x] 确认最终表名：`promo_campaigns`、`promo_campaign_applications`
- [x] 输出技术方案文档：`docs/promo-campaign-refactor.md`

### Phase 1 - Schema & Models

- [x] 新增 SQLAlchemy models：`PromoCampaign`、`PromoCampaignApplication`
- [x] Alembic migration：创建 `promo_campaigns`、`promo_campaign_applications`
- [x] 确认索引与约束：添加 `UNIQUE(order_bid, campaign_bid, deleted)`

### Phase 2 - Data Migration

- [x] 回填脚本/迁移：`active` → `promo_campaigns`（`active_id` 复用为 `campaign_bid`）
- [x] 回填脚本/迁移：`active_user_record` → `promo_campaign_applications`（`record_id` 复用为 `campaign_application_bid`）
- [x] 明确 `active_discount_type/active_discount/active_price` 映射到新表的规则并实现
- [ ] 数据一致性校验：数量、抵扣金额汇总、抽样订单对比（`cd src/api && python scripts/check_promo_campaign_migration.py`）

### Phase 3 - Code Switch

- [x] 下单链路改造：读写新表（替换 `Active`/`ActiveUserRecord`）
- [x] 后台订单展示改造：读取 `promo_campaign_applications`
- [x] 选择模块组织策略：合并进 `service/promo`
- [ ] （可选）dual-write：新表写入 + 旧表写入，降低回滚风险

### Phase 4 - Testing & Rollout

- [x] 更新/新增测试用例，确保关键路径覆盖
- [x] 运行 `pytest`（`cd src/api && pytest`）
- [x] 运行 `pre-commit run -a`（根目录）
- [ ] 灰度发布/上线监控：订单金额、促销抵扣、后台展示
- [ ] 观察期后停止写旧表，并新增迁移删除旧表（单独 migration）
- [ ] 补充运维手册：回滚策略与数据校验步骤

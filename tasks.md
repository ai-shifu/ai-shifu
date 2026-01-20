# Redis Hard Dependency Removal (Redis 可选化改造)

目标：
- 未配置/不可用 Redis 时：系统可运行，使用**服务器内存缓存**（非持久）+ **数据库存储**（持久）替代关键能力。
- 配置并可用 Redis 时：启用 Redis 缓存/分布式锁等机制。
- 通过 provider 形式解耦具体实现，避免业务代码直接依赖 `redis_client`。

## Checklist

- [ ] 定义 `CacheProvider` 接口（get/set/setex/getex/delete/incr/ttl/lock）
- [ ] 实现 `InMemoryCacheProvider`（带 TTL + 本地锁）
- [ ] 让 Redis 初始化可选化：未配置/连接失败时自动降级且不影响启动
- [ ] 配置读取缓存（`service/config/funcs.py`）改用 provider（无 Redis 时使用内存缓存；DB 仍为来源）
- [ ] Token 存储改用 provider：无 Redis 时使用数据库 `user_token` 表实现过期与滑动续期
- [ ] 手机/邮箱验证码校验改造：无 Redis 时从 `user_verify_code` 表校验有效期并标记已使用
- [ ] 发送频控/封禁（IP/手机号/邮箱）改造：无 Redis 时使用内存缓存（可接受单实例语义）
- [ ] Google OAuth state 存储改造：无 Redis 时使用内存缓存或数据库（按可用性选择）
- [ ] Shifu 权限缓存改造：无 Redis 时使用内存缓存
- [ ] 运行脚本相关分布式锁改造：无 Redis 时使用本地锁
- [ ] Feishu tenant token 缓存改造：无 Redis 时使用内存缓存
- [ ] 移除所有 docker-compose 中的 Redis service/depends_on/环境变量
- [ ] 更新相关文档/示例配置（说明 Redis 为可选项）
- [ ] 更新/新增测试用例，确保 `pytest` 通过

# 线上数据库时间字段时区核查 (UTC vs 北京时间)

> 库: `agi-sifu-prod` (阿里云 RDS,只读账号 sifu_prod_read)
> 核查时间基准: **UTC=2026-06-25 02:00:57** / **北京时间(NOW)=2026-06-25 10:00:57**
> DB 会话/全局时区: `+08:00`;字段总数: **178** 个时间字段,覆盖 64 张表。

## 一、核心结论

数据库里**同时存在两种时区**,根因是两条写入路径落在不同时区:

| 写入路径 | 求值位置 | 实际时区 |
|---|---|---|
| SQLAlchemy `default=func.now()` / `onupdate=func.now()` | **数据库端**(会话时区 `+08:00`) | **北京时间** |
| Python `datetime.now()` / `datetime.utcnow()` | **应用服务器**(运行于 UTC) | **UTC** |

因此规律为:

- **`created_at` / `updated_at` / `created` / `updated`**(走 `func.now()`)→ 基本都是**北京时间**。
- **业务/事件时间字段**(`paid_at`、`effective_from`、`expires_at`、`processed_at`、`scheduled_at`、`generated_at`、`token_expired_at`、`ready_at`、`completed_at` 等,由 Python 代码赋值)→ **UTC**。
- **例外1 — 旧订单系统 `order_*` 表**:模型所有时间列都用 `func.now()`,故**全部为北京时间**(含 `paid_at` 等)。
- **例外2 — 新计费系统 `bill_*` / `credit_*`**:`created_at/updated_at` 北京时间,事件字段 UTC,同一行内相差正好 8 小时。
- **例外3 — `shifu_*` 草稿/发布及归档**:多数 `created_at`/事件字段走 Python(utcnow)→ **UTC**(注意 `shifu_published_*.updated_at` 实测为北京时间)。
- 部分 `updated_at` 被服务层用 Python 显式覆盖(如 `bill_subscriptions`、`bill_renewal_events`、`credit_wallets`、`notification_*`)→ 这些 `updated_at` 是 **UTC**。

## 二、判定方法

1. **实测最新值比对(主依据)**:每表按主键倒序取最新 50 行,取各时间字段最大值,与服务器 `UTC_TIMESTAMP()`(02:00)、`NOW()`(10:00)比对——≈02:00 即 UTC,≈10:00 即北京时间。
2. **小时分布直方图(对不活跃表)**:统计创建时间的小时分布。中国用户在**北京时间凌晨 2-7 点**为活动低谷;低谷落在 2-7 点=北京时间存储,低谷落在 18-22 点=UTC 存储(与新鲜度无关)。
3. **同行字段配对**:同一行内事件字段较 `created_at` 恒早 8 小时即为 UTC。
4. **后端模型代码**:`func.now()` vs `datetime.now/utcnow` 交叉印证。

统计:**北京时间字段 118 个 / UTC 字段 59 个 / 其他(日期或待定) 1 个**。

## 三、UTC 字段清单(写入/对账时需 +8h 才是北京时间)

- **bill_daily_ledger_summary**: `window_started_at`, `window_ended_at`
- **bill_daily_usage_metrics**: `window_started_at`, `window_ended_at`
- **bill_domain_bindings**: `last_verified_at`
- **bill_entitlements**: `effective_from`, `effective_to`
- **bill_orders**: `paid_at`, `failed_at`, `refunded_at`, `expires_at`
- **bill_renewal_events**: `scheduled_at`, `processed_at`, `updated_at`
- **bill_subscriptions**: `billing_anchor_at`, `current_period_start_at`, `current_period_end_at`, `grace_period_end_at`, `last_renewed_at`, `last_failed_at`, `updated_at`
- **credit_ledger_entries**: `expires_at`, `consumable_from`
- **credit_usage_rates**: `effective_from`, `effective_to`
- **credit_wallet_buckets**: `effective_from`, `effective_to`
- **credit_wallets**: `updated_at`
- **migration_sync_log**: `sync_time`, `created_at`
- **notification_records**: `requested_at`, `attempted_at`, `sent_at`, `updated_at`
- **notification_templates**: `last_synced_at`, `updated_at`
- **referral_campaign_reward_rules**: `starts_at`, `ends_at`
- **referral_campaigns**: `starts_at`, `ends_at`
- **referral_invite_codes**: `generated_at`
- **referral_invite_rewards**: `effective_at`, `expires_at`
- **shifu_draft_outline_items**: `created_at`, `updated_at`
- **shifu_draft_shifus**: `created_at`, `updated_at`
- **shifu_log_draft_structs**: `created_at`, `updated_at`
- **shifu_log_published_structs**: `created_at`
- **shifu_published_outline_items**: `created_at`
- **shifu_user_archives**: `archived_at`, `created_at`, `updated_at`
- **tts_minimax_cloned_voices**: `ready_at`, `deleted_at`
- **user_onboarding_states**: `completed_at`
- **user_token**: `token_expired_at`
- **user_users**: `creator_activated_at`

## 四、逐表逐字段明细

判定列:🕗=北京时间, 🌐=UTC, ⬜=日期/待定。

### `ai_course_auth`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | timestamp | 50 | 2026-06-25 09:57:06 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |
| `updated_at` | timestamp | 50 | 2026-06-25 09:57:06 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |

### `bill_campaign_products`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 0 | — | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码);当前无数据 | 中 |
| `updated_at` | datetime | 0 | — | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码);当前无数据 | 中 |

### `bill_campaigns`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 0 | — | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码);当前无数据 | 中 |
| `updated_at` | datetime | 0 | — | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码);当前无数据 | 中 |
| `start_at` | datetime | 0 | — | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码);当前无数据 | 中 |
| `end_at` | datetime | 0 | — | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码);当前无数据 | 中 |

### `bill_daily_ledger_summary`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `window_started_at` | datetime | 50 | 2026-06-24 00:00:00 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |
| `window_ended_at` | datetime | 50 | 2026-06-25 00:00:00 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |
| `created_at` | datetime | 50 | 2026-06-25 09:30:02 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.52) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 09:30:02 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.52) | 高 |

### `bill_daily_usage_metrics`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `window_started_at` | datetime | 50 | 2026-05-21 00:00:00 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |
| `window_ended_at` | datetime | 50 | 2026-05-22 00:00:00 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |
| `created_at` | datetime | 50 | 2026-05-23 13:35:34 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 50 | 2026-05-23 13:35:34 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `bill_domain_bindings`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `last_verified_at` | datetime | 2 | 2026-06-17 06:11:37 | 🌐 UTC | 同行较 created_at 早8h(配对) | 高 |
| `created_at` | datetime | 2 | 2026-06-17 14:11:36 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 2 | 2026-06-18 18:16:00 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `bill_entitlements`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `effective_from` | datetime | 2 | 2026-06-17 06:10:36 | 🌐 UTC | 同行较 created_at 早8h(配对) | 高 |
| `effective_to` | datetime | 2 | — | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 中 |
| `created_at` | datetime | 2 | 2026-06-17 14:11:36 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 2 | 2026-06-18 18:16:00 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `bill_orders`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `paid_at` | datetime | 50 | 2026-06-25 01:57:06 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.06) | 高 |
| `failed_at` | datetime | 50 | — | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 中 |
| `refunded_at` | datetime | 50 | — | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 中 |
| `created_at` | datetime | 50 | 2026-06-25 09:57:06 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 09:57:06 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |
| `expires_at` | datetime | 50 | 2026-06-24 08:05:27 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |

### `bill_products`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 8 | 2026-04-20 23:51:22 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 8 | 2026-04-20 23:51:22 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `bill_renewal_events`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `scheduled_at` | datetime | 50 | 2026-07-23 15:59:59 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |
| `processed_at` | datetime | 50 | 2026-06-25 01:57:07 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.06) | 高 |
| `created_at` | datetime | 50 | 2026-06-25 09:57:06 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 01:57:07 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.06) | 高 |

### `bill_subscriptions`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `billing_anchor_at` | datetime | 50 | 2026-06-25 01:57:06 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.06) | 高 |
| `current_period_start_at` | datetime | 50 | 2026-06-25 01:57:06 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.06) | 高 |
| `current_period_end_at` | datetime | 50 | 2026-07-23 15:59:59 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |
| `grace_period_end_at` | datetime | 50 | — | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 中 |
| `last_renewed_at` | datetime | 50 | 2026-06-25 01:57:06 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.06) | 高 |
| `last_failed_at` | datetime | 50 | — | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 中 |
| `created_at` | datetime | 50 | 2026-06-25 09:57:06 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 01:57:07 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.06) | 高 |

### `bill_usage`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 10:00:57 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=0.0) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 10:00:57 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=0.0) | 高 |

### `credit_ledger_entries`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `expires_at` | datetime | 50 | 2027-04-20 17:40:56 | 🌐 UTC | consumable_from/expires_at 为UTC配置值 | 高 |
| `consumable_from` | datetime | 50 | 2026-06-25 01:57:06 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.06) | 高 |
| `created_at` | datetime | 50 | 2026-06-25 10:00:57 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=0.0) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 10:00:57 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=0.0) | 高 |

### `credit_usage_rates`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `effective_from` | datetime | 50 | 2026-05-13 00:00:00 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |
| `effective_to` | datetime | 50 | — | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 中 |
| `created_at` | datetime | 50 | 2026-06-24 14:47:11 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 50 | 2026-06-24 14:47:11 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `credit_wallet_buckets`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `effective_from` | datetime | 50 | 2026-06-25 01:57:06 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.06) | 高 |
| `effective_to` | datetime | 50 | 2026-07-10 01:57:06 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |
| `created_at` | datetime | 50 | 2026-06-25 09:57:06 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 09:56:51 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.07) | 高 |

### `credit_wallets`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 09:57:06 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 01:57:07 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.06) | 高 |

### `learn_generated_audios`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 07:10:26 | 🕗 北京时间 | 小时分布低谷在北京凌晨2-7点(实测直方图) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 07:10:26 | 🕗 北京时间 | 小时分布低谷在北京凌晨2-7点(实测直方图) | 高 |

### `learn_generated_blocks`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 10:00:59 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=0.0) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 10:00:59 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=0.0) | 高 |

### `learn_generated_elements`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 10:00:59 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=0.0) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 10:00:59 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=0.0) | 高 |

### `learn_lesson_feedbacks`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 09:52:44 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.14) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 09:52:44 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.14) | 高 |

### `learn_progress_records`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 10:00:58 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=0.0) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 10:00:58 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=0.0) | 高 |

### `migration_sync_log`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `sync_time` | datetime | 50 | 2025-09-09 23:14:58 | 🌐 UTC | 一次性迁移批处理(2025-09),代码用 datetime.now()→UTC;样本陈旧无法以活动验证 | 中 |
| `created_at` | datetime | 50 | 2025-09-09 23:14:58 | 🌐 UTC | 一次性迁移批处理(2025-09),代码用 datetime.now()→UTC;样本陈旧无法以活动验证 | 中 |

### `notification_records`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `requested_at` | datetime | 50 | 2026-06-25 02:00:02 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.02) | 高 |
| `attempted_at` | datetime | 50 | 2026-06-25 02:00:02 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.02) | 高 |
| `sent_at` | datetime | 50 | 2026-06-25 02:00:02 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.02) | 高 |
| `created_at` | datetime | 50 | 2026-06-25 10:00:01 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.02) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 02:00:02 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.02) | 高 |

### `notification_templates`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `last_synced_at` | datetime | 10 | 2026-06-23 04:57:38 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |
| `created_at` | datetime | 10 | 2026-06-05 09:33:18 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 10 | 2026-06-23 04:57:38 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |

### `order_alipay_orders`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 0 | — | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00(当前无数据,按代码) | 中 |
| `updated_at` | datetime | 0 | — | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00(当前无数据,按代码) | 中 |

### `order_banner_info`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 3 | — | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00; | 高 |
| `updated_at` | datetime | 3 | — | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00; | 高 |

### `order_orders`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 09:08:02 | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00; | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 09:08:02 | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00; | 高 |

### `order_pingxx_orders`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `paid_at` | datetime | 50 | 2026-06-24 20:31:22 | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00; | 高 |
| `refunded_at` | datetime | 50 | 2026-06-24 20:31:22 | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00; | 高 |
| `closed_at` | datetime | 50 | 2026-06-24 20:31:22 | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00; | 高 |
| `failed_at` | datetime | 50 | 2026-06-24 20:31:22 | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00; | 高 |
| `created_at` | datetime | 50 | 2026-06-24 20:31:22 | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00; | 高 |
| `updated_at` | datetime | 50 | 2026-06-24 20:31:22 | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00; | 高 |

### `order_stripe_orders`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 0 | — | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00(当前无数据,按代码) | 中 |
| `updated_at` | datetime | 0 | — | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00(当前无数据,按代码) | 中 |

### `order_wechatpay_orders`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 0 | — | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00(当前无数据,按代码) | 中 |
| `updated_at` | datetime | 0 | — | 🕗 北京时间 | order 模型全部 func.now()→服务器+08:00(当前无数据,按代码) | 中 |

### `promo_coupon_usages`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-17 21:14:24 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 50 | 2026-06-17 21:17:04 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `promo_coupons`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `start` | datetime | 50 | 2026-06-17 00:00:00 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `end` | datetime | 50 | 2046-03-26 00:00:00 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `created_at` | datetime | 50 | 2026-06-17 21:14:24 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 50 | 2026-06-17 21:17:04 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `promo_promos`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `start_at` | datetime | 7 | 2025-11-11 21:58:22 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `end_at` | datetime | 7 | 2025-11-11 21:57:56 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `created_at` | datetime | 7 | 2025-09-04 21:15:06 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 7 | 2025-11-11 21:58:22 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `promo_redemptions`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-02-02 21:03:59 | 🕗 北京时间 | 小时分布低谷在北京凌晨2-7点(实测直方图) | 高 |
| `updated_at` | datetime | 50 | 2026-04-30 13:53:10 | 🕗 北京时间 | 小时分布低谷在北京凌晨2-7点(实测直方图) | 高 |

### `referral_campaign_reward_rules`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `starts_at` | datetime | 1 | 2026-06-12 00:00:00 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |
| `ends_at` | datetime | 1 | 2027-02-28 23:59:00 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |
| `created_at` | datetime | 1 | 2026-06-12 10:57:54 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 1 | 2026-06-12 10:57:54 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `referral_campaigns`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `starts_at` | datetime | 1 | 2026-06-12 00:00:00 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |
| `ends_at` | datetime | 1 | 2027-02-28 23:59:00 | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 高 |
| `created_at` | datetime | 1 | 2026-06-12 10:57:54 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 1 | 2026-06-12 10:57:54 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `referral_invite_codes`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `generated_at` | datetime | 50 | 2026-06-24 09:29:20 | 🌐 UTC | 同行较 created_at 早8h(配对) | 高 |
| `created_at` | datetime | 50 | 2026-06-24 17:29:20 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 50 | 2026-06-24 17:29:20 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `referral_invite_events`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-24 20:55:02 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `referral_invite_relations`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `bound_at` | datetime | 21 | 2026-06-22 09:10:28 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `created_at` | datetime | 21 | 2026-06-22 17:10:28 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 21 | 2026-06-22 17:10:28 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `referral_invite_rewards`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `effective_at` | datetime | 21 | — | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 中 |
| `expires_at` | datetime | 21 | — | 🌐 UTC | 业务/事件字段由 Python(datetime.now/utcnow)写入,应用服务器运行于UTC | 中 |
| `created_at` | datetime | 21 | 2026-06-22 17:10:28 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 21 | 2026-06-22 17:10:28 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `resource`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | timestamp | 50 | 2026-06-24 19:57:12 | 🕗 北京时间 | 小时分布低谷在北京凌晨2-7点(实测直方图) | 高 |
| `updated_at` | timestamp | 50 | 2026-06-24 19:57:12 | 🕗 北京时间 | 小时分布低谷在北京凌晨2-7点(实测直方图) | 高 |

### `resource_usage`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | timestamp | 0 | — | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码);当前无数据 | 中 |
| `updated_at` | timestamp | 0 | — | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码);当前无数据 | 中 |

### `risk_control_result`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created` | timestamp | 50 | 2026-06-25 10:00:56 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.0) | 高 |
| `updated` | timestamp | 50 | 2026-06-25 10:00:56 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.0) | 高 |

### `scenario_favorite`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | timestamp | 0 | — | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码);当前无数据 | 中 |
| `updated_at` | timestamp | 0 | — | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码);当前无数据 | 中 |

### `scenario_resource`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | timestamp | 0 | — | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码);当前无数据 | 中 |

### `shifu_draft_outline_items`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 02:00:03 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.01) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 02:00:03 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.01) | 高 |

### `shifu_draft_shifus`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 01:59:31 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.02) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 02:00:56 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.0) | 高 |

### `shifu_log_draft_structs`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 02:00:56 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.0) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 02:00:56 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.0) | 高 |

### `shifu_log_published_structs`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 01:43:28 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.29) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 09:43:28 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.29) | 高 |

### `shifu_published_outline_items`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 01:43:28 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.29) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 09:43:51 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.28) | 高 |

### `shifu_published_shifus`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 09:43:28 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.29) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 09:43:51 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.28) | 高 |

### `shifu_user_archives`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `archived_at` | datetime | 50 | 2026-06-24 06:25:28 | 🌐 UTC | 小时分布反相(低谷北京晚间)→UTC,且 shifu 服务用 utcnow | 高 |
| `created_at` | datetime | 50 | 2026-06-24 06:25:28 | 🌐 UTC | 小时分布反相(低谷北京晚间)→UTC,且 shifu 服务用 utcnow | 高 |
| `updated_at` | datetime | 50 | 2026-06-24 06:25:28 | 🌐 UTC | 小时分布反相(低谷北京晚间)→UTC,且 shifu 服务用 utcnow | 高 |

### `sys_configs`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 8 | 2026-06-24 14:51:26 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 8 | 2026-06-24 14:51:26 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `tts_minimax_cloned_voices`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 3 | 2026-06-24 15:45:57 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated_at` | datetime | 3 | 2026-06-24 15:46:07 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `ready_at` | datetime | 3 | 2026-06-24 07:46:08 | 🌐 UTC | 同行较 created_at 早8h(配对) | 高 |
| `deleted_at` | datetime | 3 | 2026-06-23 00:51:15 | 🌐 UTC | 同行较 updated_at 早8h(配对) | 高 |

### `user_auth_credentials`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 09:56:58 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.07) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 09:56:58 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.07) | 高 |

### `user_conversion`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created` | timestamp | 50 | 2026-06-25 09:56:36 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.07) | 高 |
| `updated` | timestamp | 50 | 2026-06-25 09:56:36 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.07) | 高 |

### `user_feedback`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created` | timestamp | 50 | 2026-06-08 22:18:48 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |
| `updated` | timestamp | 50 | 2026-06-08 22:18:48 | 🕗 北京时间 | func.now() 默认→DB会话+08:00(代码) | 中 |

### `user_onboarding_states`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `completed_at` | datetime | 50 | 2026-06-25 01:57:10 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.06) | 高 |
| `created_at` | datetime | 50 | 2026-06-25 09:57:09 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 09:57:09 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |

### `user_token`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `token_expired_at` | timestamp | 50 | 2026-07-02 01:57:06 | 🌐 UTC | 同行UTC(token_store.py 用 utcnow) | 高 |
| `created` | timestamp | 50 | 2026-06-25 09:57:06 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |
| `updated` | timestamp | 50 | 2026-06-25 09:57:06 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |

### `user_users`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `birthday` | date | 50 | — | ⬜ 日期(无时区) | date 仅日期,无时分秒 | — |
| `created_at` | datetime | 50 | 2026-06-25 09:56:36 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.07) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 09:56:58 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.07) | 高 |
| `creator_activated_at` | datetime | 50 | 2026-06-25 01:34:53 | 🌐 UTC | 最新值≈当前UTC(实测 dh_utc=-0.43) | 高 |

### `user_verify_code`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created` | timestamp | 50 | 2026-06-25 09:57:06 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |
| `updated` | timestamp | 50 | 2026-06-25 09:57:06 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.06) | 高 |

### `var_variable_values`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 10:00:55 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.0) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 10:00:55 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.0) | 高 |

### `var_variables`

| 字段 | 类型 | 最新50行非空 | 最新样本值 | 判定 | 依据 | 置信度 |
|---|---|---|---|---|---|---|
| `created_at` | datetime | 50 | 2026-06-25 09:43:12 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.3) | 高 |
| `updated_at` | datetime | 50 | 2026-06-25 09:43:12 | 🕗 北京时间 | 最新值≈当前北京时间(实测 dh_bj=-0.3) | 高 |

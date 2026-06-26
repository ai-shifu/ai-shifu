# 时间统一改造 — 进度记录

> 配套核查报告:`todo/time_list.md`
> 目标:数据库以 **UTC** 为准;网页(国内/国外)与 skill 调用都能显示**准确的当地时区**。

## 背景结论(为什么改)

- 旧问题:178 个时间字段中 118 个北京时间 / 59 个 UTC,根因是两条写入路径落在不同时区:
  - `func.now()` 在 **DB 端**按会话时区(`+08:00`)求值 → 北京时间;
  - Python `datetime.now()/utcnow()` 在 **UTC 进程**求值 → UTC。
- 展示侧三条路径并存:① 客户端 `Intl` 转换(learner 页 / billing,已正确);② 服务端按 `?timezone=` 转换(mdflow/dashboard);③ 不转换原样显示(部分 admin operations → 显示 UTC,bug)。skill 完全不转换。

---

## 阶段一 ✅ 数据库写入统一 UTC(已完成)

**做法:连接层强制 UTC 会话 + 模型默认值改 Python UTC。无需 Alembic 迁移、不改列类型。**

- `src/api/flaskr/dao/__init__.py`:非 sqlite 引擎注入 `connect_args.init_command = "SET time_zone = '+00:00'"`(安全网,覆盖所有入口)。
- `src/api/flaskr/util/datetime.py`:新增 `now_utc()`(返回 naive UTC,不依赖进程 TZ)。
- 15 个 `models.py`:`default=func.now()` / `onupdate=func.now()` → `now_utc`;**保留 `server_default=func.now()`**;按需调整 `func` 导入。
  - 含 `BillingTableMixin`、`ReferralTableMixin`,以及 order/shifu/user/learn/promo/profile/metering/tts/resource/config/feedback/check_risk。
- `src/api/flaskr/service/promo/funcs.py`:批量 update 的 `func.now()` → `now_utc()`。
- 核查:`get_now_time()`(默认 Asia/Shanghai)全代码仅再导出、无写入调用,无风险,未改。

**验证**:ruff 通过;连接层注入逻辑单测(mysql 注入 / sqlite 跳过)通过;ORM 写入读回 ≈ 当前 UTC;`promo/referral/user/billing` 聚焦 pytest **452 passed**。

**已知影响(用户确认可接受)**:历史 TIMESTAMP 列读取偏移 8h;历史 DATETIME 列不变。

---

## 阶段二 ✅ 协作规范(已完成)

- 根 `AGENTS.md` 增加硬规则:时间一律 UTC,后端写库用 `now_utc()`,新模型默认值用 `now_utc`,禁止 `func.now()`/裸 `datetime.now()/utcnow()` 存储时间。
- 已运行 `generate_ai_collab_docs.py` 与 `check_repo_harness.py`(通过),无镜像 drift。

---

## 阶段三 ✅ Skill 时区(场景 C,已完成)

仓库:`/Users/aichy/work/aishifu/skills`(独立仓库)

- `skills/ai-shifu-course-creator/scripts/shifu-cli.py`:
  - `fmt_time()`:解析后 `astimezone()` 转**机器本地时区**;无偏移裸串按 UTC 解释。覆盖 `cmd_list`/`cmd_history`/`_auto_pull_overwrite`。
  - `exported_at`:`datetime.now()` → `datetime.utcnow()`(一致性)。
- 文档:`references/analytics/{privacy-and-presentation,recipes}.md` 的 Translation Gate 注明"后端时间为 UTC,展示前转本地"。

**验证**:`TZ=Asia/Shanghai` 下 `01:00Z`(及裸串)→ `09:00`、空值 → `""`,断言通过。

---

## 阶段四 ✅ admin operations 后端本地化(场景 A/B 运营后台,已完成)

> 经测试证实这些 admin 字段是**刻意 Naive 显示 + 后端负责本地化**(`LearnOrdersTab.test` mock 浏览器时区为 UTC 仍期望原样)。故采用**后端本地化**(与 billing/dashboard 一致),而非前端翻转。曾误按前端翻转,已 `git checkout` 回退。

**后端(用 `flask.g` 注入,免逐层透传):**
- `src/api/flaskr/service/shifu/admin_operations/route.py` `_require_operator()`:读取校验 `?timezone=` 存入 `g.operator_timezone`(所有运营路由都过该守卫,62 处自动覆盖)。
- `src/api/flaskr/service/order/admin.py` `_format_admin_datetime` 与 `src/api/flaskr/service/shifu/admin_operations/courses.py` `_format_operator_datetime`:`tz_name` 由写死 `"UTC"` 改为读 `g.operator_timezone`(缺省 UTC,向后兼容)。

**前端(6 个页面 / 10 个数据型请求加 `timezone: getBrowserTimeZone()`;显示仍 `formatAdminNaiveDateTime` 不变):**
- `src/app/admin/operations/page.tsx`(课程列表)
- `.../orders/LearnOrdersTab.tsx`、`.../orders/OperatorOrderDetailSheet.tsx`
- `.../[shifu_bid]/page.tsx`(详情/用户/积分用量/用量明细)
- `.../[shifu_bid]/ratings/page.tsx`、`.../[shifu_bid]/follow-ups/page.tsx`
- 相应 `*.test.tsx` 更新调用参数断言(加 `timezone`)。

**验证**:后端 ruff 通过;helper 断言 `01:00Z + Asia/Shanghai → 09:00+08:00`、无 timezone 回退 `...Z`;`order/test_admin_orders`+`shifu/test_admin_courses`+`test_admin_course_detail` **100 passed**;前端 `type-check`+`eslint` 通过;受影响 jest **122 passed**。

---

## 已核实无缺口(无需处理)

- **后台 worker / celery**:经 `flaskr/common/celery_app.py:186 create_app()` 构建 → 同一 SQLAlchemy 引擎(UTC 会话 connect_args)+ 进程 `TZ=UTC`;celery `timezone` 取 `config.TZ`(=UTC),beat crontab 按 UTC 调度。写库与调度均为 UTC。
- **多库 binds**:生产无 `SQLALCHEMY_BINDS`(仅测试用),单引擎已被 connect_args 覆盖。
- **`time.time()`**(20 处):epoch 秒,与时区无关。

---

## ⏳ 后续计划(按优先级;完成后在此打勾)

### P1 — 收口性 ✅ 已完成
- [x] **积分订单(credit orders / bill_*)运营后台本地化**
  - 后端列表 `build_operator_credit_orders_page` / 详情 `get_operator_credit_order_detail` 本已支持 `timezone_name`;本次在 `admin_operations/route.py` 两个 credit 路由把 `_require_operator()` 存入的 `g.operator_timezone` 作 `timezone_name` 传入。
  - 前端 `CreditOrdersTab` / `CreditOrderDetailDialog` 请求加 `timezone: getBrowserTimeZone()`;相应 `CreditOrdersTab.test.tsx` 断言补 `timezone`。
  - 验证:后端 `test_admin_orders` **19 passed**;前端 `CreditOrdersTab.test` **9 passed**;type-check/eslint 通过。
- [x] **补永久回归测试**
  - `tests/common/test_now_utc.py`:`now_utc()` 返回 naive UTC;模型默认值写入即 UTC。
  - `tests/service/shifu/test_operator_datetime_localization.py`:`_format_admin_datetime`/`_format_operator_datetime` 在 `g.operator_timezone` 下本地化、缺省回退 `...Z`。
  - 验证:**4 passed**。

### P2 — 健壮性 / 一致性
- [ ] **learner(终端用户)页面快速审计**:确认无"裸显示后端时间"或"把 UTC 当本地"之处(此前仅重点核对 admin/billing,learner 页假定走客户端 `Intl` 转换但未逐页核对)。
- [ ] **API 时间序列化格式长期统一**:现状混杂(`Z` / `+00:00` / 裸串 / 预格式化 `*_display`),前端 3 套解析器。建议二选一:全返回带偏移 UTC ISO + 客户端转换,或全服务端按 `?timezone=` 转换。
- [ ] **billing `+08:00` 兜底分支**(`src/cook-web/src/lib/billing.ts` `BILLING_LEGACY_SOURCE_OFFSET`):当前不可达;如要与 UTC 体系一致可改 `+00:00`(防御性,运行时无影响)。

### P3 — 知悉/产品&运维决策(不一定改)
- [ ] **"日"聚合按 UTC 天**:`bill_daily_*` 窗口为 UTC 午夜(=北京 08:00)。统一后一致,但若运营要"北京天"口径需产品决策。
- [ ] **保持部署 `TZ=UTC`**:序列化对 naive 值取 app `TZ` 作源时区;国内外 k8s 均未设 TZ(默认 UTC),正确。注意 `DEFAULT_TIMEZONE` 默认 `Asia/Shanghai` 是潜在脚枪,勿接入序列化路径。
- [ ] **历史数据混时区**:跨迁移点的历史报表不一致(已确认不回刷)。
- [ ] **Go / planB 服务**:若也写这些库表的时间列,需同样对齐 UTC(独立服务,本次未动)。

---

## 提交状态

- 后端阶段一/二、skill 阶段三、阶段四(admin operations)改动均在工作区,**尚未提交**。
- 涉及两个仓库:`ai-shifu`(后端 + cook-web + AGENTS.md)与 `skills`(shifu-cli + 文档)。

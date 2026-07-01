# Billing 时区死管道清理 — 执行计划

> 自包含执行文档。时区物理收口已完成（分支 `aichy/time-260620`，8 个 commit，`fmt` 为唯一 UTC 出口）。
> 本计划清理 billing 残留的 `timezone_name` 死参数链与前端 `?timezone=` 注入。
> conda python: `/opt/homebrew/Caskroom/miniconda/base/envs/ai-shifu/bin/python`
> 测试：`cd src/api && pytest tests/service/billing -q`；`cd src/cook-web && ./node_modules/.bin/jest src/components/billing src/hooks src/app/admin/billing`
> 注意：本地 dev billing 未启用（端点返回 `7103`），无法实时验证，**完全依赖单测**。

## 背景

时区收口后，billing DTO 时间字段已是 `datetime | None`，`fmt` 在序列化时统一转 UTC `Z`。但 billing 模块仍残留一套 `timezone_name` 线程：后端从 `?timezone=` 读取浏览器时区并贯穿 serialize/read_models/routes 等约 9 个文件、~100 处参数；前端用 `withBillingTimezone`/`buildBillingSwrKey` 注入。**后端已忽略这个参数**（serializers 直接放 raw datetime 给 DTO），所以是死代码——但需谨慎清理，因为有 2 处不是纯死代码（见下）。

**目标**：删除 billing 的 `timezone_name` 死参数链 + 前端 timezone 注入，使 billing 与其他 4 模块一致（前端不发 `?timezone=`，后端不接收）。

## ⚠️ 两个非纯死代码点（必须先处理，不能只删参数）

1. **`trials.py` 仍走 `serialize_dt`**（`from .primitives import serialize_dt as _serialize_dt`，用于 `granted_at`/`expires_at`/`welcome_dialog_acknowledged_at`/`acknowledged_at`，行 ~98/103/108/827）。
   - 现状：`serialize_dt(...)` 返回 ISO **字符串**喂给已改为 `datetime | None` 的 DTO 字段 → Pydantic 把字符串重解析回 datetime → fmt 再转 UTC。**碰巧正确**（aware→UTC），但是双重转换、且仍读 timezone_name。
   - 收口：改为直接传 **raw datetime**（`granted_at=trial.granted_at` 等），与 serializers.py 一致。
2. **`credit_notifications.py` 的 `_serialize_dt`**（行 1233 = `return _format_sms_datetime(app, value)`，用于通知记录 dict 的 `expires_at`，行 1530/1647/1816/1865）。
   - 这走 **SMS 本地时区**（`_format_sms_datetime` → app `DEFAULT_TIMEZONE`），不是 UTC。
   - **判定**：这些是 admin **通知记录**响应 dict（非 SMS 正文）。应改为 UTC `Z`（与其他 admin 一致）——把 `_serialize_dt` 在这些点替换为 `flaskr.route.common.fmt` 风格的 UTC 串，或直接放 raw datetime（若该 dict 经 `make_common_response`→`fmt`）。**需先确认这些 dict 是否经 fmt 序列化**（grep 调用链）；若经 fmt，直接放 raw datetime 最干净。保留真正的 SMS 正文路径 `_format_sms_datetime`（Step 9 已定）。

## Step 1 — 后端：移除 `timezone_name` 参数链

按文件（`timezone_name` 出现数）：`read_models.py`(41)、`serializers.py`(21)、`routes.py`(16)、`trials.py`(15)、`domains.py`(8)、`campaigns.py`(6)、`credit_notifications.py`(3)、`tasks.py`(2)、`primitives.py`(2)。

1. 先做上面"两个非纯死代码点"（trials 改 raw datetime；credit_notifications 通知 dict 改 UTC）。
2. `routes.py`：删 `_get_timezone_name()` 定义（行 78）+ 12 处 `timezone_name=_get_timezone_name(),` 调用实参。删 `request.args.get("timezone"...)` 残留与未用 import。
3. 逐文件删 serialize/build 函数签名里的 `*, timezone_name: str | None = None` 形参 + 函数体内 `timezone_name` 透传 + 所有调用实参 `timezone_name=...`。建议用脚本：
   - 删形参：正则匹配多行签名里的 `\n\s*timezone_name: str \| None = None,`。
   - 删实参：正则匹配 `\n\s*timezone_name=[\w._()]+,`。
   - 每个文件 `py_compile` + 跑 billing 单测。
4. `primitives.py`：`serialize_dt`（行 227）在 trials 改 raw 后应无人用 → 删 def + 其 `timezone_name` 参数。确认 `from .primitives import serialize_dt` 已无引用再删。
5. 清理各文件因此产生的未用 import（`get_app_timezone` / `serialize_with_app_timezone` / `request` 等）。

**关键事实**：serializers.py 早已不用 timezone_name（收口时 unwrap 成 raw），所以删形参只是去掉死参数，不改行为。read_models/campaigns/domains 把 timezone_name 往下透传到 serializers，删除后调用方少传一个被忽略的 kwarg。

## Step 2 — 后端测试

`tests/service/billing/` 里断言/构造带 `timezone_name=` 或 `?timezone=` 的用例：
- 删除调用里的 `timezone_name=` 实参；
- 之前重写过的 `test_overview_..._ignoring_request_timezone` / `test_ledger_emits_utc_...` / `test_build_billing_ledger_page_returns_raw_created_at` 已断言"忽略 ?timezone= 恒 UTC Z"，保持；
- 若有 monkeypatch `_get_timezone_name` 的用例，删除。
- `pytest tests/service/billing -q` 必须全绿（当前 378 passed 基线）。

## Step 3 — 前端：移除 timezone 注入

`src/lib/billing.ts`：
- 删 `withBillingTimezone(params, timezone)`（行 ~450）。
- 改 `buildBillingSwrKey(baseKey, timezone, ...parts)` → `buildBillingSwrKey(baseKey, ...parts)`（去掉 timezone 维度）——**注意改签名后所有调用方的参数位置都要改**。

消费方（去掉 `getBrowserTimeZone()` + `withBillingTimezone` + buildBillingSwrKey 的 timezone 实参）：
- `src/hooks/useBillingData.ts`、`src/hooks/useBillingAdminPagedQuery.ts`
- `src/components/billing/BillingOverviewTab.tsx`、`AdminBillingExceptionsPanel.tsx`、`AdminBillingReportsPanel.tsx`
- `src/app/admin/billing/components/BillingRecentActivitySection.tsx`
- `src/app/admin/operations/users/page.tsx`（`buildBillingSwrKey(BILLING_OVERVIEW_SWR_KEY, getBrowserTimeZone())` → 去 timezone）

显示不受影响：billing 前端用 `parseBillingDateValue + Intl`（`src/lib/billing.ts`），对 UTC `Z` 已正确按浏览器时区显示，**不依赖** `timezone` 参数。

## Step 4 — 前端测试

`src/components/billing/*.test.tsx`、`src/app/admin/billing/**/*.test.tsx`、`BillingRecentActivitySection.test.tsx`、`BillingOverviewTab.test.tsx` 等：
- 删 API 调用断言里的 `timezone:` 实参；
- 删 SWR key 断言里的 timezone 维度；
- 保留 `getBrowserTimeZone` mock（无害）或一并删除其在 billing 测试里的 mock。
- `./node_modules/.bin/jest src/components/billing src/hooks src/app/admin/billing` 全绿；`npx tsc --noEmit` 全绿。

## 验证
```bash
cd src/api && /opt/homebrew/Caskroom/miniconda/base/envs/ai-shifu/bin/python -m pytest tests/service/billing -q   # 378 baseline
cd src/cook-web && npx tsc --noEmit && ./node_modules/.bin/jest src/components/billing src/hooks src/app/admin/billing
# 残留检查
grep -rn "timezone_name\|withBillingTimezone\|_get_timezone_name" src/api/flaskr/service/billing | grep -v __pycache__   # 期望仅 _format_sms_datetime 相关(若保留)
grep -rn "withBillingTimezone\|buildBillingSwrKey(.*getBrowserTimeZone" src/cook-web/src   # 期望空
```

## 风险
1. **trials.py 双重转换**：必须改 raw datetime（否则保留死参数但行为仍依赖 Pydantic 重解析，不算清理干净）。
2. **credit_notifications 通知 dict**：先确认是否经 `fmt`；若是 → 放 raw datetime；若不是（手动 dict）→ 用 UTC `Z` 串。别误删真正的 SMS 正文 `_format_sms_datetime`（无浏览器路径，Asia/Shanghai 直出）。
3. **buildBillingSwrKey 改签名**：参数位置变化，逐调用方核对，靠 tsc 兜底。
4. **本地不可实时验证**（dev billing 7103）：完全靠 378 billing 单测 + tsc。改完务必跑满。
5. 纯死参数删除（serializers/read_models 等）行为不变；唯 trials/credit_notifications 两点是真实收口，重点测。

## 完成后
- 更新 memory `timezone-refactor.md`：标记 billing 死管道清理完成，时区重构 100% 收尾。
- 本文件移入 `docs/exec-plans/completed/` 或删除。

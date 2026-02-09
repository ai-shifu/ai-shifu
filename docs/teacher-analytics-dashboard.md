# Teacher Analytics Dashboard (v1)

## Background

AI-Shifu already stores rich learning and conversation data for a published course (Shifu). This document proposes a **teacher-facing dashboard** (initial integration) to help course creators/collaborators understand:

1. Learner progress
2. Course completion
3. Follow-up questions (ASK) metrics
4. Learner personalization (profiles/variables)
5. Follow-up details (Q/A logs)

Requirements:

- Provide **detailed views** (tables + drill-down per learner)
- Provide **chart analysis** (ECharts)
- Frontend chart library: **`echarts` + `echarts-for-react`**
- Prefer **additive changes** with minimal disturbance to existing business logic
- Make chart components **wrappable/composable** for future reuse

## What We Have Today (Relevant Data Sources)

### Course structure (published)

- `shifu_log_published_structs` (`flaskr.service.shifu.models.LogPublishedStruct`)
  - JSON serialized `HistoryItem` tree (type: `shifu`, `outline`, `block`)
- `shifu_published_outline_items` (`PublishedOutlineItem`)
  - `outline_item_bid`, `title`, `type` (trial/normal/guest), `hidden`

This is the **source of truth** for what learners can study in production mode.

### Learner progress

- `learn_progress_records` (`flaskr.service.learn.models.LearnProgressRecord`)
  - Key fields:
    - `shifu_bid`, `outline_item_bid`, `user_bid`
    - `status` (`LEARN_STATUS_*`)
    - `block_position` (coarse pointer inside an outline’s block list)
    - `updated_at` (used as “last activity” proxy)
  - Note: there can be multiple records per `(user_bid, outline_item_bid)`; code paths often pick the latest by `id`.

### Follow-up Q/A logs (追问)

- `learn_generated_blocks` (`LearnGeneratedBlock`)
  - Follow-up handler: `flaskr.service.learn.handle_input_ask.handle_input_ask`
  - For follow-ups:
    - Student question: `type = BLOCK_TYPE_MDASK_VALUE`, `role = ROLE_STUDENT`
    - Teacher answer: `type = BLOCK_TYPE_MDANSWER_VALUE`, `role = ROLE_TEACHER`
  - Has timestamps: `created_at`, plus `outline_item_bid`, `progress_record_bid`, `position`.

### Personalization data

- Profile item definitions: `flaskr.service.profile.profile_manage.get_profile_item_definition_list(parent_id=shifu_bid)`
- User variable values: `var_variable_values` (`flaskr.service.profile.models.VariableValue`)
  - Global/system scope values: `shifu_bid == ""` (core profile labels)
  - Course scope values: `shifu_bid == <course_id>` (custom variables collected during learning)
  - Read helper used in learning runtime: `flaskr.service.profile.funcs.get_user_profiles`

### Enrollment candidates (optional enhancement)

- `order_orders` (`flaskr.service.order.models.Order`)
  - Can be used to include “purchased but never started” learners.
  - V1 can start with “learners with progress records”; optionally union orders later.

## Metrics Definitions (V1)

### Outline set (what counts toward progress)

Default for V1:

- Use **published** outline items from `LogPublishedStruct` + `PublishedOutlineItem`.
- Exclude `hidden == 1`.
- Count only `type == UNIT_TYPE_VALUE_NORMAL` as “required lessons”.

Optional flags for future:

- `include_trial=true`: include trial outlines
- `include_guest=true`: include guest outlines

### Learner set (who is included)

Default for V1:

- Learners are users who have **at least one** `LearnProgressRecord` for this `shifu_bid` (latest non-reset record).

Optional later:

- Union in paid orders (`Order.status == ORDER_STATUS_SUCCESS`) to include not-started learners.

### Per-learner summary fields

- `required_outline_total`
- `completed_outline_count`
- `in_progress_outline_count`
- `progress_percent = completed / total` (0..1)
- `last_active_at = max(updated_at)` across latest progress records
- `follow_up_ask_count = count(MDASK)` (time-range aware for charting; total for per-learner)

### Course-level overview

- `learner_count`
- `completion_count` (learners with `completed == total`)
- `completion_rate`
- `progress_distribution` (bucketed)
- `follow_up_trend` (daily count within date range)
- `top_outlines_by_follow_ups`
- `top_learners_by_follow_ups`

## Backend Design

### New service module

Add a new additive service module:

- `src/api/flaskr/service/dashboard/`
  - `dtos.py` (Pydantic DTOs with `__json__`)
  - `funcs.py` (query/aggregation helpers)
  - `routes.py` (HTTP routes, `@inject`)

### Permission model

Teacher dashboard must be restricted:

- Require login (existing `before_request` sets `request.user`)
- Require Shifu permission:
  - `shifu_permission_verification(app, request.user.user_id, shifu_bid, "view")`

### Proposed endpoints (V1)

All endpoints under `/api/dashboard`, additive to avoid disturbing existing routes.

1. `GET /api/dashboard/shifus/{shifu_bid}/outlines`
   - Returns published outline list used for progress calculation and filtering.

2. `GET /api/dashboard/shifus/{shifu_bid}/overview`
   - Query params:
     - `start_date` (YYYY-MM-DD, optional)
     - `end_date` (YYYY-MM-DD, optional)
     - `include_trial` / `include_guest` (optional)
   - Returns KPI + chart-ready series (daily arrays, top-N arrays, buckets).

3. `GET /api/dashboard/shifus/{shifu_bid}/learners`
   - Query params:
     - `page_index` (default 1)
     - `page_size` (default 20, max 100)
     - `keyword` (optional; matches user_bid / mobile / nickname)
     - `sort` (optional; e.g. `last_active_at_desc`, `progress_desc`, `followups_desc`)
   - Returns paginated learner summaries.

4. `GET /api/dashboard/shifus/{shifu_bid}/learners/{user_bid}`
   - Returns:
     - outline progress statuses (per outline)
     - learner core info
     - learner course-scoped variables (from `get_user_profiles`)
     - follow-up aggregates (count by outline, recent items)

5. `GET /api/dashboard/shifus/{shifu_bid}/learners/{user_bid}/followups`
   - Query params:
     - `outline_item_bid` (optional filter)
     - `start_time`, `end_time` (optional, ISO or `YYYY-MM-DD`)
     - `page_index`, `page_size`
   - Returns follow-up items (question/answer, timestamps, outline info).

### Data access patterns (important implementation notes)

**Hard constraint: no database JOIN queries.**

- Do not use SQL JOIN / SQLAlchemy `.join()` / relationship eager-loading to combine tables.
- For parent/child lookups, always:
  1. Query the parent table first to get the parent keys (`*_bid`, `id`, `parent_bid`, etc.).
  2. Query the child table with `IN (...)` using those keys.
  3. Combine the result sets in Python with dict maps.
- If an `IN (...)` list can grow large, chunk it (e.g. 500-1000 ids per query) and merge the chunks in memory.

Examples:

- Published outlines:
  - Load `LogPublishedStruct` (parent) to obtain the outline `id` / `outline_item_bid` list.
  - Load `PublishedOutlineItem` (child) with `PublishedOutlineItem.id.in_(...)`.
  - Merge by `outline_item_bid` in Python.
- Learner list:
  - Load latest `LearnProgressRecord` rows first (parent) and collect `user_bid` list.
  - Load `UserEntity` (child) with `UserEntity.user_bid.in_(...)`.
  - Load `AuthCredential` (child) with `AuthCredential.user_bid.in_(...)`.
  - Merge user + credential + progress in Python.

Other important patterns:

- Always use **latest** progress record per `(user_bid, outline_item_bid)`:
  - Build a `max(id)` subquery grouped by `(user_bid, outline_item_bid)` with `status != LEARN_STATUS_RESET` and `deleted == 0`, then load full rows via `LearnProgressRecord.id.in_(subquery)`.
- Avoid N+1 by batching with `IN (...)` queries:
  - Batch-load users/credentials for learner lists.
  - Batch-load ask counts via grouped queries on `learn_generated_blocks` (no joins).
- Time range for trends:
  - `DATE(created_at)` group-by for follow-up trend.

### Swagger schemas

Follow existing convention:

- `@register_schema_to_swagger`
- DTOs are `pydantic.BaseModel` with explicit `__json__`.

## Frontend Design (Cook Web)

### Route

Add a new admin page:

- `src/cook-web/src/app/admin/dashboard/page.tsx`

Minimal existing changes:

- Add a new menu item in `src/cook-web/src/app/admin/layout.tsx` pointing to `/admin/dashboard`.

### API client integration

Add new endpoints to:

- `src/cook-web/src/api/api.ts`

Then use the generated functions via `import api from '@/api'`.

### Chart component architecture (ECharts)

Add reusable primitives:

- `src/cook-web/src/components/charts/EChart.tsx`
  - Client-only wrapper around `echarts-for-react` via `next/dynamic`
  - Props: `option`, `style`, `loading`, `onEvents`, `opts`, `notMerge`, `lazyUpdate`
- `src/cook-web/src/components/charts/ChartCard.tsx`
  - Standardized card chrome: title, subtitle, actions slot, chart area

Option builders (future-friendly):

- `src/cook-web/src/lib/charts/options.ts`
  - `buildLineOption(...)`
  - `buildBarOption(...)`
  - Common theme tokens aligned with Tailwind variables

### UI layout (V1)

Dashboard page sections:

1. Header controls
   - Course selector (reuses existing shifu list API)
   - Date range selector (reuse `Calendar` / `Popover` patterns from admin orders)
2. KPI cards
   - Learners, completion rate, follow-up totals, active learners (optional)
3. Charts grid
   - Progress distribution (bar)
   - Follow-up trend (line)
   - Top outlines by follow-ups (bar)
4. Learner table + drill-down
   - Table: learner info + progress + follow-ups + last active
   - Row click opens a `Sheet` with tabs:
     - Progress (outline list statuses)
     - Follow-ups (Q/A list with filters)
     - Personalization (variables table)

### i18n

Add a new namespace file:

- `src/i18n/en-US/modules/dashboard.json`
- `src/i18n/zh-CN/modules/dashboard.json`

Keys example:

- `module.dashboard.title`
- `module.dashboard.kpi.learners`
- `module.dashboard.chart.followUpsTrend`
- `module.dashboard.table.progress`

## Testing & Validation

Backend:

- Add API tests under `src/api/tests/service/dashboard/`
- Focus on:
  - permission enforcement
  - outline set correctness (hidden excluded)
  - “latest record” selection correctness
  - pagination stability

Frontend:

- Basic render tests for chart wrappers (Jest)
- Manual QA checklist:
  - load dashboard
  - switch course
  - switch date range
  - open learner detail and paginate follow-ups

## Risks / Open Questions

1. **Learner set definition**: should it include “purchased but not started” by default?
2. **Progress precision**: `block_position` enables intra-outline progress, but total blocks length requires parsing MarkdownFlow; V1 uses outline-level completion.
3. **PII exposure**: showing mobile/email in teacher dashboard might require masking or role-based gating.
4. **Performance**: large courses may need caching/materialized aggregates and better DB indexes (post-V1).

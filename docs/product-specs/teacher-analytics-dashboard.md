---
title: Teacher Analytics Dashboard (v1)
status: implemented
owner_surface: shared
last_reviewed: 2026-08-16
canonical: true
---

# Teacher Analytics Dashboard (v1)

## Background

AI-Shifu stores rich learning and conversation data for a published course (Shifu). The implemented **teacher-facing dashboard** helps course owners and collaborators understand:

1. Learner progress
2. Course completion
3. Follow-up questions (ASK) metrics
4. Learner personalization (profiles/variables)
5. Follow-up details (Q/A logs)

The current implementation:

- Provide **detailed views** (tables + drill-down per learner)
- Present aggregate values as reusable metric cards
- Present courses, learners, follow-ups, and ratings through filterable, paginated tables
- Prefer **additive changes** with minimal disturbance to existing business logic

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
- `follow_up_ask_count = count(MDASK)` (time-range aware for filtered lists; total for per-learner)

### Course-level overview

- `learner_count`
- `completion_count` (learners with `completed == total`)
- `completion_rate`
- `order_count`
- `order_amount`
- `new_learner_count_last_7_days`
- `learning_learner_count`
- `active_learner_count_last_7_days`
- `total_follow_up_count`
- `rating_score`

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

### Implemented endpoints (V1)

All endpoints live under `/api/dashboard` and are additive to existing routes.

1. `GET /api/dashboard/entry`
   - Returns summary cards and a paginated course table.
   - Supports course keyword and last-active date filters.

2. `GET /api/dashboard/shifus/{shifu_bid}/detail`
   - Returns course basics and aggregate metrics for the metric-card grid.

3. `GET /api/dashboard/shifus/{shifu_bid}/learners`
   - Returns filterable, paginated learner summaries.

4. `GET /api/dashboard/shifus/{shifu_bid}/follow-ups`
   - Returns summary cards and a filterable, paginated follow-up table.

5. `GET /api/dashboard/shifus/{shifu_bid}/follow-ups/{generated_block_bid}/detail`
   - Returns the selected follow-up, its answer, and the surrounding timeline.

6. `GET /api/dashboard/shifus/{shifu_bid}/ratings`
   - Returns summary cards and a filterable, paginated rating table.

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
- Time range filters normalize their boundaries once and apply them to the corresponding entry, follow-up, learner, or rating query.

### Swagger schemas

Follow existing convention:

- `@register_schema_to_swagger`
- DTOs are `pydantic.BaseModel` with explicit `__json__`.

## Frontend Design (Cook Web)

### Route

The dashboard uses these admin routes:

- `src/cook-web/src/app/admin/dashboard/page.tsx`
- `src/cook-web/src/app/admin/dashboard/[shifu_bid]/page.tsx`
- `src/cook-web/src/app/admin/dashboard/[shifu_bid]/follow-ups/page.tsx`
- `src/cook-web/src/app/admin/dashboard/[shifu_bid]/ratings/page.tsx`

### API client integration

Dashboard endpoints are registered in:

- `src/cook-web/src/api/api.ts`

Then use the generated functions via `import api from '@/api'`.

### Metric card and table architecture

- Reuse `CourseMetricsCardGrid` for course, follow-up, and rating summaries.
- Reuse `AdminTableShell` for course, learner, follow-up, and rating lists so loading, empty state, footnotes, pagination, and sticky action columns stay consistent with the rest of the admin UI.
- Keep route-specific filters and row actions in the corresponding dashboard page or focused child component.

### UI layout (V1)

Dashboard surfaces:

1. Dashboard entry
   - Course keyword and last-active date filters
   - Course, learner, order, and revenue summary cards
   - Paginated course table with course-detail and order actions
2. Course detail
   - Basic course information and aggregate metric cards
   - Filterable learner table with progress, status, follow-up count, and dates
3. Follow-up detail
   - Summary cards and a filterable follow-up table
   - A sheet for the current Q/A record and its conversation timeline
4. Ratings
   - Summary cards and a filterable rating table

### i18n

Add a new namespace file:

- `src/i18n/en-US/modules/dashboard.json`
- `src/i18n/zh-CN/modules/dashboard.json`

Keys example:

- `module.dashboard.title`
- `module.dashboard.entry.kpi.learners`
- `module.dashboard.detail.metrics.completionRate`
- `module.dashboard.detail.learners.columns.progress`

## Testing & Validation

Backend:

- Add API tests under `src/api/tests/service/dashboard/`
- Focus on:
  - permission enforcement
  - outline set correctness (hidden excluded)
  - “latest record” selection correctness
  - pagination stability

Frontend:

- Render and interaction tests for the dashboard entry, course detail, follow-up list/detail, and ratings pages (Jest)
- Manual QA checklist:
  - load the dashboard and filter the course table
  - open a course detail and paginate/filter learners
  - open follow-up and rating lists, exercise filters, and inspect a follow-up

## Risks / Open Questions

1. **Learner set definition**: should it include “purchased but not started” by default?
2. **Progress precision**: `block_position` enables intra-outline progress, but total blocks length requires parsing MarkdownFlow; V1 uses outline-level completion.
3. **PII exposure**: showing mobile/email in teacher dashboard might require masking or role-based gating.
4. **Performance**: large courses may need caching/materialized aggregates and better DB indexes (post-V1).

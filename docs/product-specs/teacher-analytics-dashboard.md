---
title: Teacher Analytics Dashboard (v1)
status: implemented
owner_surface: shared
last_reviewed: 2026-08-16
canonical: true
---

# Teacher Analytics Dashboard (v1)

## Background

AI-Shifu stores rich learning and conversation data for a published course (Shifu). The implemented **teacher-facing dashboard** helps course owners understand:

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
  - Multiple records can exist per `(user_bid, outline_item_bid)`. Preserve the
    metric-specific history rules below instead of selecting one latest row.

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

## Implemented course progress metrics

The course-detail progress helpers in `flaskr/service/dashboard/funcs.py` use
these distinct populations and histories:

- `_load_course_leaf_outline_bids` selects visible, non-deleted published
  outlines and removes parents of visible outlines. It does not restrict the
  set to normal lessons or expose `include_trial` / `include_guest` flags.
- `_load_course_learner_bids` unions distinct users with any non-deleted,
  non-reset progress record and users with successful, non-deleted manual
  orders. It does not union every paid order.
- `_load_dashboard_course_learned_lesson_count_map` counts distinct eligible
  leaf lessons across all non-deleted, non-reset progress rows for each scoped
  learner. `_load_dashboard_course_last_learning_map` takes `max(updated_at)`
  across that learner's non-deleted, non-reset course rows. Neither selects a
  latest row per lesson.
- `_load_dashboard_course_completed_learner_bids` examines all non-deleted
  status records for each learner/leaf lesson, ordered by `created_at`, then
  `id`. A lesson counts as completed if any record is completed, or if a reset
  record has a later record. Thus completed followed by in-progress still
  counts, as does reset followed by restudy; reset alone does not. A learner is
  completed only when every eligible leaf counts; an empty leaf set yields no
  completed learners.
- `learning_learner_count` counts learners with at least one learned leaf who
  are not in the completed set. Learner display rows expose
  `learned_lesson_count` and `last_learning_at`; the historical proposed
  `completed_outline_count` / `progress_percent` fields are not their contract.

Use `DashboardCourseDetailDTO` and its nested DTOs for the `/detail` response
(`basic_info`, aggregate `metrics`, and `learning_mode_metrics`). The separate
`/learners` response uses `DashboardCourseDetailLearnersDTO`, whose `items` are
`DashboardCourseDetailLearnerItemDTO` rows. Both DTO families live in
`src/api/flaskr/service/dashboard/dtos.py`. Entry-page metrics have their own
time-window and population contract in
[Dashboard Entry Page Contract](dashboard-entry-page.md).

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
- Limit access to owned published courses. The entry page uses
  `_load_dashboard_course_meta_map(user_id)`; course-specific builders use
  `_load_dashboard_course_meta(user_id, shifu_bid)`. Both restrict
  `PublishedShifu.created_user_bid` to the requesting user and exclude deleted
  records and built-in demo courses.
- Collaborator `view` permission does not grant dashboard access. These builders
  do not call `shifu_permission_verification`; course-specific requests without
  an eligible owned course are rejected.

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

Query guidance reviewed against the implemented dashboard on 2026-09-26:

- Filter by the authorized course scope before aggregating or associating data.
  Course-specific requests use the targeted ownership check; the entry page
  uses its owned-course scope.
- Use bounded SQL joins, subqueries, and grouped aggregates where the existing
  query path requires them. Preserve one-row-per-learner or rating semantics
  and avoid multiplying counts when joining one-to-many records.
- Apply SQL filtering and pagination before hydrating page-only display fields
  where filters can be resolved in SQL. The follow-up `source_status` path is
  an explicit exception: it resolves candidate source status in Python, applies
  that filter, then computes the filtered total and slices the page. Paginating
  before that filter would give incorrect totals and incomplete pages.
  Compute summary metrics over the full eligible scope, not only the page.
- Retain the metric-specific progress history rules above. In particular,
  completion needs ordered reset/completion history; activity and learned-lesson
  aggregates use all eligible non-reset rows. Batch contact and other display
  lookups instead of adding per-row queries. Python maps remain appropriate
  for those bounded presentation joins.
- Normalize date boundaries once and keep API timestamps in UTC. Query
  optimizations must preserve empty-state, filter, ordering, and pagination
  contracts covered by the dashboard route and query-contract tests.

The entry route and its four metrics are specified in
[Dashboard Entry Page Contract](dashboard-entry-page.md); do not duplicate a
second route or metric definition here.

### Swagger schemas

Follow existing convention:

- `@register_schema_to_swagger`
- DTOs are `pydantic.BaseModel` with explicit `__json__`.

## Frontend Design (Cook Web)

### Route

The dashboard uses these admin routes:

- `src/web/src/app/admin/dashboard/page.tsx`
- `src/web/src/app/admin/dashboard/[shifu_bid]/page.tsx`
- `src/web/src/app/admin/dashboard/[shifu_bid]/follow-ups/page.tsx`
- `src/web/src/app/admin/dashboard/[shifu_bid]/ratings/page.tsx`

### API client integration

Dashboard endpoints are registered in:

- `src/web/src/api/api.ts`

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
  - metric-specific completion/reset history and non-reset aggregate semantics
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

---
title: Operator Course Visit Analytics
status: implemented
owner_surface: shared
last_reviewed: 2026-04-17
canonical: true
---

## Operator Course Visit Analytics

### Goal

Add a reliable operator-facing `访问人数` metric for the course detail page by
using Umami as the analytics source while keeping the admin UI dependent on the
business backend instead of querying Umami directly.

This document is intentionally implementation-ready. When a later task says
"implement course visit count from the Umami plan", it refers to this file.

### Product Decision

#### What the metric means

- `访问人数` = distinct logged-in users who opened the learner-side course page
  within a defined time window

#### Recommended first version

- show `近 30 天访问人数`
- do **not** show cumulative all-time visitor count in the first version

#### Why this is the first version

- Umami is good at time-window analytics and distinct visitor reporting
- all-time deduplicated visitor count is much harder to maintain correctly
- a rolling window is more useful for operators who care about recent course
  activity

### Non-Goals

- do not make the admin detail page call Umami APIs at request time
- do not read Umami's underlying tables directly from the product backend
- do not infer course visitors from generic page paths only
- do not reuse the existing generic `visit` event for course-level analytics

### High-Level Architecture

Use a three-stage pipeline:

1. learner frontend emits a dedicated Umami event with course identity
2. backend scheduled job syncs aggregated Umami stats into the business DB
3. operator detail API reads only from the business DB aggregation table

This keeps the admin surface stable, fast, auditable, and independent from
Umami availability during page load.

### Event Design

#### Dedicated event

Add a dedicated Umami event instead of relying on generic pageviews:

- event name: `course_visit`

#### Required event payload

- `shifu_bid`

#### Optional event payload

- `outline_item_bid`
- `entry_type`
  - examples: `catalog`, `deep_link`, `pay_redirect`, `resume`
- `preview_mode`
  - should normally be omitted or `false` for real learner visits

#### Why a dedicated event is required

- page path rules can change later
- the same course may be entered through different learner URLs
- event payload makes course-level aggregation explicit and stable

### Frontend Trigger Rules

Emit `course_visit` only when all of the following are true:

- current page is a real learner course route
- a valid `shifu_bid` is available
- the current visitor is logged in
- this is not creator preview mode
- this page load has not already emitted a visit for the same course in the
  current browser session

#### Suggested dedupe rule on the frontend

Use a session-level guard:

- key: `course_visit:<shifu_bid>`
- store in `sessionStorage`
- only emit once per browser tab session per course

This reduces noisy duplicate events caused by rerenders or intra-page state
changes while still allowing a later session to count as a new visit if Umami's
visitor model decides it should.

### Identity Rule

The metric is defined as distinct logged-in users, so Umami identify support is
required.

Use the existing Umami identify flow already present in the frontend and ensure
the distinct identity maps to the business user identity consistently.

#### Required property

- distinct id should map to stable logged-in user identity

#### Strong recommendation

- use the same stable `user_bid` currently used by product logic
- do not use nickname, email, or phone as the primary analytics identity

### Backend Data Ownership

The product backend must own the displayed metric.

That means:

- Umami is the source of analytics events
- business DB is the source of admin-page reads

The operator detail API should never need Umami credentials.

### Storage Design

Create a dedicated aggregation table for course analytics synced from Umami.

Suggested table:

- table name: `analytics_course_daily_stats`

Suggested columns:

- `id`
- `stat_date`
- `shifu_bid`
- `visit_count`
  - raw event count for `course_visit`
- `visitor_count`
  - distinct logged-in users for that day and course
- `source`
  - default `umami`
- `synced_at`
- `created_at`
- `updated_at`

Suggested uniqueness:

- unique index on `(stat_date, shifu_bid, source)`

### Why daily aggregation is the right first step

- it keeps the table small
- it supports rolling-window queries easily
- it avoids storing user-level analytics data in the product DB for the first
  version

### Sync Job Design

Add a scheduled backend job that periodically pulls Umami aggregation data and
upserts the daily table.

#### Sync cadence

Recommended first version:

- run hourly

#### Sync window

Recommended first version:

- backfill the last `N` days on every run
- suggested `N = 3`

#### Canonical timezone

Recommended first version:

- use `UTC` as the single canonical timezone for the sync job
- convert Umami event timestamps into UTC before deriving `stat_date`
- use the same UTC basis when calculating:
  - the `last N days` sync backfill window
  - the `last 30 days` snapshot window
- keep `window_start_date`, `window_end_date`, and `stat_date` all defined in
  UTC so daily buckets stay stable across environments and timezone changes

This makes late-arriving analytics updates less risky.

#### Job responsibilities

- query Umami for the `course_visit` event
- aggregate by:
  - date
  - `shifu_bid`
- collect:
  - event count
  - visitor count
- upsert the daily stats table

### Admin Metric Query

The operator course detail API should read from `analytics_course_daily_stats`
and return a rolling-window metric.

#### Recommended contract

- field name: `visit_count_30d`

#### Query rule

- sum `visitor_count` over the last 30 days is **not** mathematically correct
  for deduplicated 30-day users if the same user visited on multiple days

Because of that, there are two possible implementations:

##### Option A: approximate daily-sum model

- sum daily `visitor_count`
- cheapest to build
- overcounts repeat visitors across multiple days
- **not recommended** if the field label says `访问人数`

##### Option B: true rolling distinct model

- fetch a true distinct visitor metric for the 30-day window from Umami during
  sync
- store the pre-aggregated 30-day metric in a second table or snapshot table
- **recommended**

### Recommended storage for the displayed metric

Use a second snapshot table for rolling-window display values.

Suggested table:

- `analytics_course_window_stats`

Suggested columns:

- `id`
- `window_type`
  - initial value: `last_30_days`
- `shifu_bid`
- `visitor_count`
- `visit_count`
- `source`
- `window_start_date`
- `window_end_date`
- `synced_at`

Suggested uniqueness:

- unique index on `(window_type, shifu_bid, source)`

### Why a second window table is recommended

- it keeps the admin API simple
- it preserves exact 30-day distinct visitor semantics
- it avoids incorrect summing across daily uniques

### API Contract Change

When implemented, extend the operator course detail metrics payload:

- `visit_count_30d: int`

Suggested UI label:

- zh-CN: `近30天访问人数`
- en-US: `Visitors (30d)`

### Page Placement

When this metric is added later:

- place it before `学习人数`
- keep the rest of the metrics order unchanged

Recommended metric order:

- `近30天访问人数`
- `学习人数`
- `订单数`
- `流水总额`
- `追问数`
- `评分`

### Data Semantics

#### `近30天访问人数`

- distinct logged-in visitors who triggered `course_visit` in the last 30 days

#### `学习人数`

- distinct users with learning progress records

These two metrics intentionally measure different stages:

- access interest
- actual learning participation

### Failure Strategy

If Umami sync fails:

- admin API should continue working
- metric should fall back to last successful synced value
- UI may show the latest synced number without surfacing Umami directly

If no synced value exists:

- return `0` or an empty-state value based on product choice
- recommended first version: return `0`

### Security Rules

- Umami API tokens must live only in backend config
- frontend must never receive Umami management credentials
- operator detail endpoint must read only from business DB

### Observability

The sync job should log:

- sync window
- queried Umami site / environment
- number of course rows upserted
- number of failed rows
- final sync timestamp

Recommended alerts:

- sync job failed repeatedly
- sync result unexpectedly drops to zero for all courses

### Implementation Breakdown

#### Phase 1: frontend event

- add `course_visit` event emission on learner course entry
- include `shifu_bid`
- dedupe per session
- skip guests and preview mode

#### Phase 2: backend analytics storage

- create aggregation table(s)
- add migration
- add repository/service helpers for upsert and query

#### Phase 3: Umami sync job

- add Umami client wrapper in backend
- fetch event metrics for `course_visit`
- write daily stats and rolling-window stats

#### Phase 4: operator detail integration

- extend metrics DTO
- expose `visit_count_30d`
- render new card before learner count

### Open Product Choices

These should be confirmed before implementation starts:

- should the label explicitly say `近30天访问人数` instead of plain `访问人数`
  - recommended: yes
- should guests be excluded
  - recommended: yes
- should creator self-visits be excluded
  - recommended: no for the first version unless operators explicitly care
- should preview mode be excluded
  - recommended: yes

### Exact Recommendation To Follow

If there is no new product decision, implement exactly this:

- dedicated Umami event: `course_visit`
- required payload: `shifu_bid`
- only count logged-in users
- skip preview mode
- frontend dedupe once per session per course
- backend sync Umami into product DB
- display `近30天访问人数`
- source of admin read: business DB only

### Short Handoff Prompt

If a future task references this design, use this prompt:

> Implement the operator course visit metric according to
> `docs/product-specs/operator-course-visit-analytics.md`: add a dedicated Umami
> `course_visit` event with `shifu_bid`, sync exact rolling 30-day visitor data
> into backend-owned analytics tables, and expose `visit_count_30d` in the
> operator course detail metrics before learner count.

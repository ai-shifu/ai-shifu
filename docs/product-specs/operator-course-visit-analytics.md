---
title: Operator Course Visit Analytics
status: implemented
owner_surface: shared
last_reviewed: 2026-08-30
canonical: true
---

## Operator Course Visit Analytics

### Goal

Show operators how many distinct logged-in users opened a learner course page
during the trailing 30 days. The metric is recorded and queried entirely from
the product database. Umami remains a separate best-effort telemetry system
and is neither a producer nor a consumer of this business metric.

### Decision and Metric

The metric answers one decision-relevant question:

> How many registered users showed recent interest in this course by opening
> its learner page, whether or not they started a lesson?

The operator label is `近30天访问人数` in Chinese and `Visitors (30d)` in
English. Its exact definition is:

- count distinct eligible `user_bid` values per `shifu_bid`;
- include a user when their most recent eligible visit is within the trailing
  `30 * 24` hours at query time;
- calculate both write and query timestamps in UTC;
- exclude future timestamps from the count;
- start collecting when the first-party migration and write path are deployed.

This intentionally differs from `学习人数`, which requires a learning
progress record. A user can visit a course without starting a lesson.

### Eligible Population and Exclusions

Record a visit only when all of the following are true:

- the browser user store has finished initialization;
- the user has a real logged-in token rather than a temporary guest token;
- the route points to a real learner course page;
- the loaded course ID matches the current route course ID;
- the page is not creator preview mode;
- a non-deleted published course exists for the requested `shifu_bid`;
- the server-side user row is active and has registered, trial, or paid state.

The course owner is included when they open the published learner route. Guest
accounts, deleted users, draft-only courses, preview routes, stale course state,
and failed course loads are excluded.

### Trigger Contract

The frontend sends one best-effort request after the eligible course identity
and user state are ready:

```text
POST /api/learn/shifu/<shifu_bid>/visit
Content-Type: application/json

{}
```

The body is deliberately empty. The server obtains user identity from the
validated token and course identity from the encoded route parameter. The
request must not accept or send user IDs, course titles, URLs, referrers,
prompts, profile content, or other user-authored data.

An empty course title does not suppress the request. Course identity readiness,
not display copy, is the trigger boundary.

### Failure Independence

Recording is subordinate to the learner-visible course operation:

- the frontend calls the endpoint asynchronously and does not await it before
  rendering or navigating;
- the request suppresses error toasts;
- a rejected or failed request does not change course state, lesson loading,
  login state, or navigation;
- the frontend attempts at most once per user-course key during one route
  mount, even after failure, so high-frequency course renders cannot create a
  retry storm; a later real route mount may try again;
- the server returns a normal JSON envelope so the shared request client can
  parse the response consistently.

### Deduplication and Storage

Persist one row per `(shifu_bid, user_bid)` in `learn_course_visitors`:

| Column | Contract |
| --- | --- |
| `id` | Autoincrement primary key. |
| `shifu_bid` | Stable course business ID. |
| `user_bid` | Stable authenticated user business ID. |
| `first_visited_at` | UTC timestamp of the first recorded eligible visit. |
| `last_visited_at` | UTC timestamp of the most recent recorded eligible visit. |
| `created_at` | UTC row creation timestamp. |
| `updated_at` | UTC row update timestamp. |

The database enforces a unique constraint on `(shifu_bid, user_bid)` and an
index on `(shifu_bid, last_visited_at)`. Recording uses an atomic database
upsert: the first visit inserts a row and later visits advance
`last_visited_at` without changing `first_visited_at`.

Frontend in-flight or mount-level deduplication reduces redundant requests but
is not part of metric correctness. The database uniqueness contract is the
authoritative deduplication boundary and makes request retries safe.

This compact latest-visit model exactly supports the current rolling distinct
metric. It deliberately does not preserve per-visit history, visit counts, or
historical-as-of snapshots.

### Operator Read Contract

The operator course detail backend queries only `learn_course_visitors` and
returns:

```text
metrics.visit_count_30d: integer
```

At one captured UTC `now`, count rows for the requested course where:

```text
last_visited_at >= now - 30 days
last_visited_at <= now
```

The metric card appears immediately before `学习人数`. Its tooltip states that
the value counts logged-in, non-preview course-page visitors during the last
30 days and that collection starts when this feature is deployed.

### Initial Data and Backfill

There is no correct first-party source for visits that happened before this
feature was deployed. Do not backfill from Umami, page paths, learning progress,
orders, or another proxy because each would change the metric definition.

The initial value therefore represents a partial 30-day window and grows into
a full trailing window after 30 days. The tooltip communicates this limitation.

### Data Ownership, Privacy, and Retention

- The business database is the source of truth for the displayed metric.
- Umami availability, filtering, identity, retention, credentials, or delivery
  cannot change this metric or block course access.
- Stored values are stable machine IDs and timestamps only.
- No free-form text, profile data, contact details, URLs, queries, referrers,
  tokens, or raw errors are stored in the visit row or accepted by the API.
- Rows may be deleted with the corresponding user/course lifecycle when that
  lifecycle policy is defined; absence of per-visit history keeps storage
  bounded to one row per course-user pair.

### Downstream Consumer

The only initial consumer is the operator course detail metric card and its
backing API response. Billing, permissions, auditing, course access, and other
correctness-sensitive decisions must not depend on this count.

### Regression Requirements

Backend coverage must prove:

- only active registered/trial/paid users are recorded;
- guest, deleted-user, missing-course, and draft-only requests do not write;
- repeated writes preserve one row and advance only the latest visit time;
- distinct users and courses stay isolated;
- the trailing 30-day boundary is UTC-based and excludes future timestamps;
- operator detail reads the business table and returns zero when no row exists;
- the migration has the uniqueness and query indexes and keeps a single
  Alembic head.

Frontend coverage must prove:

- initialization, login, preview, loaded-course identity, and empty-title
  trigger rules;
- rerenders and in-flight requests do not create duplicate calls;
- a failed request cannot change the visible course result or retry repeatedly
  during the same mount;
- the request body and options match the stable contract;
- the operator metric renders before learner count with localized label,
  formatted zero/large values, and the explanatory tooltip.

### Non-Goals

- Do not read Umami APIs or tables from product code.
- Do not sync Umami aggregates into the business database.
- Do not restore dynamic `course_visit_<shifu_bid>` events or compatibility
  double-writes.
- Do not count anonymous browsers or claim to measure natural persons across
  devices.
- Do not infer visits from learning progress, orders, or generic pageviews.
- Do not provide historical visit charts or visit frequency in this version.

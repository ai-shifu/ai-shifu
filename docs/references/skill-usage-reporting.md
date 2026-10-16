---
title: Skill Usage Reporting
status: implemented
owner_surface: backend
last_reviewed: 2026-10-16
canonical: true
---

# Skill usage reporting

This is the downstream consumer for the
[Skill usage analytics contract](../product-specs/skill-usage-analytics.md).
Run the query against a read-only Umami PostgreSQL replica or an authorized
read-only export database. It returns aggregate operation counts, account
activity, and observed cohorts. It does not return account identifiers.

## Identity and supported schema

The backend sends the authenticated AI-Shifu account's `user_id` as Umami's
`payload.id`, matching Cook Web's `umami.identify(user_id)`. Umami documents
[Distinct IDs](https://docs.umami.is/docs/distinct-ids) as available since
2.18.0. Check the deployed collector version and an actual stored event before
enabling production reporting; acceptance of an HTTP request alone does not
prove that its identity was stored.

The query targets the
[Umami 2.19.0 PostgreSQL schema](https://github.com/umami-software/umami/blob/v2.19.0/db/postgresql/schema.prisma):

| Meaning | PostgreSQL mapping |
| --- | --- |
| Account identity | `session.distinct_id`, nullable `varchar(50)` |
| Event and session link | `website_event.event_id`, `session_id`, `website_id` |
| Event time | `website_event.created_at`, `timestamp with time zone` |
| Event kind and source | `website_event.event_name`, `event_type`, `hostname` |
| Flat event properties | `event_data.website_event_id`, `data_key`, `string_value`, `number_value` |

Event properties are separate rows, not a JSON column. Identity must join
through `session` for PostgreSQL. The schema's timezone-aware timestamps make
`created_at AT TIME ZONE 'Asia/Shanghai'` a local wall-clock timestamp, whose
date is the reporting day. Do not apply this expression unchanged to a
timezone-naive export. Inspect and normalize that export first. Current
[Umami PostgreSQL source](https://github.com/umami-software/umami/blob/master/prisma/schema.prisma)
retains these mappings; this is not a guarantee for every future release or
for ClickHouse.

Umami visitors, visits, and sessions are not the account metric. Deduplicate
the nonempty `distinct_id` across all matching sessions and sources. Account
identity is used only inside the aggregate query. Anonymous browser traffic,
events without an identity, and legacy external-client journey events are
excluded. A missing identity must not be replaced with a session ID, IP
address, token, or Agent name.

## Inputs and metric boundaries

Set these `psql` variables before running the SQL below:

| Variable | Value |
| --- | --- |
| `website_id` | The configured Umami website UUID shared by Cook Web and backend events |
| `rollout_utc` | UTC timestamp of the beginning of verified, continuous identity and event coverage |
| `complete_before_utc` | Exclusive UTC cutoff at a completed Asia/Shanghai day boundary, including an appropriate delivery/replication lag allowance |
| `report_start_day` | First requested reporting date, in `YYYY-MM-DD` Asia/Shanghai calendar form |
| `web_hosts` | PostgreSQL text array of the exact current Cook Web hostnames for this website, for example `'{host-one.invalid,host-two.invalid}'`; populate from deployment configuration |

Use a credential manager or an existing protected connection configuration for
the replica connection. Do not put a database password in a report, repository,
or shared command transcript. The query is a single read-only statement and
needs no new AI-Shifu API, dashboard, or persisted account-level report table.

For example, `2026-10-17T16:00:00Z` is the exclusive start of October 18 in
Asia/Shanghai. An in-progress day is not complete. The report families are empty
if the cutoff is not a Shanghai midnight or precedes coverage. It excludes a
partial first coverage day from report and cohort output; those observations
still establish an account's first observed Skill day.

The operation report counts every eligible authenticated request, split by
`operation`, `outcome`, and `caller_agent`. Fan-out requests, retries, and
repeated commands remain separate requests. `accounts` deduplicates within
that one report row; summing those columns across operations or Agents is not
a unique-account total. `unknown` is an ordinary separate Agent row.

Account activity requires at least one `skill_api_request_v1` with
`outcome=success` on that day. Failures do not create active days or cohort
entries. Combined activity is the union of successful Skill account-days and
identified Cook Web pageview/custom-event account-days (`event_type` 1 or 2)
on the explicit host allowlist. It does not include arbitrary backend events,
performance telemetry, or every HTTP request. The host allowlist must not
contain the backend's synthetic `server.ai-shifu` hostname.

DAU counts distinct active accounts on a complete day; rolling 7/30 counts
distinct accounts in the trailing 7/30 calendar days including that day.
Rolling values are `null` until the full window is covered. Agent account-day
rows can overlap when one account uses multiple Agents; the `all` row
deduplicates across them.

Cohorts begin on an account's **first observed successful Skill day** over the
entire available coverage period, not its first event in the selected report
range, installation date, or necessarily its first-ever Skill use. D1 and D7
mean activity on the exact first-day-plus-1 or plus-7 calendar date. They are
reported separately for Skill return and any combined return. The cohort
Agent is the first successful request's Agent, with event ID breaking equal
timestamps. The `all` row counts each account once. An immature cohort's
return counts, denominators, and rates remain `null`; do not turn these into
zeros or include them in an aggregate retention denominator.

## Aggregate SQL

Pass the variables with `psql -v name=value` or set them with `\set` in a
private session. Do not substitute an application user ID into any variable.
The output has three report families; the JSON arrays contain only dates,
allowlisted dimensions, counts, and rates. An empty family is `[]`.

```sql
WITH parameters AS (
  SELECT :'website_id'::uuid AS website_id,
         :'rollout_utc'::timestamptz AS rollout_utc,
         :'complete_before_utc'::timestamptz AS complete_before_utc,
         :'report_start_day'::date AS report_start_day,
         :'web_hosts'::text[] AS web_hosts
), bounds AS (
  SELECT p.*,
         (complete_before_utc AT TIME ZONE 'Asia/Shanghai')::date AS end_day,
         (rollout_utc AT TIME ZONE 'Asia/Shanghai')::date
           + CASE WHEN (rollout_utc AT TIME ZONE 'Asia/Shanghai')::time
                         = time '00:00:00' THEN 0 ELSE 1 END
           AS first_complete_day
  FROM parameters p
  WHERE complete_before_utc > rollout_utc
    AND (complete_before_utc AT TIME ZONE 'Asia/Shanghai')::time
          = time '00:00:00'
    AND NOT ('server.ai-shifu' = ANY(web_hosts))
), observed AS (
  SELECT e.event_id, e.created_at, s.distinct_id,
         (e.created_at AT TIME ZONE 'Asia/Shanghai')::date AS day,
         e.event_name, e.event_type, e.hostname,
         properties.operation, properties.outcome,
         CASE WHEN properties.caller_agent IN
           ('codex', 'claude_code', 'cursor', 'hermes', 'openclaw', 'workbuddy',
            'qoderwork', 'grok_bot', 'unknown')
           THEN properties.caller_agent ELSE 'unknown' END AS caller_agent
  FROM bounds b
  JOIN website_event e ON e.website_id = b.website_id
  JOIN session s ON s.website_id = e.website_id
                AND s.session_id = e.session_id
  LEFT JOIN LATERAL (
    SELECT max(string_value) FILTER (WHERE data_key = 'operation') AS operation,
           max(string_value) FILTER (WHERE data_key = 'outcome') AS outcome,
           max(string_value) FILTER (WHERE data_key = 'caller_agent') AS caller_agent
    FROM event_data d
    WHERE d.website_id = e.website_id
      AND d.website_event_id = e.event_id
      AND e.event_name = 'skill_api_request_v1'
  ) properties ON true
  WHERE e.created_at >= b.rollout_utc
    AND e.created_at < b.complete_before_utc
    AND nullif(s.distinct_id, '') IS NOT NULL
    AND ((e.event_name = 'skill_api_request_v1' AND e.event_type = 2)
      OR (e.hostname = ANY(b.web_hosts) AND e.event_type IN (1, 2)))
), skill AS (
  SELECT * FROM observed
  WHERE event_name = 'skill_api_request_v1'
    AND event_type = 2
    AND outcome IN ('success', 'failure')
    AND operation IN (
      'course_list', 'course_create', 'course_get', 'course_update',
      'course_archive', 'course_unarchive', 'course_publish', 'course_export',
      'outline_list', 'outline_get', 'outline_create', 'outline_update',
      'outline_delete', 'outline_reorder', 'content_get', 'content_save',
      'content_history_list', 'content_history_get', 'draft_meta_get',
      'asset_upload', 'asset_url_upload', 'analytics_query',
      'analytics_credit_detail')
), skill_days AS (
  SELECT DISTINCT distinct_id, day, caller_agent
  FROM skill WHERE outcome = 'success'
), combined_days AS (
  SELECT distinct_id, day FROM skill_days
  UNION
  SELECT distinct_id, day FROM observed o CROSS JOIN bounds b
  WHERE o.hostname = ANY(b.web_hosts)
    AND o.event_type IN (1, 2)
    AND o.event_name IS DISTINCT FROM 'skill_api_request_v1'
), days AS (
  SELECT generate_series(
    greatest(report_start_day, first_complete_day)::timestamp,
    (end_day - 1)::timestamp, interval '1 day')::date AS day
  FROM bounds
), operations AS (
  SELECT s.day, s.operation, s.outcome, s.caller_agent,
         count(*) AS requests, count(DISTINCT s.distinct_id) AS accounts
  FROM skill s CROSS JOIN bounds b
  WHERE s.day >= greatest(b.report_start_day, b.first_complete_day)
  GROUP BY s.day, s.operation, s.outcome, s.caller_agent
), agent_dimensions AS (
  SELECT 'all'::text AS caller_agent
  UNION SELECT caller_agent FROM skill_days
), activity AS (
  SELECT d.day, a.caller_agent,
         counts.skill_dau,
         CASE WHEN d.day - 6 >= b.first_complete_day
              THEN counts.skill_rolling_7 END AS skill_rolling_7,
         CASE WHEN d.day - 29 >= b.first_complete_day
              THEN counts.skill_rolling_30 END AS skill_rolling_30,
         CASE WHEN a.caller_agent = 'all' THEN combined.combined_dau END
           AS combined_dau,
         CASE WHEN a.caller_agent = 'all'
                   AND d.day - 6 >= b.first_complete_day
              THEN combined.combined_rolling_7 END AS combined_rolling_7,
         CASE WHEN a.caller_agent = 'all'
                   AND d.day - 29 >= b.first_complete_day
              THEN combined.combined_rolling_30 END AS combined_rolling_30
  FROM days d CROSS JOIN agent_dimensions a CROSS JOIN bounds b
  CROSS JOIN LATERAL (
    SELECT count(DISTINCT distinct_id) FILTER (WHERE day = d.day) AS skill_dau,
           count(DISTINCT distinct_id) FILTER (WHERE day >= d.day - 6)
             AS skill_rolling_7,
           count(DISTINCT distinct_id) AS skill_rolling_30
    FROM skill_days
    WHERE day BETWEEN d.day - 29 AND d.day
      AND (a.caller_agent = 'all' OR caller_agent = a.caller_agent)
  ) counts
  CROSS JOIN LATERAL (
    SELECT count(DISTINCT distinct_id) FILTER (WHERE day = d.day) AS combined_dau,
           count(DISTINCT distinct_id) FILTER (WHERE day >= d.day - 6)
             AS combined_rolling_7,
           count(DISTINCT distinct_id) AS combined_rolling_30
    FROM combined_days WHERE day BETWEEN d.day - 29 AND d.day
  ) combined
), first_skill AS (
  SELECT DISTINCT ON (distinct_id)
         distinct_id, day AS cohort_day, caller_agent AS first_agent
  FROM skill WHERE outcome = 'success'
  ORDER BY distinct_id, created_at, event_id
), returns AS (
  SELECT f.*, b.end_day,
         EXISTS (SELECT 1 FROM skill_days x WHERE x.distinct_id = f.distinct_id
                 AND x.day = f.cohort_day + 1) AS skill_d1,
         EXISTS (SELECT 1 FROM skill_days x WHERE x.distinct_id = f.distinct_id
                 AND x.day = f.cohort_day + 7) AS skill_d7,
         EXISTS (SELECT 1 FROM combined_days x WHERE x.distinct_id = f.distinct_id
                 AND x.day = f.cohort_day + 1) AS any_d1,
         EXISTS (SELECT 1 FROM combined_days x WHERE x.distinct_id = f.distinct_id
                 AND x.day = f.cohort_day + 7) AS any_d7
  FROM first_skill f CROSS JOIN bounds b
  WHERE f.cohort_day >= greatest(b.report_start_day, b.first_complete_day)
), cohorts AS (
  SELECT cohort_day, coalesce(first_agent, 'all') AS caller_agent,
         count(*) AS observed_new_skill_accounts,
         CASE WHEN cohort_day + 1 < end_day THEN count(*) END AS d1_eligible_accounts,
         CASE WHEN cohort_day + 7 < end_day THEN count(*) END AS d7_eligible_accounts,
         CASE WHEN cohort_day + 1 < end_day
              THEN count(*) FILTER (WHERE skill_d1) END AS skill_d1_accounts,
         CASE WHEN cohort_day + 7 < end_day
              THEN count(*) FILTER (WHERE skill_d7) END AS skill_d7_accounts,
         CASE WHEN cohort_day + 1 < end_day
              THEN count(*) FILTER (WHERE any_d1) END AS any_d1_accounts,
         CASE WHEN cohort_day + 7 < end_day
              THEN count(*) FILTER (WHERE any_d7) END AS any_d7_accounts,
         CASE WHEN cohort_day + 1 < end_day
              THEN avg(skill_d1::int) END AS skill_d1_rate,
         CASE WHEN cohort_day + 7 < end_day
              THEN avg(skill_d7::int) END AS skill_d7_rate,
         CASE WHEN cohort_day + 1 < end_day
              THEN avg(any_d1::int) END AS any_d1_rate,
         CASE WHEN cohort_day + 7 < end_day
              THEN avg(any_d7::int) END AS any_d7_rate
  FROM returns
  GROUP BY GROUPING SETS
    ((cohort_day, end_day), (cohort_day, end_day, first_agent))
)
SELECT 'operations' AS report,
       coalesce(jsonb_agg(to_jsonb(o) ORDER BY day, operation, outcome, caller_agent),
                '[]'::jsonb) AS rows
FROM operations o
UNION ALL
SELECT 'account_activity',
       coalesce(jsonb_agg(to_jsonb(a) ORDER BY day, caller_agent), '[]'::jsonb)
FROM activity a
UNION ALL
SELECT 'observed_cohorts',
       coalesce(jsonb_agg(to_jsonb(c) ORDER BY cohort_day, caller_agent), '[]'::jsonb)
FROM cohorts c;
```

## Readback and limitations

### Local SQL regression check

The portable fixture runs this document's SQL against an in-memory PostgreSQL
database through PGlite. It covers account deduplication, Agent overlap,
Shanghai day boundaries, rolling windows, retention maturity, invalid event
kinds, and exclusion of raw account identifiers from output. It uses synthetic
data only and does not connect to a collector or production database.

From the repository root, install the test-only dependency in a temporary
directory and pass its module path to the fixture:

```bash
skill_sql_test_dir=$(mktemp -d)
npm install --prefix "$skill_sql_test_dir" --no-save @electric-sql/pglite@0.5.10
node scripts/test_skill_usage_reporting.mjs "$skill_sql_test_dir/node_modules/@electric-sql/pglite/dist/index.js"
```

The dependency is not part of the application. If it is already resolvable
from the repository's Node environment, the module-path argument is optional.

### Production readback

Before relying on a report, verify one controlled successful Skill request,
one business failure delivered as HTTP 200, one export response, and one
identified Cook Web event for the same test account. Confirm that successes
join to the same `distinct_id` while failure-only days do not become active;
then run the aggregate query without exporting that account identifier.
Exercise two Agents on the same account-day to check that the `all` row
deduplicates while Agent rows remain separate. Check a Shanghai midnight and
an immature D7 cohort. Use only controlled test accounts for readback.

Maintain a coverage note with collector version, website, verified deployment
cutover, delivery/replication lag, outages, data-retention start, and host
allowlist changes. A reset, deletion, expired retention, blocked browser
tracker, opt-out, dropped queue item, unavailable collector, or missing
identity can reduce observed counts. After a coverage gap, label or exclude
affected periods; moving `rollout_utc` forward also restarts observed cohorts.
Do not call these counts exact users, first-ever adoption, or complete
retention. Client headers and environment hints remain forgeable analytics
signals and must not be used for enforcement or auditing.

Only the final aggregate output is intended for sharing. Keep the underlying
account-level rows, database connection, and any diagnostic identity lookup
inside the authorized analytics boundary. Apply the deployment's account-data
retention and deletion procedure to Umami identity-linked records as well as
the primary application; this query does not anonymize the source data.

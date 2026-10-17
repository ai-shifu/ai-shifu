---
title: Skill Usage Reporting
status: implemented
owner_surface: backend
last_reviewed: 2026-10-17
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

The v2 collector contract targets official **Umami 3.4.0** and the query uses
its [PostgreSQL schema](https://github.com/umami-software/umami/blob/v3.4.0/prisma/schema.prisma).
On 2026-10-17 the deployed image and startup log still identify **3.1.0**.
That version does not include UA in the session key when an ID is supplied,
so a single account switching Agents can retain the first session's OS.
It does not satisfy the v2 client-classification acceptance criteria. This
change does not upgrade Umami; use an authorized compatible 3.4 test site for
storage and UI acceptance before enabling v2 production reporting.

The common reporting columns are:

| Meaning | PostgreSQL mapping |
| --- | --- |
| Account identity | `session.distinct_id`, nullable `varchar(50)` |
| Event and session link | `website_event.event_id`, `session_id`, `website_id` |
| Event time | `website_event.created_at`, `timestamp with time zone` |
| Event kind and source | `website_event.event_name`, `event_type`, `hostname`, `tag` |
| Native identity association | `session_link.session_id`, `distinct_id` (acceptance checks only) |
| Flat event properties | `event_data.website_event_id`, `data_key`, `string_value`, `number_value` |

Event properties are separate rows, not a JSON column. Identity must join
through the one-to-one event-to-session key for PostgreSQL. Do not join
`session_link` into request or account aggregation: multiple identity links
can multiply requests and misattribute history. Read it separately to verify
native profile association. Missing or empty `session.distinct_id` is excluded
from account metrics, with no fallback or inferred historical identity.
The schema's timezone-aware timestamps make
`created_at AT TIME ZONE 'Asia/Shanghai'` a local wall-clock timestamp, whose
date is the reporting day. Do not apply this expression unchanged to a
timezone-naive export. Inspect and normalize that export first. These mappings
are not a guarantee for future releases or ClickHouse.

Umami visitors, visits, and sessions are not the account metric. Deduplicate
the nonempty `distinct_id` across all matching sessions and sources. Account
identity is used only inside the aggregate query. Anonymous browser traffic
and legacy external-client journey events are
excluded from account metrics. A valid request record with a missing stored
identity still contributes to requests and sessions. A missing identity must
not be replaced with a session ID, IP
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
The separate `request_totals` family deduplicates by Agent and an `all` row;
`requests`, `successful_requests`, `accounts`, `sessions`, and `v2_pageviews`
are distinct measures. Each v2 row is one HTTP request pageview, not one CLI
command or human visit. Browser/OS native cards classify synthetic clients;
their counts are not distinct account counts. The backend-generated UA includes
the installed CLI version, so CLI upgrades may create new sessions for the same
account. Continue deduplicating accounts by distinct ID, not by UA or session.
The shared website's total PV
increases even though Web tracking and production behavior remain unchanged.

Request compatibility requires `hostname='server.ai-shifu'` and
`skill_id='ai-shifu-course-creator'` for both versions, plus either
historical `event_type=2` with `event_name='skill_api_request_v1'`, or v2
`event_type=1` with a null event name and `tag='skill_api_request_v2'`.
V2 requires exactly the seven allowlisted typed properties and the current
operation/method pair; historical v1 does not require a method property.
The CLI follows the pinned
[detect_agent.md v0.1.5 catalog](https://github.com/ai-shifu/detect_agent/blob/9eee13e/detect_agent.md)
and owns detection and the bounded display name. It sends the ID and display
name through `X-AI-Shifu-Caller-Agent` and `X-AI-Shifu-Caller-Agent-Name`, alongside
`X-AI-Shifu-Skill` and `X-AI-Shifu-Skill-Version`. The backend validates the pair
and generates the versioned UA from the bundled CLI release; it never forwards
the original client UA. The query accepts all 35 canonical IDs plus `unknown`,
and preserves the nine historical IDs exactly in both v1 and v2 records.
In particular, historical `qoderwork` means the former QoderWork / Qwen Work
family and is not renamed to the new `qwenwork` brand. Historical `hermes`,
`claude_code`, and `grok_bot` also remain separate from their canonical IDs.
Agent labels can therefore split across CLI versions; do not add account counts
across those labels. The `all` row and combined Web/CLI union still deduplicate
by the same account ID. Unrecognized historical v1 Agent values fall back to
`unknown`; unlisted v2 Agent values are rejected. Do not infer cross-version
duplicate requests from timestamps: retries are independent requests. The producer prevents dual writes.
Old creation/publish stage events are not added to these request records.

Account activity requires at least one valid v1 or v2 request with
`outcome=success` and a stored account ID on that day. Failures do not create
active days or cohort entries. Combined activity is the union of successful Skill account-days and
identified Cook Web pageview/custom-event account-days (`event_type` 1 or 2)
on the explicit host allowlist. It does not include arbitrary backend events,
performance telemetry, or every HTTP request. The host allowlist must not
contain the backend's synthetic `server.ai-shifu` hostname. Web-only rows
also exclude both request markers and all old creation/publish stage markers,
even if historical data has an incorrect Web hostname. Cross-channel account
counts use a union of IDs, never the sum of Web and CLI counts. Identity
association does not promise a shared session or cross-session native funnel.

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
The output has four report families; the JSON arrays contain only dates,
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
), operation_methods(operation, method) AS (
  VALUES ('course_list', 'GET'), ('course_create', 'PUT'),
    ('course_get', 'GET'), ('course_update', 'POST'),
    ('course_archive', 'POST'), ('course_unarchive', 'POST'),
    ('course_publish', 'POST'), ('course_export', 'GET'),
    ('outline_list', 'GET'), ('outline_get', 'GET'),
    ('outline_create', 'PUT'), ('outline_update', 'POST'),
    ('outline_delete', 'DELETE'), ('outline_reorder', 'PATCH'),
    ('content_get', 'GET'), ('content_save', 'POST'),
    ('content_history_list', 'GET'), ('content_history_get', 'GET'),
    ('draft_meta_get', 'GET'), ('asset_upload', 'POST'),
    ('asset_url_upload', 'POST'), ('analytics_query', 'POST'),
    ('analytics_credit_detail', 'POST')
), observed AS (
  SELECT e.event_id, e.session_id, e.created_at,
         nullif(s.distinct_id, '') AS distinct_id,
         (e.created_at AT TIME ZONE 'Asia/Shanghai')::date AS day,
         e.event_name, e.event_type, e.hostname, e.tag,
         properties.skill_id, properties.operation, properties.outcome, properties.method,
         properties.valid_v2_properties,
         properties.caller_agent AS raw_caller_agent,
         CASE WHEN properties.caller_agent IN
           ('antigravity', 'augment-cli', 'claude-code', 'claude_code',
            'cline', 'codex', 'cowork', 'crush',
            'cue', 'cursor', 'cursor-cli', 'devin',
            'doubao-work', 'gemini-cli', 'github-copilot', 'goose',
            'grok-bot', 'grok-build', 'grok_bot', 'hermes',
            'hermes-agent', 'hi', 'junie', 'kilo-code',
            'kimi', 'kiro', 'manus', 'muse',
            'openclaw', 'opencode', 'pi', 'qoderwork',
            'qwenwork', 'replit', 'sandbase-harness', 'trae',
            'unknown', 'vtcode', 'workbuddy', 'zed')
           THEN properties.caller_agent ELSE 'unknown' END AS caller_agent
  FROM bounds b
  JOIN website_event e ON e.website_id = b.website_id
  JOIN session s ON s.website_id = e.website_id
                AND s.session_id = e.session_id
  LEFT JOIN LATERAL (
    SELECT max(string_value) FILTER (WHERE data_key = 'skill_id') AS skill_id,
           max(string_value) FILTER (WHERE data_key = 'operation') AS operation,
           max(string_value) FILTER (WHERE data_key = 'outcome') AS outcome,
           max(string_value) FILTER (WHERE data_key = 'method') AS method,
           max(string_value) FILTER (WHERE data_key = 'caller_agent') AS caller_agent,
           count(*) = 7 AND count(DISTINCT data_key) = 7
             AND bool_and(coalesce(CASE
               WHEN data_key = 'skill_id' THEN
                 string_value = 'ai-shifu-course-creator' AND number_value IS NULL
               WHEN data_key = 'skill_version_major' THEN
                 string_value ~ '^(v[0-9]|unknown)$' AND number_value IS NULL
               WHEN data_key IN ('operation', 'outcome', 'method', 'caller_agent')
                 THEN string_value IS NOT NULL AND number_value IS NULL
               WHEN data_key = 'duration_ms' THEN
                 string_value IS NULL AND number_value >= 0
                 AND number_value < 'Infinity'::numeric
                 AND number_value = trunc(number_value)
               ELSE false END, false)) AS valid_v2_properties
    FROM event_data d
    WHERE d.website_id = e.website_id
      AND d.website_event_id = e.event_id
      AND (e.event_name = 'skill_api_request_v1' OR e.tag = 'skill_api_request_v2')
  ) properties ON true
  WHERE e.created_at >= b.rollout_utc
    AND e.created_at < b.complete_before_utc
    AND ((e.hostname = 'server.ai-shifu' AND
          ((e.event_name = 'skill_api_request_v1' AND e.event_type = 2)
           OR (e.event_name IS NULL AND e.event_type = 1
               AND e.tag = 'skill_api_request_v2')))
      OR (e.hostname = ANY(b.web_hosts) AND e.event_type IN (1, 2)))
), skill AS (
  SELECT o.* FROM observed o
  JOIN operation_methods m ON m.operation = o.operation
  WHERE hostname = 'server.ai-shifu'
    AND skill_id = 'ai-shifu-course-creator'
    AND outcome IN ('success', 'failure')
    AND ((event_name = 'skill_api_request_v1' AND event_type = 2)
      OR (event_name IS NULL AND event_type = 1 AND tag = 'skill_api_request_v2'
          AND valid_v2_properties AND o.method = m.method
          AND raw_caller_agent = caller_agent))
), skill_days AS (
  SELECT DISTINCT distinct_id, day, caller_agent
  FROM skill WHERE outcome = 'success' AND distinct_id IS NOT NULL
), web_days AS (
  SELECT DISTINCT distinct_id, day FROM observed o CROSS JOIN bounds b
  WHERE o.hostname = ANY(b.web_hosts)
    AND o.event_type IN (1, 2) AND o.distinct_id IS NOT NULL
    AND o.tag IS DISTINCT FROM 'skill_api_request_v2'
    AND (o.event_name IS NULL OR o.event_name NOT IN
      ('skill_api_request_v1', 'skill_api_request_v2',
       'external_course_creation_started', 'external_course_creation_completed',
       'external_course_creation_failed', 'external_course_publish_started',
       'external_course_publish_completed', 'external_course_publish_failed'))
), combined_days AS (
  SELECT distinct_id, day FROM skill_days
  UNION
  SELECT distinct_id, day FROM web_days
), days AS (
  SELECT generate_series(
    greatest(report_start_day, first_complete_day)::timestamp,
    (end_day - 1)::timestamp, interval '1 day')::date AS day
  FROM bounds
), operations AS (
  SELECT s.day, s.operation, s.outcome, s.caller_agent,
         count(*) AS requests,
         count(*) FILTER (WHERE s.outcome = 'success') AS successful_requests,
         count(DISTINCT s.distinct_id) AS accounts,
         count(DISTINCT s.session_id) AS sessions,
         count(*) FILTER (WHERE s.event_type = 1) AS v2_pageviews
  FROM skill s CROSS JOIN bounds b
  WHERE s.day >= greatest(b.report_start_day, b.first_complete_day)
  GROUP BY s.day, s.operation, s.outcome, s.caller_agent
), request_totals AS (
  SELECT s.day, coalesce(s.caller_agent, 'all') AS caller_agent,
         count(*) AS requests,
         count(*) FILTER (WHERE s.outcome = 'success') AS successful_requests,
         count(DISTINCT s.distinct_id) AS accounts,
         count(DISTINCT s.session_id) AS sessions,
         count(*) FILTER (WHERE s.event_type = 1) AS v2_pageviews
  FROM skill s CROSS JOIN bounds b
  WHERE s.day >= greatest(b.report_start_day, b.first_complete_day)
  GROUP BY GROUPING SETS ((s.day), (s.day, s.caller_agent))
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
  FROM skill WHERE outcome = 'success' AND distinct_id IS NOT NULL
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
SELECT 'request_totals',
       coalesce(jsonb_agg(to_jsonb(t) ORDER BY day, caller_agent), '[]'::jsonb)
FROM request_totals t
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
kinds, v1/v2 coexistence, exact v2 properties/methods, malformed contract
markers, failure-only requests, repeated sessions, Web-only filtering, and
exclusion of raw account identifiers from output. It uses synthetic
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

Actual 3.4 storage and UI readback is pending; local fixtures and HTTP 200
responses do not establish acceptance. Bot filtering may return HTTP 200 with
`{"beep":"boop"}` without storing anything. Before relying on a report, verify
one controlled successful Skill request,
one business failure delivered as HTTP 200, one export response, and one
identified Cook Web event for the same test account. Confirm that successes
join to the same `distinct_id` while failure-only days do not become active;
then run the aggregate query without exporting that account identifier.
Exercise two Agents on the same account-day to check that native Browser is
`AI-Shifu CLI`, each OS matches its Agent, and switching Agents does not retain
the first OS. Verify pageview kind, null event name, fixed tag, sanitized route,
shared distinct ID, and the native `session_link` association separately.
Confirm the aggregate `all` row deduplicates while Agent rows remain separate,
and that the same account's Web activity does not add a second account. Check a Shanghai midnight and
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

---
title: Skill Usage Analytics
status: implemented
owner_surface: frontend-backend
last_reviewed: 2026-10-16
canonical: true
---

# Skill usage analytics

## Decision and measurement

Measure adoption, successful API activity, operation mix, failures, and return
usage of `ai-shifu-course-creator`, segmented by the invoking Agent. Use Umami
and the existing authenticated account identity shared with Cook Web. These
are observed product metrics, never billing, permissions, or audit records.
This does not measure Skill discovery, installation, prompt reading, local
builds, complete CLI commands, or model usage.

## Request contract

The Skill CLI adds these headers to authenticated business requests:

| Header | Accepted value |
| --- | --- |
| `X-AI-Shifu-Skill` | `ai-shifu-course-creator` |
| `X-AI-Shifu-Skill-Version` | Bounded ASCII semantic version; only its major bucket reaches Umami |
| `X-AI-Shifu-Caller-Agent` | `codex`, `claude_code`, `cursor`, `hermes`, `openclaw`, `workbuddy`, `qoderwork`, `grok_bot`, `unknown` |

These are outbound HTTP metadata generated inside the CLI, not CLI flags or
identity supplied by the invoking Agent. The detector checks only the
existence of a fixed allowlist of process environment names, once before
loading dotenv or profile configuration. Values, process lists, configuration
files, hooks, and Agent APIs are not used for Agent detection. The Skill's
version comes from its own package metadata. `SHIFU_DISABLE_ANALYTICS=1`, set
in the process or Skill dotenv configuration, omits all three headers.

| Agent result | Presence keys |
| --- | --- |
| `codex` | `CODEX_THREAD_ID`, `CODEX_SESSION_ID` |
| `claude_code` | `CLAUDECODE`, `CLAUDE_CODE_CHILD_SESSION` |
| `cursor` | `CURSOR_AGENT` |
| `hermes` | `HERMES_AGENT`, `HERMES_SESSION_ID` |
| `openclaw` | `OPENCLAW_SHELL` |
| `workbuddy` | `WORKBUDDY_CONFIG_DIR` |
| `qoderwork` | `QODERWORK_IS_CN`, `QODERWORK_SOURCE_CHAT_ID` |
| `grok_bot` | `SAND_AGENT` |

Multiple keys for one Agent collapse to one match. `SAND_AGENT` suppresses
the shared `CURSOR_AGENT` signal because Grok Bot's local executor injects
both. Other multiple-Agent matches and no matches produce `unknown`.
`qoderwork` identifies the QoderWork / Qwen Work product family, not a region
or brand inferred from a variable value. Doubao Work, Muse, Manus, and Cue have
no confirmed Skill subprocess marker in this implementation.

These markers are compatibility heuristics, not a trusted identity protocol.
Inherited or manually set markers can misattribute a caller; nested Agents
may be ambiguous. Shells can clear variables. Grok Bot's local Bash/Zsh
propagation was inspected in 0.71.2, WorkBuddy in 5.8.2, and Qwen Work in 1.2.5;
this is static package evidence, not a promise about their cloud execution or
future versions. Report `unknown` separately rather than guessing. No model
or Agent version is reported.

## Event contract: `skill_api_request_v1`

- Business question: which accounts use the Skill, from which Agent, for
  which operations, with what failure rate, and do they return?
- Actor and surface: an authenticated account making an allowlisted backend
  business request with all three valid Skill headers.
- Trigger: response preparation completes, once per HTTP request. HTTP 200
  with a nonzero business `code` is a failure. A successful file export means
  the download response was prepared, not that its stream was consumed or the
  file was saved by the client.
- Population: account-authenticated course, outline, content, revision,
  upload, export, and creator-analytics requests used by the Skill. Exact
  endpoint names and HTTP methods are allowlisted in the backend. Exclude
  login, device polling, verification, configuration, update checks, local
  commands, unauthenticated requests, unmatched methods/endpoints, and
  missing or malformed Skill metadata.
- Count unit: one server-observed API request, not one CLI command. Import,
  pull, status, and other commands may make several requests; their API
  operations remain separate and cannot be relabeled as complete commands.
- Deduplication: one after-request event per eligible response. Separate
  retries remain separate requests. Delivery is best effort, with no retry
  or replay guarantee. User metrics deduplicate accounts, not requests.
- Correlation: top-level Umami `id` is the authenticated `request.user.user_id`,
  identical to the string passed to browser `umami.identify`. Never derive
  identity from telemetry headers, an unverified JWT, or an independently
  re-read credential. Anonymous Umami visitors and sessions are not accounts.
- Consumers: the aggregate reporting queries in
  [Skill usage reporting](../references/skill-usage-reporting.md).
- Compatibility: a new event series. Older clients without these headers
  keep their behavior and any existing legacy attribution events. Valid new
  Skill metadata suppresses the older external course journey events for the
  same request; do not sum the old stage series with this request series.
  Authorization events and old clients remain unaffected. No backfill.

| Payload field | Type / allowed values | Privacy class | Purpose |
| --- | --- | --- | --- |
| `skill_id` | Fixed `ai-shifu-course-creator` | Non-personal | Skill selection |
| `skill_version_major` | `v0` through `v9`, otherwise `unknown` | Non-personal | Release-family comparison |
| `caller_agent` | Enum above | Non-personal | Agent adoption |
| `operation` | Fixed backend endpoint operation enum | Non-personal | Capability mix |
| `outcome` | `success`, `failure` | Non-personal | Success and failure trends |
| `duration_ms` | Finite, nonnegative number | Non-personal | Backend response preparation time |

The transport uses fixed synthetic hostname `server.ai-shifu` and path
`/backend/skill` rather than request URLs. Account identity is pseudonymous
and belongs only in Umami's top-level distinct-ID field, never duplicated in
event data. Do not forward the client's IP address, User-Agent, headers,
cookies, referrer, request body, queries, course IDs, titles, prompts, model
output, raw failures, environment values, or session/device identifiers.

## Isolation and privacy operations

Reuse the bounded backend sender: two workers, at most 32 queued/in-flight
deliveries, short network timeouts, and exception isolation. Analytics failure,
missing settings, or saturation must preserve responses and transactions.
Streamed/download responses are not consumed to determine an outcome.

The CLI disclosure describes the account linkage and opt-out. Operators must
apply the same analytics access controls, deployment region, retention, and
account-deletion handling as the existing Cook Web distinct identity. Before
production release, record the actual collector/site, authorized report
readers, retention setting, and deletion procedure; this PR does not establish
those deployment-specific facts or turn pseudonymous data into anonymous data.
No SQL models, migrations, token-attribution storage, or Agent-model API calls
are introduced.

## Rollout and acceptance

Release the backend before distributing the new Skill. Existing clients and
older backends tolerate absent or unknown headers. Do not call the rollout
verified until a controlled Skill request is observed in the configured Umami
site with the expected account distinct ID, allowed fields, operation and
outcome, and the aggregate report is read back. Keep test traffic in a separate
site or exclude explicitly designated test accounts inside the protected
reporting environment. Historical pre-release days are uncovered, not zero.

Regression coverage must verify the exact schema, authentication-selected
identity, exclusions, HTTP-200 business failures, download nonconsumption,
one event per response, missing/invalid headers, opt-out, environment-presence
semantics, dotenv isolation, Agent conflicts, and fail-open delivery.

## Operation allowlist

The operation comes from matched backend endpoint and method, never request
paths, parameters, a query body, or a caller-provided operation label.

| Method | Flask endpoint | Operation |
| --- | --- | --- |
| GET | `get_shifu_list_api` | `course_list` |
| PUT | `create_shifu_api` | `course_create` |
| GET | `get_shifu_detail_api` | `course_get` |
| POST | `save_shifu_detail_api` | `course_update` |
| POST | `archive_shifu_api` | `course_archive` |
| POST | `unarchive_shifu_api` | `course_unarchive` |
| POST | `publish_shifu_api` | `course_publish` |
| GET | `export_shifu_api` | `course_export` |
| GET | `get_outline_tree_api` | `outline_list` |
| GET | `get_unit_info_api` | `outline_get` |
| PUT | `create_outline_api` | `outline_create` |
| POST | `modify_outline_api` | `outline_update` |
| DELETE | `delete_unit_api` | `outline_delete` |
| PATCH | `update_chapter_order_api` | `outline_reorder` |
| GET | `get_mdflow_api` | `content_get` |
| POST | `save_mdflow_api` | `content_save` |
| GET | `get_mdflow_history_api` | `content_history_list` |
| GET | `get_mdflow_history_version_detail_api` | `content_history_get` |
| GET | `get_draft_meta_api` | `draft_meta_get` |
| POST | `upfile_api` | `asset_upload` |
| POST | `upload_url_api` | `asset_url_upload` |
| POST | `creator_analytics_query` | `analytics_query` |
| POST | `creator_analytics_credit_detail` | `analytics_credit_detail` |

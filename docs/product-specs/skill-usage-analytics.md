---
title: Skill Usage Analytics
status: implemented
owner_surface: frontend-backend
last_reviewed: 2026-10-17
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

## Pageview contract: `skill_api_request_v2`

- Decision: measure authenticated Skill adoption, operation mix, failures, and
  return usage in Umami, with native Pages, Browser, OS, and account activity.
- Actor: an account-authenticated, allowlisted endpoint/method request carrying
  all three valid Skill headers. Exclude login, device polling, verification,
  configuration, update checks, local commands, unauthenticated requests, and
  missing or invalid metadata. Existing endpoint/authentication scope is unchanged.
- Trigger: response preparation completes once per HTTP request, including
  failures. HTTP 200 with nonzero business `code` is failure. File export
  success means response preparation, not stream consumption or client receipt.
- Count unit: an API request, not a CLI command or human visit. Commands can
  call several endpoints; retries are independent requests. Delivery is best
  effort with no replay. Account and session counts are separate measures.
- Identity: only authenticated `request.user.user_id`, serialized exactly as
  existing Web identify, becomes top-level `payload.id`. Never infer identity
  from metadata, environment, unverified JWTs, or independently reread tokens.
- Consumers: [Skill usage reporting](../references/skill-usage-reporting.md)
  and native Umami pageview/client/account activity reports.

### Delivery and client classification

A single bounded background job attempts `type="identify"`, then one
`type="event"` pageview even if identify fails. Both have identical website,
account id, timestamp, HTTP User-Agent, and top-level browser/os/device.
Identify has no data. Pageview entirely omits `name`; it is not a custom event.
Use the existing Web website configuration without modifying Web producers,
identify, identity rules, events, pageviews, or UA.

| Field | Contract |
| --- | --- |
| `browser` | Top-level fixed `AI-Shifu CLI` |
| `os` | Top-level Agent label from the fixed table below |
| `device` | Top-level fixed `desktop`, a synthetic category, not observed hardware |
| `hostname` | Pageview fixed `server.ai-shifu` |
| `url` | Pageview matched allowlisted backend route template |
| `tag` | Pageview fixed `skill_api_request_v2` |
| `timestamp` | Integer Unix seconds captured in UTC at response preparation, before queue submission |

HTTP User-Agent is `Mozilla/5.0 AI-Shifu-CLI/1.0 (<UA name>)`. Its `1.0` is a
fixed reporting protocol, unrelated to Skill releases. Do not set
`payload.userAgent`, forward the client UA, send `x-umami-cache`, or share a
collector cache across requests or Agents. Different Agent UAs separate
sessions under Umami 3.4; `payload.os` alone does not separate sessions.

| caller_agent | os | UA name |
| --- | --- | --- |
| `codex` | `Codex` | `Codex` |
| `claude_code` | `Claude Code` | `Claude-Code` |
| `cursor` | `Cursor` | `Cursor` |
| `hermes` | `Hermes` | `Hermes` |
| `openclaw` | `OpenClaw` | `OpenClaw` |
| `workbuddy` | `WorkBuddy` | `WorkBuddy` |
| `qoderwork` | `QoderWork` | `QoderWork` |
| `grok_bot` | `Grok Bot` | `Grok` |
| `unknown` | `Unknown Agent` | `Unknown` |

All values are generated by backend enum mappings. `Grok-Bot` must not appear
in the UA because it matches the bot filter; `Grok Bot` remains the OS label.
Do not disable bot checks or set `DISABLE_BOT_CHECK`.

### Safe routes and event data

Derive the path only from the actually matched Flask rule with an allowlisted
endpoint/method and exact normalized template. Replace dynamic segments,
including converter syntax, with `:parameter_name`; for example,
`/api/shifu/shifus/:shifu_bid/detail`. Never include real IDs, query strings,
fragments, credentials, complete URLs, local paths, or user input. No safe
matched template means skip telemetry, without falling back to `request.path`.
Still retain valid Skill-request state for legacy-stage suppression.

Pageview data has exactly these seven fields:

| Field | Type / allowed values | Purpose |
| --- | --- | --- |
| `skill_id` | Fixed `ai-shifu-course-creator` | Skill selection |
| `skill_version_major` | `v0` through `v9`, otherwise `unknown` | Release family |
| `caller_agent` | Agent enum above | Agent adoption |
| `operation` | Endpoint/method operation enum below | Capability mix |
| `method` | Allowlisted HTTP method for the operation | Request classification |
| `outcome` | `success`, `failure` | Success/failure trends |
| `duration_ms` | Nonnegative integer | Response preparation duration |

No account ID belongs in data. Do not collect environment values, session or
thread IDs, model or Agent versions, tokens, cookies, raw headers/errors,
request/response bodies, content, titles, prompts, model output, real resource
IDs, client IP/UA, referrer, screen, or language. These are account-linked
pseudonymous records, not anonymous data.

## Compatibility and reporting

Replace `skill_api_request_v1` for each valid new Skill request; do not double
write an equivalent custom event. Preserve historical v1 data, older clients,
authorization events, and all other shared-sender callers. Valid Skill metadata
continues suppressing the old external-course journey events. Do not sum those
stage events with request records or infer command counts from request counts.

Queries accept historical custom v1 and v2 pageview plus fixed tag. Historical
v1 lacks method and is not required to satisfy the new seven-field contract.
Use successful requests for existing Skill active-account/cohort metrics, but
include failures in request volume. Cross-channel account counts deduplicate
by the same distinct identity; never add Web and CLI account totals. Native
Browser/OS cards classify sessions, not distinct accounts. The shared website's
total PV grows; unchanged Web production behavior does not preserve total PV.
Web-only reports retain the existing Web-hostname allowlist. Same-account
activity can be associated across sessions; a shared session and automatic
cross-session funnels are not promised. Do not fan out aggregate joins through
`session_link` or guess identities for uncovered historical rows.

## Isolation and privacy operations

Reuse the existing two-worker sender with at most 32 queued/in-flight jobs,
short timeouts, and exception isolation. One identify/pageview pair occupies
one slot. Missing configuration, queue saturation, network errors, or collector
rejection must not change business responses or transactions. Do not consume
streams or add automatic retries/replay.

HTTP 200 plus `{"beep":"boop"}` is bot filtering, not successful ingestion.
A normal acknowledgement also cannot prove identity linkage: Umami can catch
session-link errors internally. Verify stored records and native activity.

The CLI disclosure explains account linkage and opt-out. Apply existing Web
analytics access, region, retention, and account-deletion controls. Before
production release record the collector/site, authorized readers, retention,
and deletion procedure. No business models, migrations, token storage, direct
CLI collector call, or Agent/model API is introduced.

## Deployment and acceptance

The implementation targets official Umami 3.4.0. Read-only inspection on
2026-10-17 confirmed the existing deployment runs 3.1.0, including its startup
package version. Under 3.1, identified session IDs do not include UA, and the
first Agent's OS can persist for later Agents of the same account; 3.1 also
lacks the 3.4 identity-link behavior. Do not upgrade automatically, claim
compatibility, or release this change to that collector as verified.

Sources: [3.4 collector](https://github.com/umami-software/umami/blob/v3.4.0/src/app/api/send/route.ts),
[3.1 collector](https://github.com/umami-software/umami/blob/v3.1.0/src/app/api/send/route.ts).

Stage backend before Skill distribution only against a confirmed compatible
collector. Until an authorized 3.4 test site is available, actual storage/UI
acceptance remains open. In that site use one test account for Web and at least
two Agents; read back pageview type, tag, safe route, seven-field data, Browser,
OS, distinct identity, and `session_link`. Check identify/pageview actually
resolve to the same session, including the collector-observed source IP, then
check cross-session native Activity and aggregate results. Sending logs or
HTTP 200 do not satisfy acceptance. Keep test traffic separate and report
coverage gaps rather than zero activity.

Regressions cover presence-only detection and dotenv isolation, fixed UAs
against the target isbot version, all client/identity/time fields, safe routes,
privacy, authentication/exclusions/opt-out, HTTP/business failures, download
nonconsumption, once-only triggering, delayed queue execution, fail-open
identify/pageview, unchanged legacy callers/Web, and mixed-history queries.

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

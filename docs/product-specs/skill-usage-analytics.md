---
title: Skill Usage Analytics
status: implemented
owner_surface: frontend-backend
last_reviewed: 2026-10-23
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

The backend applies the shared [analytics user exclusion policy](../references/frontend-product-analytics.md#analytics-user-exclusions)
to known accounts before queueing CLI identify/pageview pairs or legacy
external-client events. `ANALYTICS_EXCLUDED_USER_IDS` changes the measured
population without changing event names, dimensions, or business outcomes.

The Skill CLI adds these headers to authenticated business requests:

| Header | Accepted value |
| --- | --- |
| `X-AI-Shifu-Skill` | `ai-shifu-course-creator` |
| `X-AI-Shifu-Skill-Version` | Installed CLI/Skill release: three ASCII numeric components, each 1–6 digits, without prerelease/build suffixes; its full version appears in the HTTP UA and its major bucket appears in data |
| `X-AI-Shifu-Caller-Agent` | One of the 35 canonical IDs in the client table below, or `unknown` |
| `X-AI-Shifu-Caller-Agent-Name` | Fixed CLI-generated display label from the client table below; must match the Agent enum |

These are outbound metadata generated inside the CLI, not CLI parameters.
The CLI is bundled with the Skill and uses the same installed release version.
It detects the Agent and generates the display label; the backend validates
both allowlists and their correspondence, then generates the UA. Missing or
invalid display metadata takes the existing invalid-metadata path. Older
clients without valid metadata keep their legacy behavior.

### Agent detection: pinned detect_agent.md 0.1.5

Implement the [requested specification](https://github.com/ai-shifu/detect_agent/blob/9eee13ebdd8dcee22bd90b03125fa9f509a80be1/detect_agent.md)
locally in Python, pinned to commit `9eee13ebdd8dcee22bd90b03125fa9f509a80be1`.
There is no runtime GitHub request, SDK, vendor API, or external dependency.
The detector returns internal `agent_id` and `evidence`, evaluates the supplied
lookup provider when called, and preserves its name-case semantics. The CLI
calls it before dotenv/profile loading for each invocation; it does not keep a
process-lifetime detection cache.

- Explicit `AI_AGENT`, then `AGENT` declarations take precedence. Apply only
  ASCII trim/lowercase and documented declaration aliases. An unrecognized
  nonempty declaration blocks marker fallback and reports unknown.
- Evaluate all 28 runtime rules in specification order, preserving AND/OR
  groups. First match wins; simultaneous independent markers are no longer
  automatically treated as a conflict.
- Ordinary markers use nonempty checks: empty strings fail; `0`, `false`, and
  whitespace pass. Only `GROK_AGENT=1` and
  `CURSOR_EXTENSION_HOST_ROLE=agent-exec` use exact runtime comparisons.
- Evaluate the eight context hints after runtime rules. The pure detector
  supports supplied filesystem/TTY probes for conformance; CLI invocation
  supplies neither and does not scan files or parent processes. Context-only
  evidence is never promoted to Agent execution.
- Publish a canonical ID only for `declared` or `runtime-marker` evidence;
  null IDs, `context-hint`, and `none` produce `unknown` / `Unknown Agent`.
  Evidence remains internal and does not add an event property.

Read only listed variable names. Values are compared locally as the specification
requires; never enumerate, log, transmit, or persist environment values, paths,
session IDs, credentials, or models. These signals identify an associated
process environment, not a trusted immediate caller or authenticated account.
Inherited or manually set markers can still misattribute activity.

Inline and pinned supplementary conformance cases cover declaration Unicode,
lookup casing, nonempty/exact semantics, priority, compound rules, context hints,
and changing providers. Vendored test data retains MIT attribution. Rule changes
require an explicit source revision and coordinated producer/consumer tests.
`SHIFU_DISABLE_ANALYTICS=1`, in the process or Skill dotenv configuration, omits
all four metadata headers without changing authentication or business results.

## Pageview contract: `skill_api_request_v2`

- Decision: measure authenticated Skill adoption, operation mix, failures, and
  return usage in Umami, with native Pages, Browser, OS, and account activity.
- Actor: an account-authenticated, allowlisted endpoint/method request carrying
  all four valid CLI metadata headers. Exclude login, device polling, verification,
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

HTTP User-Agent is `Mozilla/5.0 AI-Shifu-CLI/<installed version> (<UA name>)`,
for example `Mozilla/5.0 AI-Shifu-CLI/2.0.0 (Codex)`. The backend generates it
from the validated numeric release and display label; it never forwards a client UA.
Both request metadata and the sender reject version suffixes so arbitrary text
cannot enter the UA through a prerelease or build label. Do not set
`payload.userAgent`, forward the client UA, send `x-umami-cache`, or share a
collector cache across requests or Agents. Different Agent UAs separate
sessions under Umami 3.4; `payload.os` alone does not separate sessions.
A CLI upgrade changes the UA and may create a new session; distinct account
identity and cross-channel account deduplication remain unchanged.

| caller_agent | CLI-generated os | Backend UA token |
| --- | --- | --- |
| `antigravity` | `Antigravity` | `Antigravity` |
| `augment-cli` | `Augment CLI` | `Augment CLI` |
| `claude-code` | `Claude Code` | `Claude-Code` |
| `cline` | `Cline` | `Cline` |
| `codex` | `Codex` | `Codex` |
| `cowork` | `Claude Cowork` | `Claude Cowork` |
| `crush` | `Crush` | `Crush` |
| `cue` | `Cue` | `Cue` |
| `cursor` | `Cursor` | `Cursor` |
| `cursor-cli` | `Cursor CLI` | `Cursor CLI` |
| `devin` | `Devin` | `Devin` |
| `doubao-work` | `Doubao Work` | `Doubao Work` |
| `gemini-cli` | `Gemini CLI` | `Gemini CLI` |
| `github-copilot` | `GitHub Copilot` | `GitHub Copilot` |
| `goose` | `Goose` | `Goose` |
| `grok-bot` | `Grok Bot` | `Grok` |
| `grok-build` | `Grok Build` | `Grok-Build` |
| `hermes-agent` | `Hermes Agent` | `Hermes` |
| `hi` | `hi` | `hi` |
| `junie` | `Junie` | `Junie` |
| `kilo-code` | `Kilo Code` | `Kilo Code` |
| `kimi` | `Kimi Code` | `Kimi Code` |
| `kiro` | `Kiro` | `Kiro` |
| `manus` | `Manus` | `Manus` |
| `muse` | `Muse` | `Muse` |
| `openclaw` | `OpenClaw` | `OpenClaw` |
| `opencode` | `opencode` | `opencode` |
| `pi` | `Pi` | `Pi` |
| `qwenwork` | `QwenWork` | `QwenWork` |
| `replit` | `Replit` | `Replit` |
| `sandbase-harness` | `SandBase Harness` | `SandBase Harness` |
| `trae` | `TRAE` | `TRAE` |
| `unknown` | `Unknown Agent` | `Unknown` |
| `vtcode` | `VT Code` | `VT Code` |
| `workbuddy` | `WorkBuddy` | `WorkBuddy` |
| `zed` | `Zed` | `Zed` |

The CLI generates OS display labels. The backend validates the enum/name pair
and formats only the UA token exceptions shown above; it does not render OS
labels from an enum-to-display mapping. `Grok-Bot` must not appear
in the UA because it matches the bot filter; `Grok Bot` remains the OS label.
Likewise, `Hermes Agent` is retained as OS while its UA token is `Hermes`.
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

Shared backend events use HTTP UA `Mozilla/5.0 AI-Shifu-Backend/1.0`; the
fixed `1.0` is its reporting identity version. Their payloads and triggers remain
unchanged. CLI pageviews retain their separate real-release CLI UA above.

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

The implementation targets official Umami 3.4.0. Initial inspection on
2026-10-17 found Umami 3.1.0: identified session IDs did not include UA, the
first Agent's OS could persist, and the 3.4 identity-link behavior was absent.
A later read-only Pod/package check at 03:13 UTC confirmed the actual running
package is now 3.4.0. This task performed no upgrade or service mutation.
The version prerequisite is satisfied; it does not establish that this
unreleased backend/CLI contract is deployed or stored correctly.

Sources: [3.4 collector](https://github.com/umami-software/umami/blob/v3.4.0/src/app/api/send/route.ts),
[3.1 collector](https://github.com/umami-software/umami/blob/v3.1.0/src/app/api/send/route.ts).

Stage backend before Skill distribution only against a confirmed compatible
collector. Actual storage/UI acceptance remains open until an authorized test site and
controlled request are available. In that site use one test account for Web and at least
two Agents; read back pageview type, tag, safe route, seven-field data, Browser,
OS, distinct identity, and `session_link`. Check identify/pageview actually
resolve to the same session, including the collector-observed source IP, then
check cross-session native Activity and aggregate results. Sending logs or
HTTP 200 do not satisfy acceptance. Keep test traffic separate and report
coverage gaps rather than zero activity.

Regressions cover pinned detection conformance and dotenv isolation, real-version UAs
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

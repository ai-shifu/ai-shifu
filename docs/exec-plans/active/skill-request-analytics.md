# Account-linked Skill request pageviews

## Purpose / Big Picture

Implement the approved backend measurement of AI-Shifu Course Creator Skill
business requests, with the invoking Agent detected inside the Skill CLI.
The canonical event, privacy, identity, and compatibility contract is
[Skill usage analytics](../../product-specs/skill-usage-analytics.md).
Implementation spans this backend and a separate `ai-shifu/skills` PR.
Neither PR merges itself or changes a production deployment. The approved v2
revision replaces request custom events with native Umami pageviews while
preserving all Web behavior and legacy shared-sender callers.

## Progress

- [x] 2026-10-16 UTC: Inspected backend authentication, existing bounded Umami
  delivery, browser identify, current CLI transports, and adjacent tests.
- [x] 2026-10-16 UTC: Updated remote refs, created backend task branch, and
  created a separate Skills worktree from its current remote main.
- [x] 2026-10-16 UTC: Defined the request/event and privacy contract, including
  the specific Grok Bot / Cursor shared-marker exception.
- [x] 2026-10-16 UTC: Implement and verify backend hooks, identity, operation allowlist,
  outcome classification, and bounded delivery.
- [x] 2026-10-16 UTC: Implement and verify CLI detection, headers on every business transport,
  exclusions, opt-out, and user disclosure in the separate Skills PR.
- [x] 2026-10-16 UTC: Execute aggregate reporting SQL against 31 synthetic
  PostgreSQL events, including account deduplication and cohort boundaries.
- [x] 2026-10-16 UTC: Pass 160 backend regressions, 302 Skill tests, 167 release
  tool tests, and six cross-repository CLI-to-Flask contract smoke cases.
- [x] 2026-10-16 UTC: Pass repository gates and prepare paired ready PRs for
  the backend and Skill branches, with the backend released first.
- [x] 2026-10-17 UTC: Confirm actual deployment is Umami 3.1.0 from image and
  startup logs; document its incompatible identified-session behavior. Do not upgrade.
- [x] 2026-10-17 UTC: Implement v2 identify/pageview delivery, fixed client
  classification, safe matched templates, response UTC time, and unchanged
  legacy sender behavior; pass 323 backend common-service tests.
- [x] 2026-10-17 UTC: Create a new Skills worktree from PR #193 head; update
  account-linked v2 disclosure without changing CLI runtime; pass 302 Skill
  tests and 167 release-tool tests.
- [x] 2026-10-17 UTC: Execute mixed-history reporting against 109 synthetic
  PostgreSQL events and all 23 operation/method pairs; validate all nine UAs
  against target isbot 5.2.2 with Grok-Bot as a filtered negative control.
- [x] 2026-10-17 UTC: Pass full lefthook, development-tool, architecture,
  unit-of-work, and documentation gates; prepare paired ready-PR updates with
  the v2 contract and remaining deployment acceptance.
- [ ] In an authorized compatible Umami 3.4 test site, verify stored pageviews,
  Browser/OS, per-Agent sessions, distinct ID/session_link, native Activity,
  and aggregate reports. No compatible test site is currently confirmed.
- [ ] After separately approved compatible deployment/release, repeat actual
  storage/UI acceptance. Production ingestion remains unverified.

## Surprises & Discoveries

The current CLI no longer emits the old direct events or entry-source marker.
Existing backend external events only cover selected device/course stages and
lack account distinct identity. They cannot establish account retention.
The reused sender's `AIShifuServer` User-Agent matched Umami's `isbot` filter;
the application User-Agent now omits that match without forwarding client
device data. A check against the actual `isbot` package confirms the old value
is filtered and the replacement is accepted. PostgreSQL fixtures caught and
fixed the missing custom-event-kind guard in the report's Skill CTE.
Grok Bot injects both `SAND_AGENT` and `CURSOR_AGENT`; ordinary conflict
handling needs one evidence-based exception. Manus/Cue variables observed at
the operator process do not prove inheritance by Skill subprocesses.

The existing deployment actually runs Umami 3.1.0. With an account ID its
session key omits UA, so different Agents can retain the first session's OS.
Umami 3.4 supports top-level client overrides and UA-separated identified
sessions, plus native session links. Do not upgrade within this task. HTTP 200
can be a bot-filter response; even a normal acknowledgement can hide an
internal session-link failure. Storage and UI readback remain necessary.

## Decision Log

- Detect fixed environment-name existence once before dotenv. Do not accept
  caller flags or collect values, model, Agent version, or raw environment.
- Preserve unknown attribution for missing/conflicting evidence. Identify the
  QoderWork family without inferring regional branding.
- Count backend API requests using endpoint/method enums, not invented
  command-level successes. Import and sync fan out into ordinary API steps.
- Use the authenticated backend account ID in Umami's distinct-ID field,
  matching browser identify. Deduplicate reports by accounts, not visitors.
- Reuse bounded async delivery and keep analytics outside correctness. Add no
  business persistence, direct CLI Umami call, or new dashboard.
- Stage backend and Skill releases, preserving old clients and separating the
  legacy stage series from the new versioned request series.

- 2026-10-17: Replace valid Skill request v1 events with one no-name v2
  pageview tagged `skill_api_request_v2`, preceded by a best-effort identify.
  Both attempts share authenticated identity, client fields, UA, and timestamp.
- Keep Web and legacy senders unchanged; use a dedicated Skill job sharing
  the existing bounded executor rather than changing generic delivery.
- Use exact matched route-template allowlisting, never request paths or input.
  A template failure skips telemetry but preserves legacy-event suppression.
- Keep historical v1 consumers; count requests, successes, accounts, sessions,
  and pageviews separately. Never fan out aggregation through session_link.
- Target 3.4 only; record 3.1 incompatibility and leave real deployment/readback
  acceptance open, without automatic upgrades or unverified production claims.

## Outcomes & Retrospective

The original v1 implementation and its prior smoke checks remain historical
validation. The v2 revision passes 323 backend common-service tests, 302 Skill
tests, 167 release-tool tests, and 109 PostgreSQL fixture events. All 23 actual
routes were independently checked against the exact template map. All nine
producer UAs pass target isbot 5.2.2; Grok-Bot is filtered. CLI runtime and Web
files are unchanged. Repository gates and final paired PR updates are recorded
in Progress. No deployment or actual collector storage/UI acceptance is claimed.

## Context and Orientation

`src/api/flaskr/service/common/server_analytics.py` owns bounded delivery.
Authentication supplies `request.user`; Cook Web uses its `user_id` in
`src/web/src/lib/tracking.ts`. The Skill's deterministic transports live in
`skills/ai-shifu-course-creator/scripts/shifu-cli.py` in `ai-shifu/skills`.
Earlier plans describe the legacy external-stage contract and remain historical
context for its consumers, not the new request series.

## Plan of Work

Preserve request eligibility, authentication, outcome handling, and once-only
consumption. Add safe matched-template routing and capture UTC seconds before
queueing one identify/pageview pair. Generate all client labels and distinct
UA values from the backend enum. Preserve shared sender behavior. In the new
Skills worktree update canonical analytics and opt-out disclosure. Update
versioned product contract, mixed-history SQL and synthetic regression fixtures.

## Concrete Steps

Use the backend development environment on PATH, including pinned Ruff 0.16.5.
Run `python scripts/check_dev_tools.py` and `lefthook run pre-commit --all-files`
before committing. Backend validation: `cd src/api && python -m pytest
tests/service/common/ -q`. Run architecture, unit-of-work, and doc-harness gates;
regenerate indexes after staging intended document changes.

Run `node scripts/test_skill_usage_reporting.mjs <external-pglite-entry>` and
`node scripts/test_skill_analytics_user_agents.mjs <external-isbot-directory>`.
Test-only dependencies may live outside the repository; the UA check asserts
isbot 5.2.2 from official Umami 3.4.0's lockfile. The tests send no real events.
In the new Skills worktree run its quality validator, complete Skill unittest
suite, release-tool suite, and changed-file pre-commit checks.

Commit English Conventional Commit titles with Changed/Benefit sections and
fast-forward only existing PR feature branches. Keep PR #3143 and Skills #193
ready and accurate; never merge main or deploy/upgrade Umami here.

## Validation and Acceptance

Use the canonical spec's complete regression checklist. Check exact top-level
identity/client/time fields across identify and pageview; no name, raw UA,
cache, or forbidden data. Test route converters, wrong/missing templates,
non-UTC host time and delayed workers, HTTP/business failures, download
nonconsumption, once-only response triggering, queue saturation, configuration
failures and identify rejection without suppressing pageview. Assert ordinary
Web/invalid metadata requests and all legacy shared-sender payloads are unchanged.

Mixed v1/v2 reporting must preserve Shanghai/cohort boundaries, distinct-account
unions, Web hostname exclusion, successful-only active days, and separate
request/session counts. Missing identity cannot become an inferred account.
In an authorized 3.4 test site read back one account across Web and two Agents,
including session_link and native client/activity cards. Verify both sends
actually resolve to the same session despite collector source-IP inputs. Local
unit tests or HTTP acknowledgements cannot close this external acceptance.

## Idempotence and Recovery

Removing the three headers opts a request out without changing its business
payload. Unavailable analytics loses events rather than blocking requests.
Separate retried requests can produce repeated events; account-day metrics
deduplicate. Backend rollback and Skill rollback are independently safe.
Do not persist inferred Agent identity into user/token/course records.

## Interfaces and Dependencies

Use existing Flask lifecycle/authentication, requests-based Umami transport,
and existing browser identity. No new external runtime dependency. The three
headers and pageview schema are owned by the linked spec. Aggregate consumers
must join Umami sessions by distinct identity, not assume sessions or synthetic
backend hostnames identify individual accounts.

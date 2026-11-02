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

- [x] 2026-10-17 UTC: Review follow-up: restrict historical v1 to the fixed Skill ID; 111 PostgreSQL fixtures pass.

- [x] 2026-10-17 UTC: Review follow-up: replace request-controlled version regex with compatible deterministic parsing; 371 common tests pass, including 48 version cases.

- [x] 2026-10-17 UTC: Review follow-up: skip process-TZ testing where time.tzset is unavailable; preserve the UTC regression on supported platforms.

- [x] 2026-10-17 UTC: Implement detect_agent.md 0.1.5 at 9eee13e locally;
  pass 170 pinned conformance cases and 39 inline examples. CLI generates
  all 35 canonical display labels and sends the fourth metadata header.
- [x] 2026-10-17 UTC: Validate all 36 actual CLI/backend label pairs, use real
  bundled versions in backend-generated UA, and pass 144 isbot samples.
  Keep Hermes Agent/Grok Bot OS labels while using safe Hermes/Grok UA tokens.
- [x] 2026-10-17 UTC: Expand historical reporting to 40 stored Agent IDs;
  169 PostgreSQL fixture events retain cross-channel account deduplication.

- [x] 2026-10-17 UTC: Pass 457 backend common tests, 309 Skill tests, 167
  release-tool tests, full repository gates, and four-channel local packaging.

- [x] 2026-10-17 03:13 UTC: Read-only verification found the replacement Pod
  ready with the official 3.4.0 image digest and actual /app/package.json
  version 3.4.0. This task did not upgrade or mutate the collector. Actual
  backend/CLI record, UI, and identity-link readback remain open.

- [x] 2026-10-17 UTC: Review privacy follow-up: restrict versions at both the
  request and sender boundaries to the CLI's three ASCII numeric components,
  each 1–6 digits, without prerelease/build suffixes. All 477 backend common
  tests pass; arbitrary version-label text cannot enter collector UAs.

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

Initial inspection found Umami 3.1.0; this observation was later superseded
by the read-only 3.4.0 package verification above. Under 3.1, an identified
session key omits UA, so different Agents can retain the first session's OS.
Umami 3.4 supports top-level client overrides and UA-separated identified
sessions, plus native session links. Do not upgrade within this task. HTTP 200
can be a bot-filter response; even a normal acknowledgement can hide an
internal session-link failure. Storage and UI readback remain necessary.

## Decision Log

- 2026-10-17 user review: name the shared sender's application UA
  `Mozilla/5.0 AI-Shifu-Backend/1.0`. Keep its payloads and triggers unchanged;
  CLI pageviews continue using the real-release CLI UA. Verify the backend
  identity against the same target isbot 5.2.2.

- 2026-10-17 user review: replace the original eight-family presence-only
  detector with detect_agent.md 0.1.5 at 9eee13e. Implement its full 35-ID
  result contract locally and retain evidence internally; report only declared
  or runtime-marker IDs, never promote context hints. Update both producers
  and historical report allowlists together. No runtime GitHub or SDK call.

- 2026-10-17 user review: the CLI owns Agent detection and display-label
  generation. Add the display-name header; the backend validates enum/name
  correspondence and generates the UA with the actual bundled CLI release
  version. Shared legacy senders keep their own UA. Use CLI terminology for
  the request producer and retain Skill identifiers as source dimensions.

- Initial implementation, superseded by detector 0.1.5: detect fixed
  environment-name existence once before dotenv. Do not accept
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
- Target 3.4 only; retain the historical 3.1 incompatibility and leave contract deployment/readback
  acceptance open, without automatic upgrades or unverified production claims.

## Outcomes & Retrospective

The v1 and initial eight-family v2 validations remain historical results.
The current revision follows user review: native detect_agent 0.1.5, 35 canonical
IDs plus unknown, CLI-generated display labels, and backend-generated real-version
UAs. The detector's 170 pinned portable cases and 39 inline examples pass; only
declared/runtime-marker results qualify for outbound Agent classification.
Cross-repository checks confirm all 36 labels match backend validation, and 144
real-version UAs pass target isbot 5.2.2. Grok-Bot remains a filtered negative
control; Hermes Agent needs the safe Hermes UA token. Reporting passes 169
PostgreSQL fixtures and preserves legacy IDs instead of renaming history.
Actual storage/UI acceptance remains open; production ingestion is not claimed.

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
queueing one identify/pageview pair. Generate display labels in the CLI and validate them in the backend;
generate distinct real-version UA values only in the backend. Preserve shared sender behavior. In the new
Skills worktree update canonical analytics and opt-out disclosure. Update
versioned product contract, mixed-history SQL and synthetic regression fixtures.

## Concrete Steps

Use the backend development environment on PATH, including pinned Ruff 0.17.3.
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

Removing the four metadata headers opts a request out without changing its business
payload. Unavailable analytics loses events rather than blocking requests.
Separate retried requests can produce repeated events; account-day metrics
deduplicate. Backend rollback and Skill rollback are independently safe.
Do not persist inferred Agent identity into user/token/course records.

## Interfaces and Dependencies

Use existing Flask lifecycle/authentication, requests-based Umami transport,
and existing browser identity. No new external runtime dependency. The four metadata
headers and pageview schema are owned by the linked spec. Aggregate consumers
must join Umami sessions by distinct identity, not assume sessions or synthetic
backend hostnames identify individual accounts.

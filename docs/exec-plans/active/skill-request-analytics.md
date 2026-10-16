# Account-linked Skill request analytics

## Purpose / Big Picture

Implement the approved backend measurement of AI-Shifu Course Creator Skill
business requests, with the invoking Agent detected inside the Skill CLI.
The canonical event, privacy, identity, and compatibility contract is
[Skill usage analytics](../../product-specs/skill-usage-analytics.md).
Implementation spans this backend and a separate `ai-shifu/skills` PR.
Neither PR merges itself or changes a production deployment.

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
- [ ] After maintainer-approved release, verify one real event and aggregate
  report from the configured collector. Production acceptance remains open.

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

## Outcomes & Retrospective

Implementation and independent review are complete. The six cross-repository
smoke cases exercise actual CLI detection/header production and backend
Flask routing with mocked authentication and collector delivery; they cover
Codex, Grok Bot, conflicting markers, success, and HTTP-200 business failure.
PostgreSQL fixtures verify the report's account and date/cohort semantics.
Backend full lefthook, architecture, unit-of-work, and documentation gates
pass. Skill quality and changed-file pre-commit gates pass. The optional
Skills all-files formatter also flagged an existing unrelated WorkBuddy
agent-file blank line; its incidental change was discarded. No deployment, real
collector readback, or production retention coverage is claimed.

## Context and Orientation

`src/api/flaskr/service/common/server_analytics.py` owns bounded delivery.
Authentication supplies `request.user`; Cook Web uses its `user_id` in
`src/web/src/lib/tracking.ts`. The Skill's deterministic transports live in
`skills/ai-shifu-course-creator/scripts/shifu-cli.py` in `ai-shifu/skills`.
Earlier plans describe the legacy external-stage contract and remain historical
context for its consumers, not the new request series.

## Plan of Work

Add central backend lifecycle instrumentation and exact endpoint/method
eligibility, after inspecting all current CLI network paths. Attach only a
validated immutable Skill context, then emit a single terminal response event
using the authenticated account. Preserve legacy stage events for old clients.
In the separate Skills worktree, snapshot detection before config loads and
centralize outbound headers across JSON, safe, conflict, analytics, multipart,
and export transports. Add focused privacy/failure regressions on both sides
and aggregate account/day/cohort reporting queries.

## Concrete Steps

Run focused backend common/auth/course suites and the Skill CLI tests. Run
backend architecture, unit-of-work, doc harness, and pre-commit gates. Generate
knowledge indexes after staging new docs. Create English Conventional Commit
titles with `Changed:` and `Benefit:` bodies, push only feature branches, and
open two non-draft PRs with dependencies and release order.

## Validation and Acceptance

Use the canonical spec's regression checklist. Demonstrate header production
and backend consumption with mocked network/collector boundaries, verify
same account across cookie and header authentication, and retain existing
business error/response behavior. Reporting must use successful requests for
active-account metrics, include `unknown`, distinguish API volume from users,
use Shanghai calendar boundaries with UTC source timestamps, and censor
cohorts whose D1/D7 observation window is incomplete.

## Idempotence and Recovery

Removing the three headers opts a request out without changing its business
payload. Unavailable analytics loses events rather than blocking requests.
Separate retried requests can produce repeated events; account-day metrics
deduplicate. Backend rollback and Skill rollback are independently safe.
Do not persist inferred Agent identity into user/token/course records.

## Interfaces and Dependencies

Use existing Flask lifecycle/authentication, requests-based Umami transport,
and existing browser identity. No new external runtime dependency. The three
headers and event schema are owned by the linked spec. Aggregate consumers
must join Umami sessions by distinct identity, not assume sessions or synthetic
backend hostnames identify individual accounts.

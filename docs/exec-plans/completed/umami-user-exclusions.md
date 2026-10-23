# Configurable Umami user exclusions

## Purpose / Big Picture

Allow operators to exclude selected account IDs from browser and backend
Umami reporting using one backend environment variable. The durable contract
is [Umami user exclusions](../../references/frontend-product-analytics.md#umami-user-exclusions).

## Progress

- [x] 2026-10-23 UTC: Refreshed origin/main and created a dedicated task branch.
- [x] 2026-10-23 UTC: Inspected centralized browser tracking, shared user-info
  responses, CLI request delivery, and legacy external-client producers.
- [x] 2026-10-23 UTC: Defined exact ID matching, private server-side policy,
  browser eligibility, queue disposal, and historical population compatibility.
- [x] 2026-10-23 UTC: Implement policy, sender gates, DTO and browser consumers.
- [x] 2026-10-23 UTC: Pass 1,478 backend tests and 22 focused frontend tests;
  independent static review found no actionable gaps.
- [x] 2026-10-23 UTC: Pass all repository pre-commit checks, including the
  documentation harness after staging generated indexes; prepare PR delivery.

## Surprises & Discoveries

- Browser auto-tracking is already disabled, and application tracking waits
  for identify before draining. Excluded startup calls can be discarded there.
- Legacy backend events do not include account IDs in payloads; their known
  account context can still enforce exclusions without changing that schema.
- Frontend type-check is blocked by existing installed-library locale typing
  mismatches in untouched `src/web/src/lib/markdown-flow-locale.ts` for
  `es-ES` and `ur-PK`. Frontend lint and focused tests pass.

## Decision Log

- Use a comma-separated backend list of exact business `user_id` values.
- Return only `analytics_enabled` on the shared user-info DTO, retaining
  compatibility with clients or servers that lack the field.
- Keep this policy independent of database/cache availability by reading the
  environment configuration layer; policy read failure suppresses telemetry.
- Unidentified guest history cannot be attributed to a future account, and
  already delivered data is outside this setting's scope.

## Outcomes & Retrospective

All requested runtime paths are implemented and locally validated. The 1,478
backend tests cover shared configuration, shared DTOs, user services and
analytics senders; 22 frontend tests cover tracking, user-store propagation
and the loader. Repository pre-commit checks pass. The two pre-existing
installed-library locale typing errors remain outside this change.
This plan's implementation scope is complete; production deployment and
historical data deletion are outside scope.

## Context and Orientation

Backend configuration lives in `src/api/flaskr/common/config.py`. Shared
user-info responses come from `src/api/flaskr/service/common/dtos.py`.
`server_analytics.py` owns backend delivery. Browser tracking lives in
`src/web/src/lib/tracking.ts`, with user-store calls supplying every identity.

## Plan of Work

Register the list, regenerate the Docker example, and expose a shared exclusion
helper. Apply it to user-info serialization and backend enqueue paths. Extend
the browser identity contract to suppress excluded users and invalidate stale
work. Cover exclusion, normal traffic, identity changes, and failures.

## Concrete Steps

1. Register `ANALYTICS_UMAMI_EXCLUDED_USER_IDS` and regenerate env examples.
2. Implement shared policy and pass trusted account IDs to legacy senders.
3. Add per-user eligibility to the backend DTO and frontend interface.
4. Gate browser identify, queueing, draining, events, and pageviews.
5. Run focused backend/frontend tests, lint, type checks and repository gates.

## Validation and Acceptance

Excluded users cause no new Umami identify/event/pageview jobs or browser
calls. Empty configuration and ordinary users keep existing behavior. Queued
calls and late identify completions cannot replay excluded data after an
account switch. Auth and business outcomes remain independent from telemetry.
No exclusion list is returned to the browser or sent in analytics payloads.

## Idempotence and Recovery

Re-running generation and tests is safe. Clearing the variable and restarting
the backend restores eligibility after browser user-info refresh. Existing
Umami history is unchanged. The branch can be reverted without data migration.

## Interfaces and Dependencies

One list-valued backend environment variable and one additive boolean
`analytics_enabled` on user-info responses. No new package or network service.

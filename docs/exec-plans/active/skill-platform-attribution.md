# Skill Channel Analytics Through Umami

> Lifecycle review, 2026-09-26: Backend #2916 and browser #2934 are merged. The separate Skills producer delivery and end-to-end acquisition report remain external dependencies.

## Purpose / Big Picture

AI Shifu needs product analytics that show which controlled Skill package
channel led a user into browser authorization and how Skill users progress
through authorization, course creation/import, and publication. All tracking
goes to Umami. User, course, and event business tables do not store analytics
attribution, and analytics never controls authentication, permissions, course
creation, publication, billing, or another user-visible result.

The backend contribution is intentionally small: validate an allowlisted Skill
identity when a CLI creates a device-authorization request, keep it only in the
existing expiring Redis device session, and return it to the authorization page.
The page and CLI independently send best-effort Umami events. Losing an event is
acceptable; changing the business operation because tracking failed is not.

## Progress

- [x] Defined the controlled `host_platform`, `skill_id`, `skill_version`, and
  request UUID contract.
- [x] Kept validated attribution only in the expiring device-authorization
  session for the browser authorization funnel.
- [x] Removed user attribution, course attribution, journey-event tables,
  migrations, database reports, and course payload coupling from this branch.
- [x] Added focused validation for accepted/rejected attribution and the
  ephemeral device-session round trip.
- [x] 2026-09-26: Confirmed merged backend #2916 and browser consumer #2934.
- [ ] Verify delivery of the separate Skills producer and the resulting end-to-end acquisition report; this repository does not establish that external delivery.

## Decision Log

- Decision: all channel and journey tracking uses Umami rather than business
  persistence. Rationale: product analytics must stay decoupled from correctness
  and operational data.
- Decision: the browser may read attribution only from the expiring device
  session. Rationale: the authorization event needs its originating package,
  but no durable user coloring is required.
- Decision: the CLI reports non-browser milestones directly through its existing
  fail-open Umami tracker. Rationale: CLI actions do not run in the browser and
  must not depend on a new business API.
- Decision: packages own `host_platform`; callers cannot choose an arbitrary
  value. Accepted values are `workbuddy`, `doubao`, `qclaw`, `lobster`, `codex`,
  and `direct`.
- Decision: events contain only allowlisted low-cardinality dimensions. Course
  content, titles, prompts, paths, tokens, contact data, raw errors, URLs, query
  strings, and handoff identifiers are excluded from Umami payloads.

## Context and Orientation

- Shared backend validation: `src/api/flaskr/service/common/skill_attribution.py`.
- Expiring device context: `src/api/flaskr/service/user/device_auth.py`.
- Device authorization route: `src/api/flaskr/route/user.py`.
- CLI Umami transport lives in the Skills repository in
  `skills/ai-shifu-course-creator/scripts/usage_tracker.py`.
- Browser authorization events are implemented by the stacked Cook Web PR and
  documented in the canonical frontend analytics contract.

## Plan of Work

1. Accept optional attribution only when creating a device authorization.
2. Validate the complete object and store it inside the existing Redis session
   with the same TTL; invalid or partial objects fail before session creation.
3. Return the validated object from the pending-device endpoint so Cook Web can
   build sanitized Umami dimensions.
4. Have the Skills CLI report authorization completion, new-course creation or
   import, and publication milestones directly to Umami. Keep tracking opt-out,
   short timeout, privacy allowlist, and fail-open behavior.
5. Have Cook Web report prompt, approve, and deny outcomes through the existing
   `useTracking` contract. Tracking failures must not affect authorization.
6. Keep package channel stamping and verification in the release repository.

## Validation and Acceptance

- Device authorization without attribution behaves exactly as before.
- A complete allowlisted attribution object round-trips through the expiring
  device session; malformed, partial, or unsupported values are rejected.
- No migration, analytics model, course attribution field, journey-event API,
  or database aggregate report remains in the PR diff.
- CLI events go to Umami directly and remain fail-open. Their payload contains
  the controlled channel and Skill version but no course or user-authored data.
- Browser events use the temporary device context, deduplicate the prompt and
  terminal outcomes, exclude the request UUID, and remain fail-open.
- The focused backend and frontend suites pass. This is not a claim that the
  latest synchronized dependency set received a complete local full-stack
  installation or lockfile-environment build.

## Idempotence and Recovery

No analytics write participates in a business transaction. The Redis context
expires with the device request. Umami delivery is best effort and may be lost
or duplicated after retries; dashboards must treat it as behavioral analytics,
not an audit ledger. Retrying a failed user operation follows the operation's
existing rules and does not consult analytics state.

## Interfaces and Dependencies

The optional device request context is:

```json
{
  "host_platform": "workbuddy",
  "skill_id": "ai-shifu-course-creator",
  "skill_version": "1.2.9",
  "handoff_id": "<canonical UUID>"
}
```

`handoff_id` correlates only the expiring authorization request and is never an
Umami dimension. The release pipeline writes `AI_SHIFU_HOST_PLATFORM` into each
controlled package; direct installations use `direct`.

## Surprises & Discoveries

The local backend and browser producer/consumer changes merged separately from the external Skills producer. A repository merge cannot establish end-to-end handoff delivery.

## Outcomes & Retrospective

Backend #2916 and browser attribution #2934 are merged. The external Skills producer and acquisition-report acceptance remain open; existing device authorization payload fields are unchanged by this documentation audit.

## Concrete Steps

Verify the external Skills release revision and handoff behavior, then exercise the existing device authorization and acquisition-report path in a controlled environment. Record aggregate outcomes without handoff identifiers or credentials.

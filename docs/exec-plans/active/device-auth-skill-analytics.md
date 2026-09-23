# Device Authorization Skill Analytics

## Purpose / Big Picture

Extend the existing browser device-authorization funnel so product reports can
compare prompt exposure, approval, and denial by the Skill host platform,
Skill identity, and Skill version that initiated the handoff. The durable
database attribution introduced by the prerequisite Skill-platform PR remains
the source of truth; Umami is a best-effort aggregate view only.

### device authorization Skill dimensions

- Business question: for each supported host platform and Skill version, how
  many resolved authorization prompts are shown, approved, or denied, and
  where does the browser authorization step become a funnel bottleneck?
- Metric definition: in a calendar week, group
  `device_auth_prompt_shown`, `device_auth_approved`, and
  `device_auth_denied` by `host_platform`, `skill_id`, and `skill_version`.
  Approval rate is approvals divided by shown prompts; denial rate is denials
  divided by shown prompts. Counts are aggregate because no handoff identifier
  is sent to Umami.
- Event names: the existing `device_auth_prompt_shown`,
  `device_auth_approved`, and `device_auth_denied` event family.
- Actor and surface: signed-in users on `/login/device`.
- Trigger: unchanged. Exposure fires once after a pending request resolves;
  an outcome fires only after the backend confirms the user's decision.
- Population: attributed Skill handoffs and ordinary unattributed device
  authorization requests. Signed-out visitors emit nothing until signed in.
- Count unit: one pending authorization request.
- Deduplication: unchanged; the live pairing code is retained only in a page
  ref and never sent. One exposure and at most one terminal outcome are
  emitted per resolved request during one mount.
- Correlation: aggregate dimensions only. Device code, handoff ID, user code,
  user identity, URL, referrer, and authored content are excluded.
- Consumers: the periodic Skill acquisition and journey report, grouped by
  host platform, Skill, and version.
- Compatibility: additive payload fields on the existing event family.
  Unattributed requests use the literal enum value `unattributed` for all
  three new dimensions so queries have a stable baseline group.
- Verification: backend tests prove that only the three public attribution
  fields reach the browser; frontend tests prove exact payloads, fallback
  values, deduplication, terminal timing, prohibited-field absence, and
  fail-open tracking.

| Field           | Type   | Allowed values                                                      | Cardinality | Privacy class                   | Why required                     |
| --------------- | ------ | ------------------------------------------------------------------- | ----------- | ------------------------------- | -------------------------------- |
| `host_platform` | string | `workbuddy`, `doubao`, `lobster`, `codex`, `direct`, `unattributed` | low         | non-personal enum               | compare host-platform funnels    |
| `skill_id`      | string | `ai-shifu-course-creator`, `unattributed`                           | low         | non-personal enum               | separate supported Skill funnels |
| `skill_version` | string | validated released Skill version, or `unattributed`                 | bounded     | non-personal release identifier | find version-specific drop-offs  |

The complete event payload remains flat and contains these three fields plus
the existing `device_os` and `from_link` fields.

## Progress

- [x] 2026-09-23 10:30 CST: Confirmed the existing device-authorization event
      family and the prerequisite backend attribution contract.
- [x] 2026-09-23 10:45 CST: Defined the decision, metric, privacy boundary,
      fallback group, and compatibility contract above.
- [x] 2026-09-23 11:05 CST: Exposed only the three allowlisted attribution
  dimensions to the authorization page; handoff identity remains private.
- [x] 2026-09-23 11:15 CST: Extended the existing event producer and focused
  regression tests, including unattributed and fail-open paths.
- [x] 2026-09-23 11:35 CST: Passed focused backend/frontend tests, type-check,
  lint, Ruff, architecture/UoW checks, repository harness, and the complete
  pre-commit gate; prepared the focused stacked pull request.

## Surprises & Discoveries

- Main already contains a privacy-reviewed authorization funnel, so this work
  extends its payload instead of adding duplicate event names.
- The prerequisite backend stores `handoff_id`, but the browser and Umami do
  not need it. The public response must therefore project a strict subset.

## Decision Log

- Decision: build this PR on the open Skill-platform attribution branch and
  target that branch initially. Rationale: the dimensions originate in that
  contract, and a stacked PR keeps both reviews focused.
- Decision: use `unattributed` instead of omitting fields. Rationale: a stable
  baseline group makes denominators and dashboards deterministic without
  inventing a dynamic source value.
- Decision: do not emit `handoff_id`. Rationale: aggregate funnel analysis does
  not require row-level correlation, and the handoff ID is pseudonymous
  workflow identity that should remain in the authoritative database.

## Outcomes & Retrospective

The browser authorization funnel now distinguishes supported host platforms,
the course-creator Skill, and Skill versions without exposing handoff or
pairing credentials. Ordinary device requests remain visible as one stable
`unattributed` group. Focused and repository-wide required gates pass. The
change is ready for review as a focused stacked pull request.

## Context and Orientation

Device authorization is implemented in
`src/api/flaskr/service/user/device_auth.py` and exposed through the user
routes. The approval page and its producer tests live under
`src/web/src/app/login/device/`. The existing analytics contract is
`docs/exec-plans/active/account-session-analytics.md`.

## Plan of Work

Project the validated cached attribution into the pending-request response as
only `host_platform`, `skill_id`, and `skill_version`. Normalize that public
object through a frontend allowlist and append the resulting stable dimensions
to all three existing events. Preserve the existing trigger and deduplication
logic.

## Concrete Steps

1. Add a backend public-projection helper and tests for attributed and ordinary
   requests, including a negative assertion for `handoff_id`.
2. Add typed frontend normalization with explicit platform and Skill
   allowlists and an `unattributed` fallback.
3. Extend prompt and terminal payloads and update producer tests.
4. Update the canonical account-session contract and this plan's outcome.
5. Validate, commit, push, and open a stacked PR against the prerequisite
   branch.

## Validation and Acceptance

- Attributed prompts and their confirmed terminal outcomes carry the same
  three Skill dimensions.
- Ordinary device authorization events use only the documented unattributed
  values.
- Re-renders do not add exposure events; failed decisions do not add terminal
  events.
- No handoff ID, pairing code, device name, raw OS value, user data, raw error,
  or URL enters the event payload.
- A tracking exception does not change prompt rendering or approval.

## Idempotence and Recovery

The backend change is read-only projection. Repeating a pending lookup does not
mutate attribution. Frontend event delivery remains best effort and preserves
the existing per-mount deduplication; retrying the business action is governed
by the existing authorization state machine, not by analytics.

## Interfaces and Dependencies

This PR depends on the Skill-platform attribution PR that stores validated
`registration_attribution`. The browser receives a public subset without
`handoff_id`. Umami events use the existing shared `useTracking` transport and
do not introduce configuration or a new analytics dependency.

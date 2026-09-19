# Charge settings previews to the course owner

## Purpose / Big Picture

Ask and TTS settings previews must charge the course owner even when an authorized
collaborator invokes them. The requesting user remains the actor in metering.

## Progress

- [x] 2026-09-19 02:35 UTC: Confirmed owner billing, course permissions, frontend
  caller-wallet gates, and settings preview call sites.
- [x] 2026-09-19 03:02 UTC: Implemented the coordinated API, frontend, and
  metering contract; 542 backend and 75 frontend tests passed.
- [x] 2026-09-19 03:05 UTC: Locked-dependency type checking, frontend lint,
  repository harness, architecture boundaries, and all-file pre-commit checks
  passed. Prepared the PR title and description for the completed change.

## Surprises & Discoveries

The settings UI gates debug using the caller's billing overview. The existing
course preview UI already limits that local gate to owners and relies on backend
admission for collaborators. Reuse that policy for settings previews.

The initial shared node_modules link contained markdown-flow-ui 0.2.21 instead of
the lockfile version 0.2.26. An isolated npm ci installation supplies the locked
dependencies without modifying another checkout.

## Decision Log

- Settings requests require a nonempty body `shifu_bid` and course edit permission,
  consistent with editable settings. Reuse the existing permission verifier.
- Resolve the owner on the server for debug limits and admission; record both
  course and actor so the existing billing ownership resolver charges the owner.
- Keep settings usage explicitly billable, including arbitrary settings submitted
  for demo courses. Existing built-in course-preview exemptions and explicit
  internal low-level metering overrides remain unchanged.
- Keep cloned voice ownership authorization tied to the actor. Changing who pays
  does not grant access to another user's private cloned voices.
- This is a correction to an existing preview workflow, with no new UI action or
  event contract. Preserve existing settings-save analytics and test it alongside
  the request payload and collaborator gate correction.

## Outcomes & Retrospective

Real admission, usage recording, and settlement tests prove the owner is debited
while the caller remains the actor. Permission and spoofing regressions pass.
All local verification passed: 542 backend tests, 75 frontend tests, type
checking, lint, repository harness, architecture checks, and all-file pre-commit
checks. The API and web must deploy together because missing course IDs fail
closed. No migration or model-tier change is included.

## Context and Orientation

`src/api/flaskr/service/shifu/route.py` owns both settings endpoints.
`tts_preview.py` creates TTS segment/root usage. Billing ownership already resolves
`shifu_bid` before `user_bid`. `ShifuSetting.tsx` sends both preview requests.

## Plan of Work

Validate one course ID before admission, carry it into LLM/TTS metering, and send
it from both existing UI controls. Align local eligibility and credit-error
messaging with course ownership. Update the billing design and regression tests.

## Concrete Steps

Run the focused preview tests, related shifu/billing/metering tests, settings Jest
tests, type checking, lint, repository harness and all-file pre-commit checks.
Commit and push this change to `sunner/preview-billing-admission` and update #2860.

## Validation and Acceptance

Both roles with edit permission charge the server-resolved owner. Missing course,
foreign course, and view-only permissions cannot invoke a provider. Owner limits
block calls regardless of caller funds; caller limits do not block a funded
owner. Direct LLM, fallback, synthesis, and TTS preserve actor and course. Client
payer, free-usage, or internal flags cannot override the contract.

## Idempotence and Recovery

No schema changes. Old clients without a course ID fail closed; deploy the API
and web update together. Do not fall back to caller billing. Reverting requires
coordinated API/web changes, not an admission bypass.

## Interfaces and Dependencies

Existing endpoint URLs and response envelopes remain. JSON `shifu_bid` becomes
required for both settings previews. No new billing service or analytics API.

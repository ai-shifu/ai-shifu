# Gemini Live follow-up acceptance

> Lifecycle review, 2026-09-26: Local implementation is merged; real Gemini, physical browser/audio, Redis/MySQL integration and controlled dev enablement remain unverified.

## Purpose / Big Picture

Close the remaining real-provider and deployment acceptance for the implemented
embedded Live follow-up. The current behavior is defined in
`docs/references/gemini-live-follow-up.md` and its linked analytics specification.

## Progress

- [x] 2026-09-26: Confirmed merged implementation including #2744, Live-only
  prompt #2780, and model upgrade #2826 against the audited main baseline.
- [x] 2026-09-26: Preserved the original delivery journal in `docs/history/`;
  earlier standalone dialogs, quotas and open-PR instructions are superseded.
- [ ] Reproduce admission/ownership and persistence acceptance with real Redis
  and MySQL, recording image/configuration and results.
- [ ] Deploy compatible API/web to the controlled dev environment, drain
  pre-upgrade admissions, and validate enabled rotation and Live-only prompts.
- [ ] Exercise a real ephemeral credential and direct Gemini WebSocket with
  microphone permissions; verify selected voice and audible responses.
- [ ] Complete Chrome, physical Safari/iOS and mobile Chrome acceptance for
  multi-turn speech, interruption, transcripts, renewal/ending, microphone
  release and restoration of lesson narration.

## Surprises & Discoveries

The previous journal mixed delivered changes and obsolete proposals. Its
local regression evidence does not establish provider or physical-device
acceptance. Production enablement is outside this plan.

## Decision Log

- 2026-09-26: Keep acceptance active. Merge state resolves publishing tasks,
  not the missing external tests. Capacity rollout has its own active plan.
- Preserve the existing ask store, explicit microphone consent, fail-closed
  ownership checks and conservative credential accounting.

## Outcomes & Retrospective

Recorded local evidence includes frontend/Live/backend suites and the full
pre-commit gate. The later model upgrade removed unsupported thinking options.
No new deployment, data migration or real-provider acceptance was performed
by the documentation audit. See the dated journal for individual test runs.

## Context and Orientation

The learner AskBlock and Live controller share history; backend admission,
session binding and turn reporting own credential and persisted-state safety.
Read `docs/references/gemini-live-follow-up.md` before changing their contract.

## Plan of Work

Prepare a credentialed dev environment, validate Redis/MySQL behavior, then
exercise the physical audio/device matrix. Record observed results and any
remaining failure individually; archive only when the original matrix passes.

## Concrete Steps

Run the existing Live admission, session, controller and AskBlock regressions.
Use the existing dev deployment workflow for compatible images and configuration.
Capture privacy-safe timestamps, image revisions and outcome summaries for the
listed acceptance cases; never record credentials, transcripts or user data.

## Validation and Acceptance

Every unchecked item above requires its own observable evidence. Renewals must
preserve consent and history without replaying a question; interruption must
stop previous playback; scope termination releases capture and ownership.
Record browser/device and tested image, including any autoplay limitations.

## Idempotence and Recovery

Do not clear Redis reservations to manufacture capacity. Roll back enablement
through configuration and allow outstanding credential risk to expire. Keep
provider turn reports independently idempotent; do not replay ambiguous input.

## Interfaces and Dependencies

Depends on valid dev provider credentials, real Redis/MySQL, microphone access,
physical devices and compatible API/web deployments. See the separate
`gemini-live-configurable-capacity.md` plan for US capacity rollout.

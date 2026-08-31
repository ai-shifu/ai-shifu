# Reuse Email and SMS Verification Login

## Purpose / Big Picture

PR #1839 adds email verification-code login beside the existing SMS flow. The
two channels should share the behavior that is semantically identical without
changing their public HTTP contracts or channel-specific delivery behavior.
After this work, both flows use one frontend form implementation, one auth-hook
orchestration path, one backend login coordinator, and one verification-code
preparation helper. SMS captcha and Aliyun delivery remain phone-specific;
SMTP delivery and email copy remain email-specific.

## Progress

- [x] 2026-08-31 15:49 CST: Confirmed the live PR head matches the clean local
      checkout at `d7a3d9b0f0c41cbc3cdc8dcebe66b30e2eef6f3e`.
- [x] 2026-08-31 15:49 CST: Audited the frontend components, `useAuth`, auth
      providers, route handlers, verification-code utilities, i18n keys, and
      focused tests.
- [x] 2026-08-31 16:02 CST: Implemented shared frontend verification-code login
  behavior and neutral auth translations.
- [x] 2026-08-31 16:05 CST: Implemented shared backend challenge preparation and
  login orchestration while preserving route payloads.
- [x] 2026-08-31 16:08 CST: Added focused frontend/backend regression coverage.
- [x] 2026-08-31 16:13 CST: Passed focused tests, type-check, lint, translation,
  repository harness, architecture, Ruff, and full pre-commit checks after
  ratcheting the reduced unit-of-work commit-site baseline.
- [ ] 2026-08-31 16:13 CST: Commit, push, update the PR description, and follow
  the current head through CI and review convergence.

## Surprises & Discoveries

- The SMS rate-limit translation key raised by the backend is
  `server.user.smsSendTooFrequent`, but `error_codes.json` contains the older
  `server.user.smsSendFrequently` spelling at code 1012. This makes the SMS
  path fall back to the generic code and forces localized message matching in
  the frontend.
- The email form accepts six digits even though both delivery implementations
  generate four-digit codes.
- The provider abstraction already exposes `send_challenge`, but the three
  send-code routes call delivery utilities directly.

## Decision Log

- Decision: keep `PhoneLogin`, `EmailLogin`, and the four public `useAuth`
  methods as compatibility wrappers. Rationale: callers do not need to know
  about the shared internal implementation.
- Decision: use neutral auth i18n keys for the shared code label, placeholder,
  required message, and send action. Rationale: these strings are not
  channel-specific, while `checkYourSms` and `checkYourEmail` remain distinct.
- Decision: preserve visible channel differences through configuration.
  Rationale: SMS still needs image captcha and an editable phone field during
  cooldown; email keeps its cooldown lock and stale-code reset behavior.
- Decision: route all three challenge endpoints through auth providers.
  Rationale: this uses the existing abstraction while preserving the console
  SMS captcha bypass as provider metadata.

## Outcomes & Retrospective

Email and SMS now share one internal frontend form, auth-hook coordinator,
backend login coordinator, and verification-challenge preparation path while
preserving their public contracts and channel-specific behavior. SMS rate
limiting now uses stable code 1012, and both forms consume a four-digit code.

Focused frontend verification passed with 21 tests. Focused backend user,
captcha, login-route, SMTP, and shared challenge verification passed with 36
tests. Frontend type-check and lint passed; lint reported only existing
repository warnings. Translation parity/usage, repository harness,
architecture boundaries, Ruff, and the full pre-commit suite passed. No real
production SMTP delivery was attempted.

## Context and Orientation

Frontend auth components live in `src/web/src/components/auth/`. Shared auth
request orchestration lives in `src/web/src/hooks/useAuth.ts`, and public API
paths live in `src/web/src/api/api.ts`. Shared UI translations live in the five
locale files under `src/i18n/*/modules/auth.json`; the generated TypeScript key
union is `src/web/src/types/i18n-keys.d.ts`.

Backend user routes live in `src/api/flaskr/route/user.py`. Provider contracts
and phone/email providers live under `src/api/flaskr/service/user/auth/`.
Verification-code delivery and persistence currently live in
`src/api/flaskr/service/user/utils.py`. Focused tests are under
`src/api/tests/service/user/` and beside the frontend components and hook.

## Plan of Work

Create an internal `VerificationCodeLogin` component parameterized by contact
mode. Move shared form state, four-digit normalization, terms confirmation,
timer lifecycle, request state, and common markup into it. Keep the public
phone and email components as thin wrappers. Refactor `useAuth` to run SMS and
email logins through one private coordinator and challenge sends through one
private sender with stable `{ rateLimited: boolean }` results.

On the backend, add a typed route configuration for verification-code login and
use one handler for both public routes. Dispatch send-code requests through
`AuthProvider.send_challenge`. Extract the shared IP limit, identifier cooldown,
code generation, Redis storage, and verification-record creation from the two
delivery utilities while leaving captcha validation and delivery transport in
their respective channel functions.

Update translations and generated key types, then update tests to exercise
shared and channel-specific behavior. Keep analytics event names and payloads
unchanged.

## Concrete Steps

1. Add the active ExecPlan and shared frontend component.
2. Convert phone and email components to thin wrappers and refactor `useAuth`.
3. Replace duplicate auth translation keys in all five locales and regenerate
   the key union.
4. Refactor route login/send handlers, providers, and challenge utilities.
5. Add or update frontend and backend focused tests.
6. Run focused tests, type-check, lint, translation checks, backend suites,
   repository harness, architecture checks, and pre-commit.
7. Update the PR description, move this plan to completed, commit and push.
8. Follow CI and live review threads for the pushed head until terminal.

## Validation and Acceptance

- Both `/login_sms` and `/login_email` keep their existing request fields and
  response envelope, including referral/context propagation and guest-only
  identity claiming.
- SMS and email challenge routes keep their existing paths and response data;
  console SMS still bypasses image captcha.
- SMS and email rate limits return stable frontend `{ rateLimited: true }`
  results, with backend business codes 1012 and 1033 respectively.
- Both forms normalize double-pasted codes to four digits, clean timers on
  unmount, show one rate-limit toast, and preserve their visible cooldown and
  captcha differences.
- Existing login analytics produce exactly one attempt and one terminal result
  without sensitive values.
- Translation parity, usage, generated key types, frontend checks, focused
  backend tests, repository harness, architecture checks, and pre-commit pass.

## Idempotence and Recovery

All code edits are source-controlled and can be rerun safely. Challenge tests
use fake Redis, SMTP, and SMS delivery; they do not require production
credentials. If a formatter or generator changes unrelated files, inspect and
restore only those generated side effects before committing. If the remote PR
head advances, stop before pushing, fetch the contributor branch, and replay
the verified commit on the new head.

## Interfaces and Dependencies

- Public React contracts: `PhoneLoginProps` and `EmailLoginProps` remain
  unchanged.
- Public hook contracts: `loginWithSmsCode`, `loginWithEmailCode`,
  `sendSmsCode`, and `sendEmailCode` remain callable with their existing
  arguments; both send methods resolve to `{ rateLimited: boolean }`.
- HTTP contracts: `/user/send_sms_code`, `/user/console_send_sms_code`,
  `/user/send_email_code`, `/user/login_sms`, and `/user/login_email` remain
  unchanged.
- Providers: phone and email continue implementing `AuthProvider`, using
  `ChallengeRequest`, `ChallengeResponse`, and `VerificationRequest`.
- External delivery: Aliyun SMS and SMTP remain channel-specific and are mocked
  in automated tests.

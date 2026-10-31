# Require issued verification codes in normal deployments

## Purpose / Big Picture

Normal API startup must accept only actually issued verification challenges,
regardless of `ENV` or a legacy `UNIVERSAL_VERIFICATION_CODE` setting. Local
development and automated tests may explicitly select a dedicated entry and
configure a test code. This change is independent of first-administrator setup.

## Progress

- [x] 2026-10-31 22:25 CST: Verified the isolated baseline is remote main
  `ba2dcb51a6a1dcdae02c8ea6959c18245c96d886`; PR #3183 remains untouched.
- [x] 2026-10-31 22:25 CST: Reproduced 18 failing security cases on the
  unchanged runtime; 27 existing verification controls passed.
- [x] 2026-10-31 22:25 CST: Added the startup capability and dedicated entry,
  removed deployment defaults and SMS fake-success, and updated setup docs.
- [x] 2026-10-31 22:25 CST: Completed one fresh read-only review; bounded
  test values to MySQL column lengths after confirming the review finding.
- [x] 2026-10-31 22:25 CST: Passed 78 final auth/startup/SMS cases, 61 static
  packaging/harness tests, new-entry Mypy and all-files lefthook checks.
- [x] 2026-10-31 22:36 CST: Recorded the full backend attempt and its baseline
  comparison; the frozen final auth/config/startup rerun passed 1,101 cases
  with five disposable-MySQL tests skipped.
- [ ] Retry the full suite in a fresh pinned environment when package downloads
  are available; both isolated setup attempts ended in network timeouts.
- [ ] External acceptance: Docker Compose rendering, image/container startup,
  browser smoke and strict MySQL execution remain unavailable locally.


## Surprises & Discoveries

The shared consumer returns before all normal challenge checks when the legacy
setting matches. SMS issuance separately treats the setting as proof of delivery.
The config registry has no runtime default, but its nonempty example becomes an
active generated deployment setting. Tests and the runtime browser harness rely
on explicitly configured test codes. The browser UI reveals code input only after
successful delivery, so the isolated harness now replaces only the external SMS
SDK transport using one read-only mount outside `/app`; business APIs stay real.
The adapter is absent from the production image. Static packaging tests permit
only this exact mount and continue rejecting product source mounts.

The first full backend run reported 15,006 passed, 4 failed and 114 skipped.
One failure used a test function collected before its final entrypoint assertion
changed; the final focused rerun passed. The other three failures reproduce on
unchanged main with the shared older dependencies (dotenv, Pydantic AI and
LiteLLM). Two attempts to prepare a separate pinned environment ended in package-index
or wheel-metadata download timeouts; no packages were installed into the shared
environment. The frozen final auth/config/startup group passes 1,101 tests with
five disposable-MySQL tests skipped. The full-suite attempt retains its actual
15,006-pass, four-failure, 114-skip result; it is not reported as a clean run. Existing-module Mypy reports the same eight errors on
main and the patch; both new entry modules pass. Docker CLI is absent and the
browser attempt failed before startup because Playwright Chromium is absent.

## Decision Log

- Enforce permission in an application extension established by startup code,
  never in an environment-derived boolean. Keep the test code default empty.
- Ordinary `app:app`, `python app.py`, release and latest Compose remain strict.
  `development_app:app` is a deliberately selected local/test startup entry.
- A configured override never turns a failed SMS provider response into success.
- Preserve the current gthread, migration, provider, repository and UOW behavior.
- Exclude installer/admin-account schema and UI, password concurrency, Google
  authentication changes, Gunicorn watcher changes and unrelated refactoring.

## Outcomes & Retrospective

The local implementation blocks the configured-code bypass at the shared
consumer, including misleading environment labels, and preserves real challenge
state transitions. Local verification is recorded above; complete verification
remains blocked by the external runtime checks. No production state was inspected
or changed, and no push, publication, advisory update or merge is authorized.

## Context and Orientation

`src/api/flaskr/service/user/verification_codes.py` owns challenge consumption.
Email/phone login and password setup/reset all call it. `utils.py` owns issuance
and durable delivery records. `app.py` owns the application singleton and normal
startup. Docker Compose and `src/api/Dockerfile` select deployment entry points.
Configuration metadata in `flaskr/common/config.py` generates
`docker/.env.example.full`. The authentication workflow is described in
`src/api/skills/user-auth-flows/SKILL.md`.

## Plan of Work

Add failing challenge, login/password and SMS-delivery regressions first.
Gate only the existing consumer bypass on a non-environment startup capability;
leave normal challenge validation and consumption intact. Add the explicit
development entry and opt existing test/harness startup into it. Remove the
release default, regenerate the env example, and update English/Chinese setup
and upgrade instructions. Run a fresh read-only bypass/regression review once.

## Concrete Steps

Run focused pytest first with the backend virtual environment, then all user,
config and app tests and the broader offline backend suite. Run Ruff, applicable
type checks, `python scripts/check_dev_tools.py`, the generated knowledge
index/harness and architecture checks, and `lefthook run pre-commit --all-files`.
Render touched Compose files with `docker compose ... config` if available.
Run browser smoke checks when possible because the runtime harness entry moves.
Keep exact results and proof gaps in the final verification record.

## Validation and Acceptance

Demonstrate that an unissued configured code fails normal login and password
ownership checks with both production and misleading development labels. A
matching genuinely issued code must still pass once, reject expiry and replay,
and share the wrong-attempt budget. Dedicated development startup requires both
an explicit entry and a nonempty code; config or `ENV` alone is insufficient.
Failed SMS delivery must stay unsent and fail. New tests must fail on the
unchanged main runtime before becoming green with the patch.

## Idempotence and Recovery

The isolated branch can be discarded without affecting the original checkout or
PR #3183. No schema migration or production data rewrite is needed. Existing
deployments must remove the legacy setting/overlays, update to a fixed API image
and normal startup, and verify real code delivery. Preserve `SECRET_KEY`.
Do not roll back to an image that restores the bypass.

## Interfaces and Dependencies

Keep auth payloads, errors, provider interfaces and cache/database state contracts
unchanged. The only opt-in is an application startup capability plus the existing
optional test-code value. The overlap with #3183 is the universal-code guard,
configuration examples, SMS-delivery semantics and related docs/tests; remove
that duplicate scope from #3183 after the foundation lands, in its own task.
No installer functionality is imported into this fix.

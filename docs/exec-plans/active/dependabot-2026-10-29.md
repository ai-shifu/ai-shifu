# Remediate the October 29 Dependabot dependency alerts

## Purpose / Big Picture

Remove the vulnerable Authlib, dnspython and KaTeX versions reported in the
repository's current Dependabot inventory. Preserve Google OAuth, custom-domain
verification and course math rendering. Keep changes reviewable in separate
backend and frontend pull requests. Merging and deployment remain manual.

## Progress

- [x] 2026-10-29 UTC: Read all 20 open alerts and refreshed remote main.
- [x] 2026-10-29 UTC: Reused backend PR #3232, which upgrades Authlib to 1.9.1
  and dnspython to 2.9.0. CI inherits these pins from requirements.txt.
- [x] 2026-10-29 UTC: Independently traced Google OAuth, DNS verification,
  MarkdownFlow math rendering and Jest's deepmerge call site.
- [x] 2026-10-29 UTC: Backend security and existing Google/domain tests pass
  (98 tests); the complete requirements-ci.txt resolves and pip check passes.
- [x] 2026-10-29 UTC: All frontend KaTeX resolutions use 0.18.2. Both focused
  dependency tests and all 279 Jest suites / 3,520 tests pass on Node 22.23.4.
- [x] 2026-10-29 UTC: Independent candidate reviewers found no concrete
  Python or KaTeX bypass or compatibility regression.
- [x] 2026-10-29 UTC: Triaged two additional npm audit findings in Ajv and
  minimatch; no unverified version-only fix was included.
- [x] 2026-10-29 UTC: Published ready-for-review backend PR #3232 and frontend
  [PR #3239](https://github.com/ai-shifu/ai-shifu/pull/3239). Final CI acceptance
  remains part of the external gate below.
- [ ] 2026-10-29 UTC: External acceptance: a maintainer merges the reviewed PRs and verifies
  Dependabot's default-branch readback and the deployed application.
- [ ] 2026-10-29 UTC: Upstream follow-up: remediate deepmerge alert #813 once a trustworthy
  release or compatible replacement is available.

## Surprises & Discoveries

- Eighteen alerts (#795-812) are duplicate runtime/CI reports for the two Python
  packages. requirements-ci.txt includes requirements.txt; it has no separate
  vulnerable pins to update.
- MarkdownFlow UI 0.3.3 already bundles KaTeX 0.18.2, but Mermaid and other math
  dependencies leave separate vulnerable KaTeX 0.16.47 artifacts in npm's graph.
- deepmerge #813 has no patched release. Latest deepmerge 4.3.1 and Jest 30.5.2
  still retain the affected implementation. Its three lockfile entries are
  development dependencies of Jest configuration loading. The affected call
  merges preset.globals with options.globals; this repository supplies neither.
  Local configuration is the relevant input boundary, not course content.
- The initial all-dependency installation timed out fetching PyPI wheels.
  Retry with lower download concurrency and a longer network timeout.
- Main advanced to 685dffe52 during CI, upgrading Ruff to 0.17.3. Refresh the
  feature branches and verify the updated toolchain before final handoff.
- npm audit also reports Ajv GHSA-2g4f-4pwh-qvx6 and minimatch
  GHSA-23c5-xmqv-rm74 outside the initial GitHub alert list. Published versions
  identified as patched still reproduce crafted default-regex inputs in
  bounded subprocess probes. The application does not directly use these APIs;
  current consumers are build/lint/configuration tools. ESLint does not enable
  Ajv's $data option and repository glob patterns are fixed configuration.

## Decision Log

- Reuse [PR #3232](https://github.com/ai-shifu/ai-shifu/pull/3232) instead of
  duplicating the existing Python dependency update.
- Add executable library-boundary regressions plus a real OAuth2Session with
  mocked HTTP transport. Existing Google tests replace the session itself.
- Use the existing npm overrides mechanism for KaTeX 0.18.2. Preserve the
  application and upstream component versions; generate the lock with npm.
- Leave genuine deepmerge alert #813 open. An older version, incompatible npm
  alias, unmerged upstream patch, or new custom merge implementation does not
  establish a safe compatible dependency fix. Replacing the test runner is
  separate engineering work, outside these focused dependency updates.
- Leave the additional Ajv/minimatch audit findings for separate upstream
  verification. Adding an optional regular-expression engine or changing a
  version number does not demonstrate that the reported default-API trigger
  stops reproducing. Do not claim universal ReDoS prevention from these fixes.

## Outcomes & Retrospective

The Python and KaTeX candidates pass focused security and legitimate-behavior
checks. All 23 new Python tests pass on Authlib 1.9.1 / dnspython 2.9.0; the same
tests produce 19 expected security failures and four passing controls on the
original Authlib 1.6.12 / dnspython 2.7.0. The larger backend selection passes
98 tests. The final frontend graph passes 3,520 tests, including the KaTeX trust
regression and existing Mermaid/YAML dependency regression.

Initial repository gates passed and both PRs are published. The latest-main
toolchain and final remote CI are being verified. A candidate or successful
check does not close a default-branch alert. No alert has been dismissed, no
code has been merged and no deployment has been requested.

## Context and Orientation

Backend dependencies live in src/api/requirements.txt. The Google provider
imports Authlib's requests integration; application JWTs use PyJWT. Billing
custom-domain verification parses untrusted TXT/CNAME DNS replies through
dnspython. Frontend dependencies and overrides live in src/web/package.json;
package-lock.json is npm-generated. MarkdownFlow and Mermaid render math in
authoring and learner views. Jest uses deepmerge only during test setup.

## Plan of Work

First validate the backend upgrade, including forged signatures, empty HMAC
keys, DNS pointer depth and normal authentication/domain behavior. Then ensure
every frontend math dependency resolves the fixed KaTeX and validate both trust
restrictions and ordinary math output. Review the candidate independently and
run repository gates. Publish separate PRs and read back their checks.

## Concrete Steps

1. Read live alerts with `gh api repos/ai-shifu/ai-shifu/dependabot/alerts`.
2. Inspect PR #3232 and add focused backend regressions on its branch.
3. Install requirements-ci.txt and run the security, Google and domain tests.
4. Add the KaTeX override, run npm install, then verify with a clean npm ci.
5. Run focused frontend regressions and the complete Jest suite.
6. Run the pinned toolchain doctor, repository harness and lefthook gates.
7. Push only feature branches and inspect the resulting PR heads and CI.

## Validation and Acceptance

- Empty HMAC keys and signature-free JSON JWS objects must be rejected.
- DNS compression chains exceeding 16 pointers must be rejected; valid
  compressed names must still parse.
- Google token exchange and bearer authentication must work using the real
  requests integration with a mocked transport.
- Every KaTeX instance must reject inherited trust while preserving ordinary
  math and explicitly trusted safe links.
- Runtime and CI dependency resolution must exclude all fixed vulnerable
  versions; npm's remaining deepmerge advisory must be reported explicitly.
- Applicable repository and PR checks must finish successfully before calling
  the corresponding candidate verified. Production acceptance requires the
  maintainer's merge, deployment and subsequent readback.

## Idempotence and Recovery

Reuse the existing backend PR. Keep frontend changes on a branch from main.
Rerun npm install to regenerate the lock; never edit it by hand. Retry failed
downloads without changing dependency pins. Revert the relevant focused commit
if compatibility fails. Never merge main or dismiss alerts automatically.

## Interfaces and Dependencies

The fixes change third-party dependency versions, not application interfaces.
Python 3.11 satisfies both upgraded packages. Authlib adds joserfc; the resolver
must include it. KaTeX 0.18.2 matches the version already used by MarkdownFlow.
No new analytics event is required because no user interaction is introduced.

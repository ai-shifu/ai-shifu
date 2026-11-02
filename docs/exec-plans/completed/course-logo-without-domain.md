# Course Logos Without Custom Domains

## Purpose / Big Picture

Allow an eligible course owner's configured logos to appear on their learner
courses when the account has no configured custom domain. Preserve the
domain-based site identity and official backend branding introduced in PR 3307.
The canonical contract is in
`docs/design-docs/creator-brand-domain-payments.md`.

## Progress

- [x] 2026-11-02 11:14 UTC: Confirmed PR 3307 merged and created a new branch
  from the current main commit; inspected billing, domain removal, and frontend
  initialization paths.
- [x] 2026-11-02 11:18 UTC: Defined logo-only eligibility and preserved effective
  customer-domain precedence and validated course ownership.
- [x] 2026-11-02 11:26 UTC: Implemented context-aware frontend refresh and
  verified 321 backend tests and 193 frontend tests; independent backend and
  frontend reviews passed.
- [x] 2026-11-02 11:29 UTC: Passed the repository-wide pre-commit gate and
  prepared the completed change for a ready pull request.
- [x] 2026-11-02: Addressed the course OAuth review with context/generation
  readiness and guarded navigation; 103 focused frontend tests passed.

## Surprises & Discoveries

- Domain removal retains a disabled row. Counting all historical rows as bound
  would prevent an account from ever regaining the domainless course behavior.
- The browser previously loaded runtime configuration once for the entire SPA.
  Course-dependent logos require refreshing when the course context changes.
- Runtime config also contains payment/login settings. Presentation changes
  must keep the validated business owner and reject stale response writes.
- A failed logo-eligibility query must decline the visual fallback while
  preserving the already-resolved commercial context.
- Review found that global bootstrap readiness alone let course OAuth start
  with another context's App ID before the new course response arrived.

## Decision Log

- Effective customer domains keep highest priority and the full site brand.
- Only a validated learner course context can select the fallback; a signed-in
  account or legacy `creator_bid` parameter cannot select it.
- The fallback supplies only wide/square logos. Favicon, home/contact links,
  generated course URLs, permission checks, and billing ownership retain their
  existing contracts.
- Pending, failed, expired-entitlement, and non-TLS bindings remain configured;
  deleted or explicitly removed/disabled bindings do not.
- Matched but ineffective request hosts never use the course fallback.
- Route-context refresh is part of this feature. It must deduplicate requests
  for the same course and prevent late responses from overwriting newer context.
- Course OAuth readiness includes the route identity, current request
  generation, and successful runtime status. A failed current context releases
  preparation without authorizing with a stale App ID.
- This is a visual branding change, with no new interaction or analytics payload.

## Outcomes & Retrospective

Focused validation passed: 321 backend tests and 193 frontend tests. Ten optional
SaaS-plugin tests are skipped because the plugin is not installed locally.
TypeScript, frontend lint, Ruff, and architecture checks passed. Independent
reviews confirmed domain precedence, explicit-removal semantics, safe commercial
fallback, response ordering, transport configuration, and route deduplication.
The repository-wide pre-commit gate passed, including documentation,
architecture, translations, formatting, and lint. The completed change is ready
for PR review. No migration, environment change, deployment, or main-branch
merge is part of this task.

## Context and Orientation

`src/api/flaskr/service/billing/runtime_config.py` builds the runtime brand and
commercial context. `domains.py` owns binding resolution and domain-removal
semantics. `src/api/flaskr/route/config.py` supplies a validated course owner.
The frontend's `initialize-runtime-config.ts` loads the shared environment store
and `RuntimeConfigInitializer.tsx` mounts in the root layout.

## Plan of Work

1. Add a domain-configuration existence check that respects explicit removal.
2. Select course logos only after domain branding and eligibility are resolved.
3. Refresh the browser's runtime configuration by course identity, with safe
   deduplication and response ordering.
4. Cover eligibility, host boundaries, navigation, and request races; update the
   canonical specification and deliver a focused new PR.

## Concrete Steps

Use the existing project Python environment and frontend dependencies. Run the
runtime billing/domain tests first, then nearby route/link/customization tests.
Run focused frontend initialization/component tests and TypeScript checking.
Run `python scripts/check_dev_tools.py` and the repository-wide pre-commit gate
before committing. Generate knowledge indexes after plan archival.

## Validation and Acceptance

- A course owned by an eligible account with saved logos and no configured
  domain uses those logos, including when an unrelated account selector exists.
- Accounts with a configured domain, absent/expired branding, missing assets,
  or no validated course context retain global logos on platform pages.
- Explicit domain removal restores fallback eligibility on platform pages;
  visits to a matched ineffective customer host still use global branding.
- Effective customer domains, course-owner mismatch rejection, generated links,
  merchant selection, and navigation destinations remain covered by regressions.
- Course A to B and course to backend transitions refresh the correct logos;
  delayed responses, failure/retry, and repeated same-course loads are safe.
- Admin-to-course and course-to-course OAuth wait for the matching runtime
  configuration; stale effects/callbacks cannot navigate with another App ID.

## Idempotence and Recovery

Runtime resolution is read-only. Rollback consists of reverting this feature
commit; no saved logos, domain bindings, or links need rewriting. Keep the PR
unmerged for user review and do not deploy without a separate request.

## Interfaces and Dependencies

Reuse existing runtime DTOs and the billing/domain helpers. The frontend retains
the public initialization entry point while accepting route context. No new
package, API field, database column, or environment variable is required.

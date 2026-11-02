# Domain-Based Site Branding

## Purpose / Big Picture

Use the effective request domain to select site branding in both the teacher
backend and learner pages. Official-domain visits keep the global AI-Shifu
brand even when the signed-in account or course owner has customer branding.
Course links follow the same official-versus-customer-domain rule.

## Progress

- [x] 2026-11-02: Inspected runtime configuration, authoring link generation,
  domain validation, frontend branding updates, and adjacent tests.
- [x] 2026-11-02: Separate domain-selected presentation from course/account
  entitlements and merchant selection; remove account-selected frontend branding.
- [x] 2026-11-02: Align course links, document the contract, and verify regressions.
- [x] 2026-11-02: Passed repository-wide gates and prepared the change for a
  ready pull request; implementation scope and acceptance were independently reviewed.
- [x] 2026-11-02: Addressed review findings with independent fixes for failed
  API discovery and legacy account selectors overriding validated ownership.

## Surprises & Discoveries

- Runtime config currently mixes presentation with course-owner entitlement and
  payment configuration. Changing the billing owner to change a logo would also
  change unrelated business configuration.
- Authoring links currently fall back from the official domain to the course
  owner's customer domain. Some customer-domain routes already reject courses
  belonging to another owner.
- The frontend runtime loader treated an empty dynamic API origin as missing
  configuration. Respecting that empty same-origin value is necessary to keep
  the customer's request host visible to the backend.

## Decision Log

- Both teacher and learner branding follow the effective domain. Account
  switches and course changes cannot change the site's brand.
- Keep global branding on the configured official host, even if it was
  accidentally entered as a customer binding.
- Only verified, TLS-active, still-entitled customer domains select customer
  branding or appear in generated course links.
- Brand presentation includes wide/square logos, favicon, home destination,
  and contact destination. Existing billing ownership, permissions, merchant
  selection, and OAuth/payment callback rules keep their own contracts.
- Preserve course-owner checks on customer domains, including for collaborators.
- This change adjusts existing presentation and link destinations; it adds no
  new interaction or analytics payload. Existing publish/share tracking stays
  unchanged and continues excluding URLs.

## Outcomes & Retrospective

Focused validation passed: 293 backend tests and 150 frontend tests, plus
TypeScript and frontend lint. Ten optional SaaS-plugin tests are skipped
because that plugin is not installed in this checkout. Two independent code
reviews found no in-scope defects. The full repository-wide pre-commit gate
passed using the existing project Python environment, including architecture,
documentation, translation, formatting, and lint checks. No schema or
stored-link migration is required.

Review follow-up preserves explicit empty same-origin discovery results while
using the configured backend on HTTP, JSON, network, or invalid-response
failures. Commercial runtime settings now prioritize validated domain/course
ownership over legacy explicit account selectors, including recovery when the
first host lookup fails. Production rollout remains a separate release step.

## Context and Orientation

`src/api/flaskr/service/billing/runtime_config.py` builds runtime billing DTOs.
`src/api/flaskr/route/config.py` projects them into public runtime config.
`src/api/flaskr/service/billing/domains.py` validates effective host bindings.
`src/web/src/lib/initialize-runtime-config.ts` loads the shared frontend store;
`src/web/src/app/admin/layout.tsx` currently overwrites it using the account.
`src/api/flaskr/service/shifu/route.py` builds authoring course URLs.

## Plan of Work

Resolve presentation from the actual valid host while preserving the explicit
course/account business context. Remove the frontend account override. Generate
official course links on the official entry point and exact customer-host
links on valid customer entry points. Extend regressions and the canonical
creator-brand design document.

## Concrete Steps

1. Update runtime branding selection and official-host protection.
2. Remove frontend account branding and verify account/course transitions.
3. Align the authoring URL resolver and its route tests.
4. Run focused backend/frontend tests, type/lint checks, and repository gates.
5. Commit with the repository message policy and open a non-draft PR.

## Validation and Acceptance

- A branded course or account on the official domain receives only global
  presentation, while its commercial entitlements and merchant context remain.
- A valid customer domain receives its owner's brand for all permitted users.
- Invalid, disabled, expired, and non-TLS bindings cannot select customer branding.
- Official-domain bindings cannot replace official branding.
- Course detail, save, publish, preview, copy, and share destinations remain
  consistent with the effective entry domain; cross-owner guards still reject.
- Account switches do not fetch account-selected logos; existing publish/share
  event names and privacy-safe payloads remain unchanged.

## Idempotence and Recovery

No schema migration or stored-link rewrite is required. Configuration remains
account-owned; only presentation and generated destinations change. Reverting
the implementation commit restores the prior resolution behavior.

## Interfaces and Dependencies

Keep runtime-config field names and authoring response shapes stable. Preserve
the separate billing API facade for authoring calls. Use existing domain
normalization and validation rather than constructing arbitrary request URLs.

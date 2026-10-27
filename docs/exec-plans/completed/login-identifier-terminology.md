# Separate deployment identifiers from interface selection and notification channels

## Purpose / Big Picture

Make login-related code readable without implying that deployment configuration
describes a user's actual login or chooses a universal preferred account type.
The foundation PR separates the configured identifier collection from existing
single-field UI policy. Each consumer names its value for its own responsibility,
including account lookup, table display and notification delivery. The dependent
learner activation PR consumes this interface under its own product contract;
this plan covers the shared foundation and its consumers. Neither PR is merged
into `main` as part of this task.

## Progress

- [x] 2026-10-27 09:34 UTC: Audited configuration provenance and all consumers;
  classified account identifiers separately from notification channels.
- [x] 2026-10-27 09:40 UTC: Implemented the collection and single-field policy,
  updated all consumers and preserved the existing delivery and account behavior.
- [x] 2026-10-27 09:42 UTC: Verified 26 suites / 435 tests, TypeScript, lint,
  architecture, repository harness and all-file pre-commit checks.
- [x] 2026-10-27 09:42 UTC: Independent scope review found no blockers; reviewed
  foundation acceptance and handed feature integration to dependent PR #3211.

## Surprises & Discoveries

The old resolver reads deployment configuration, not authentication history.
Google maps to an email identifier, but the historical single-field policy uses
phone for a mixed configuration whose default is Google. Empty or unrecognized
configurations also use the historical default-based fallback. These are existing
UI policies, not statements about every identifier the backend can accept.

Credit notifications previously propagated the same identifier-typed value into
account filters, managed lists, delivery controls and template API selection.
These uses need separate props even when today's deployment policy derives them
from the same configuration. Some account displays fall back to another stored
identifier and others do not; this refactor preserves those product policies.

## Decision Log

- `login-identifiers.ts` owns `LoginIdentifierType`,
  `resolveLoginIdentifierTypes` and `selectSingleLoginIdentifierType`.
- The collection resolver accepts deployment methods as an array, CSV, null or
  undefined; it normalizes case and whitespace, maps Google to email, deduplicates
  in phone/email order and returns an empty collection for unrecognized methods.
  It neither reads user state nor silently supplies a default identifier type.
- The single-field selector accepts the collection and default login method.
  It preserves the old policy: a sole configured type wins; otherwise explicit
  email selects email and every other default selects phone. Multi-type
  interfaces use the collection instead of this compatibility policy.
- Use local account roles such as `displayIdentifierType`, `accountColumnType`,
  `permissionIdentifierType` and `creatorIdentifierType`. Notification sending
  and templates use `notificationChannel` with the existing `sms | email` type.
  The notification page composes both policies and passes only required values
  to its children.
- Keep backend fields, independent contact APIs, translation keys and analytics
  event schemas unchanged. This adds no interaction path or sending capability.
  Existing learner validation errors stay account-neutral because parsing still
  accepts both identifier types independently of the prompt configuration.
- Preserve the PR stack: foundation targets `main`; learner activation targets
  the foundation branch. Update both PRs without merging either one.

## Outcomes & Retrospective

The foundation implementation and acceptance are complete. All 26 affected
Jest suites (435 tests) and the required repository gates passed. Independent
review confirmed preserved policy, payload and fallback behavior. Integration
with learner activation remains assigned to dependent PR #3211.

The earlier rename exposed a modeling issue: replacing one generic term globally cannot express different
consumer responsibilities. The collection and explicit UI policy make that
distinction inspectable at the shared boundary and at each call site.

## Context and Orientation

Deployment methods and the default method enter `useEnvStore` through runtime
configuration. The shared module is
`src/web/src/lib/login-identifiers.ts`. Its consumers span
admin courses, orders, dashboards, operations, billing and permissions.
Authentication and contact helpers also import its identifier type.
`src/web/src/app/admin/operations/credit-notifications/` contains both account
management and notification delivery. The dependent
`components/order/ImportActivationDialog.tsx` currently repeats method-to-type
mapping locally. Its product contract and feature validation are tracked by the dependent
learner activation PR #3211.

## Plan of Work

Introduce the collection and explicit single-field selection, then migrate all
foundation callers with context-specific names and props. Coordinate notification
producers and consumers in one change. Add direct configuration-policy tests and
focused notification regressions. Validate and commit the foundation, then merge
it into the dependent feature branch and reuse the collection for prompt copy.
Review and update each PR description to match its final diff.

## Concrete Steps

Search the old module, resolver, type and props. Inspect adjacent state and API
uses before editing. Format changed files and run affected Jest suites,
TypeScript and lint. Stage moved source and plan files before regenerating
knowledge indexes. Run the developer tool doctor, architecture and repository
checks and the all-file pre-commit gate. Commit on task branches and push each
branch normally. Confirm the child PR still targets the foundation branch.

## Validation and Acceptance

The shared collection matrix covers normalization, CSV and array input, Google,
duplicates, empty and unknown methods. The single-field matrix preserves sole,
mixed and empty-configuration behavior across default methods. Notification
tests prove account type and channel props remain distinct and preserve template
APIs and delivery controls. Existing permissions, billing, display, query and
learner activation regressions pass. No old preferred resolver imports remain;
no API payload, analytics schema or delivery behavior changes are introduced.

## Idempotence and Recovery

No database, dependency or persisted configuration migration is required. Revert
the foundation and its dependent feature integration together if rollback is
needed. Avoid history rewriting; retain separate reviewable PRs and preserve
their base/head relationship. Do not merge either PR into `main`.

## Interfaces and Dependencies

`LoginIdentifierType` remains `email | phone`.
`resolveLoginIdentifierTypes(methods)` returns a readonly collection of those
types. `selectSingleLoginIdentifierType(types, defaultMethod)` returns one type
solely for existing interfaces that require one. Notification channels keep the
existing `CreditNotificationRule['channel']` contract. Account-related child
props use identifier types; delivery-related props use notification channels.
The feature PR consumes the same collection and supplies its existing explicit
fallback only when the collection is empty.

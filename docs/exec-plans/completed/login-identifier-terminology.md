# Clarify login identifier terminology

## Purpose / Big Picture

Phone and email describe login identifier types, while Google and password
describe login methods. The shared type is used for authentication, account
lookup, input validation and API requests as well as presentation. Rename the
module, exported type, resolver and consumers to describe identifiers and the
policy that chooses one preferred type.
Deliver this foundation separately from the learner activation prompt change.

## Progress

- [x] 2026-10-27 05:36 UTC: Audited the resolver, its callers and forwarded props.
- [x] 2026-10-27 05:43 UTC: Completed the shared naming migration and dependent props.
- [x] 2026-10-27 05:45 UTC: Verified unchanged resolver behavior and consumer regressions;
  17 app suites, six helper/auth/permission suites and three billing/permission
  suite runs passed. Frontend lint passed with existing repository warnings.
- [x] 2026-10-27 05:47 UTC: Independent scope review found no blockers; TypeScript,
  architecture and repository checks passed. Reviewed acceptance and archived
  this execution plan before preparing the standalone PR.

- [x] 2026-10-27 07:02 UTC: Migrated to identifier types and preferred selection;
  all 25 affected suites (382 tests), TypeScript and lint passed. Verified the
  resolver body is unchanged after export-name substitution and reviewed the
  scope before archiving the revised foundation plan.

## Surprises & Discoveries

Google login corresponds to an email identifier. With both identifier types
enabled, the shared resolver selects one preferred type according to the
existing default rule.
Some notification components use `contactMode` for SMS/email delivery rather
than login display; those channel values retain their separate meaning.
Duplicate local display-mode type declarations were removed in favor of the
shared exported type, avoiding conflicting declarations after migration.

The former display-mode terminology proved too narrow for validation and
authentication consumers. The shared model now represents identifier types;
selection of a preferred type and presentation of a type collection are
separate responsibilities.

## Decision Log

- Use `resolve-preferred-login-identifier-type.ts`,
  `resolvePreferredLoginIdentifierType` and `LoginIdentifierType`.
- Keep the shared type as `phone | email` and preserve every decision branch.
  The dependent learner activation PR uses a `loginIdentifierTypes` collection;
  a collection containing both types does not introduce a third identifier type.
- Update selected-identifier variables and forwarded props together. Preserve
  backend fields, notification channel values, independent contact-management
  APIs, translations and analytics contracts.
- Remove the old module and exports after migrating all repository consumers;
  this internal frontend module is not an independently published package.

## Outcomes & Retrospective

The shared module, function, type and consumer names now distinguish login
identifier types from login methods. Notification channels remain a separate
concept. The resolver body is identical after exported-name substitution, and affected UI regressions
pass. The learner activation prompt commit remains on its feature branch for
the separate dependent PR.

## Context and Orientation

The original helper is `src/web/src/lib/resolve-contact-mode.ts`. Consumers span
admin courses, orders, dashboards, operations, billing, verification-code login,
permission parsing and account identifier validation. Credit notification props
form a transitive consumer chain and must be coordinated with their producers.

## Plan of Work

Rename the shared boundary without changing behavior. Migrate all imports,
exported type uses and display-related names, preserving the distinction between
login identifiers and notification delivery. Validate the standalone foundation,
then place the existing learner activation prompt change on top of it.

## Concrete Steps

Search for the old path, function, type and display props. Apply the naming
migration, format changed frontend files, and regenerate repository knowledge
indexes. Run affected consumer tests, TypeScript, frontend lint, architecture,
repository harness and all-file pre-commit checks.

## Validation and Acceptance

No old module/function/type imports remain. The resolver body matches the
original after substituting only the exported names. Existing phone/email,
Google, default-selection and fallback behavior remains unchanged. Affected
consumer regressions and repository checks pass on the foundation branch.

## Idempotence and Recovery

No database, dependency, persisted configuration or external API migration is
required. Revert the foundation commit together with any dependent feature
commit that imports its new module. Keep the two PRs separately reviewable.

## Interfaces and Dependencies

`LoginIdentifierType` is `email | phone`.
Consumers that resolve one preferred type use `preferredLoginIdentifierType`;
normalization and verification helpers accept an identifier type independently
of that preference policy.
`resolvePreferredLoginIdentifierType` accepts the same enabled-method array, CSV,
null or undefined input and optional default login method. Independent contact
identifier and permission helpers adopt the new imported type without renaming
their own APIs. Notification delivery continues to use the same SMS/email values.

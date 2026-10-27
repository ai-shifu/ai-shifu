---
title: Course activation import
status: implemented
owner_surface: frontend
last_reviewed: 2026-10-27
canonical: true
---

# Course activation import

Teachers can paste phone numbers and email addresses into one learner list,
with one account and an optional nickname per line. Each line starts with the
account; a space separates its optional nickname. Email matching and duplicate
checks ignore case. Invalid rows, duplicates and lists exceeding 50 entries
must be corrected before confirmation. The existing nickname parsing rules
remain unchanged; this feature makes no promise to overwrite existing nicknames.

Dialog descriptions, account labels, examples and required-field messages follow
the runtime login configuration. Phone-only deployments show phone prompts;
email or Google login shows email prompts. When phone and email-based login
are both enabled, prompts show both types regardless of the default login
method. If no phone or email-based method is configured, the dialog explicitly
applies the existing single-field fallback using the default login method. This guidance
does not change account parsing, mixed-list compatibility, request grouping or
analytics eligibility.

Invalid-row and duplicate-account errors use type-neutral account wording.
The parser accepts both identifier types regardless of the configured prompt
guidance, so an off-mode account must not be mislabeled by that guidance.

The dialog uses `resolveLoginIdentifierTypes` from `lib/login-identifiers.ts`
to derive a deduplicated `loginIdentifierTypes` collection of
`LoginIdentifierType` values from the deployment's enabled login methods. Google and email
both contribute the same `email` identifier type; phone contributes `phone`.
If the collection is empty, the dialog explicitly calls
`selectSingleLoginIdentifierType` to retain its existing prompt fallback.
The collection itself represents configuration, not the current user's login
method or a global preference. Configuration-specific translations receive
`hasPhoneIdentifier` and `hasEmailIdentifier` membership flags derived from the
collection. Showing both types is a presentation combination, not a third
identifier type. Changes to
runtime settings update the prompts without clearing the current input.

The course-card help refers to learner accounts without listing identifier
types, so it remains accurate for every login configuration. The dialog
provides the configuration-specific guidance. The course-card entry binds the
selected course and hides the redundant course field. The orders-page entry retains the published-course selector. The review
step identifies the course before the teacher confirms activation.

The existing API accepts one contact type per request. The frontend groups the
confirmed list into phone and email requests without changing the API schema.
The phone request settles before the email request starts, including when the
first request fails. This avoids deliberately overlapping activation for linked
credentials in one confirmed list; the existing backend check reports an account
that is already activated. A failed group does not block the next group.
Results are merged by the submitted account,
and every unsuccessful or unconfirmed account retains its associated reason.
A failed request must not discard the other request's confirmed successes.
Missing account results are unconfirmed failures, rather than successful imports.
The dialog keeps the merged failure list visible until the next submission or
the dialog closes. Network failures cannot prove that the server made no changes.

## Product analytics contract

Follow the [frontend analytics contract](../references/frontend-product-analytics.md).
The mixed-list path adds an asynchronous workflow with two possible requests.
There is no existing frontend activation event family to extend.

- Business question: do teachers complete learner activation with mixed account
  lists, and are partial or unconfirmed outcomes more common than for one type?
- Metrics: weekly confirmed-import attempt counts and terminal outcome counts,
  grouped by surface and contact mode; confirmed success and unconfirmed/failed
  account counts describe the batch outcome. No form-exposure denominator is
  collected, so this is not a form conversion rate.
- Events: `creator_course_activation_attempt` and
  `creator_course_activation_result`.
- Actor and eligible population: authorized teachers confirming activation from
  the course list or orders page, for a published course. Exclude validation
  errors, opening the review step, returning to edit, missing courses, concurrent
  resubmission, learner/preview surfaces and shared-policy excluded accounts.
- Trigger: after final confirmation and the in-flight guard, emit one attempt
  immediately before the existing API calls. Emit one result after all contact
  groups settle and each submitted account has a confirmed or failed/unconfirmed
  outcome. A partial result is not total failure.
- Count unit and deduplication: one deliberate confirmed submission. A ref blocks
  re-entry until all requests settle; one attempt and one terminal result are
  emitted for that accepted submission. Later deliberate retries count again.
- Correlation: surface, contact mode and requested count support aggregate
  analysis; there is no attempt ID or exact row-level join. Shared identity is
  sufficient for distinct teacher counts. Do not add contact or course data.
- Consumer: the product owner reviews weekly aggregate completion and partial
  outcomes in Umami. No checked-in dashboard or query currently consumes this
  additive family. Historical activation activity has no equivalent signal.
- Failure isolation: call `useTracking` without awaiting delivery. Synchronous
  throws, rejected promises or unavailable analytics must not block requests,
  merge handling, failure details, success feedback or dialog dismissal.
- Verification: component tests cover both individual account types and a mixed
  list, type grouping, combined limits, duplicate email case, bound-course entry,
  independent request failures, partial/missing responses, exact event payloads,
  prohibited fields, trigger timing, re-entry and tracking failure isolation.

| Field              | Events | Type    | Allowed values                                                 | Privacy class | Why required                                    |
| ------------------ | ------ | ------- | -------------------------------------------------------------- | ------------- | ----------------------------------------------- |
| `surface`          | Both   | string  | `admin_course_list`, `admin_orders`                            | Non-personal  | Separates bound and selectable course entries   |
| `contact_mode`     | Both   | string  | `phone`, `email`, `mixed`                                      | Non-personal  | Compares account input modes                    |
| `requested_count`  | Both   | integer | 1 through 50                                                   | Non-personal  | Defines the batch size                          |
| `outcome`          | Result | string  | `success`, `partial`, `failed`                                 | Non-personal  | Describes confirmed client completion           |
| `success_count`    | Result | integer | 0 through 50                                                   | Non-personal  | Counts confirmed successful account activations |
| `failed_count`     | Result | integer | 0 through 50                                                   | Non-personal  | Counts rejected or unconfirmed accounts         |
| `failure_category` | Result | string  | `none`, `item_failed`, `request_failed`, `incomplete_response` | Non-personal  | Distinguishes bounded failure classes           |

Result counts sum to `requested_count`. `success` requires every account to have
a success response; `partial` requires both successful and unsuccessful or
unconfirmed accounts; `failed` has no confirmed successes. Failure categories
prefer `request_failed` over `incomplete_response` over `item_failed` if several
occur in one submission. A rejected request's accounts are unconfirmed: the
event is a client workflow outcome and is never a billing or entitlement ledger.

Payloads contain only the fields above. Never include account identifiers,
nicknames, course IDs or titles, raw input lines, coupon codes, URLs, backend
messages or exception text. The shared identity and exclusion policy remain
unchanged. No analytics event is used to decide whether learning access exists.

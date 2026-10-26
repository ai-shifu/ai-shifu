---
title: First-run administrator setup
status: implemented
owner_surface: frontend-backend
last_reviewed: 2026-10-26
canonical: true
---

# First-run administrator setup

A self-hosted deployment owner can initialize a local administrator without SMS,
SMTP or OAuth. The owner retrieves a short-lived, installation-scoped code from
the server console and supplies it in the Web setup form with a phone/email
login identifier and password. A direct interactive console path uses the same
domain service.
These are new capabilities; ordinary first public registration is not authority
to administer a newly managed installation.

## User journey

The uninitialized administrator entry leads to `/setup`. The owner obtains a
code for the exact local or HTTPS origin, enters a phone number or email address
and a password, and enters the administrator area with creator and demo
permissions.
Setup creates an ordinary account and a standard `password` credential, without
sending a contact verification message. The entered contact is not marked as
verified. Existing identifiers cannot be overwritten or promoted by setup.
While initialization is pending, ordinary phone/email and Google contact-account
creation coordinate with the same installation transaction. If ordinary account
creation wins, setup rejects its identifier; if setup wins, contact login reuses
the newly created account. Completed installations avoid the pending setup lock.
After completion, `/admin-login` uses the existing password provider and requires
the authenticated account's administrator role, even when learner password
login is disabled. Existing
phone/email/OAuth administrators retain their existing login route.

The administrator can also use the normal learner login and learning paths.
Earlier preview accounts with standalone usernames retain a narrow, persisted
alias reader and the compatibility `has_local_password` session marker after
their credentials migrate to `password`. A role or client-supplied marker never
authenticates a user. Neither this compatibility behavior nor ordinary password
login proves contact ownership, grants a purchase or bypasses payment gates.

The code is short lived, single use and bound to the installation's persistent
state and selected browser origin. It cannot authenticate an arbitrary account
or reset passwords. Completed setup remains closed after service restart, cache
loss or user deletion. Existing database upgrades default to closed legacy state.

Server-console password recovery remains available without external delivery
and revokes old sessions. If contact verification is configured later, ordinary
verification-code login and password recovery refer to the same phone/email
account, including its administrator role. Owners must use a contact they control.
Password login also resolves the identifier stored in a usable password
credential, independently of later changes to the canonical contact. Both
password entrypoints and the token-issuance recheck use the same resolution;
conflicting identifiers across accounts are rejected rather than guessed.
Console recovery retains that password login path. Ordinary OTP and recovery
continue to follow the current canonical or bound phone/email contact; a
password-only identifier does not itself create a verified contact binding.
Google email-based account association likewise requires a verified email claim;
an unverified profile with an unrelated Google subject cannot claim an existing
account merely by returning the same email address. Previously bound Google
subjects retain their supported login path.
Remote browser setup requires HTTPS; loopback/SSH-forwarded use and direct
console initialization provide local alternatives. Setup secrets are never URL
parameters and sensitive HTTP bodies are excluded from logs and caches.

## HTTP contract

- `GET /api/installation/status`: standard envelope with `setup_required` and
  `local_admin_login_enabled` booleans, no account or code metadata.
- `POST /api/installation/initialize`: `setup_token`, `identifier`, `password`,
  optional `language`; returns the existing `UserToken` data on success.
- `POST /api/installation/login`: `identifier`, `password`, optional `language`;
  returns the existing `UserToken` data on success.

The browser confirms the password before submission. New local identifiers must
be email addresses (trimmed, lowercased, at most 254 characters) or mainland-China
phone numbers (11 ASCII digits beginning with `1`, with optional `+86` normalized
away). Existing shared format validators apply; dots and email plus-tags are not
collapsed. Both types are accepted independently of learner provider switches.
Passwords follow the existing strength policy and supported bcrypt input limit.

The normal account identity is the normalized contact, and the existing
`password` provider owns password verification, rate limiting and token evidence.
An installation binding records provisioning provenance and supports console
recovery; it does not define a second password provider or contact namespace.
The password credential records `contact_verification: unverified`; no verified
phone/email credential is fabricated. Normal account contact fields may expose
the identifier under the existing DTO contract, but setup does not use it as a
nickname or include it in analytics. Installation authorization, rather than
contact ownership, permits the initial credential write. Ordinary public
set-password and reset-password endpoints retain their verification-code checks.
The server's `has_password` boolean reports a usable standard password
credential, independently of administrator roles or learner login switches. The
account menu uses it for the existing old-password/new-password change flow,
without requiring a messaging service. `has_local_password` remains only as an
earlier-preview contactless-session compatibility field.

New initialization accepts no standalone username. Existing preview username
bindings are preserved by a forward migration as legacy identities; login and
console recovery accept those existing names, without permitting new ones. A
legacy `username` login payload remains a compatibility read only. A forward
data migration preserves existing credential hashes, account IDs and roles
while converting preview credentials to `password`. Contact/account collisions
or inconsistent bindings stop migration before any account conversion; operators
must resolve them in a controlled maintenance process without automatic merging.
Run the conversion while API and worker account writes are stopped. The data
migration does not provide online cross-table uniqueness. Its downgrade refuses
while any installation account binding exists; retain compatible application
code or restore a reviewed pre-upgrade backup rather than reversing a live
account's authentication namespace.

If initialization committed but session delivery failed, the UI offers local
administrator login; it does not instruct the owner to initialize again.

## Analytics contract

Business question: where does the first-run/local-admin sign-in funnel fail,
and can a new self-hosted instance reach its administrator area without external
identity configuration? Consumers are the installation funnel and support
readout; events are not an audit or authorization source of truth.

The additive family uses the shared best-effort tracking path:

| Event | Trigger | Allowlisted payload |
| --- | --- | --- |
| `installation_auth_exposure` | Once per mounted, resolved available login/setup form, or per password-change modal open | `surface`: `setup`, `local_login` or `local_password_change` |
| `installation_auth_attempt` | Validation passes and one async submit is accepted | `surface` |
| `installation_auth_result` | At most once per accepted attempt after API/session handling | `surface`, `outcome`: `success` or `failed`, `failure_category`: `none`, `credentials_rejected`, `transport_or_service`, `session_unavailable` |

Setup/login population includes guests and existing authenticated visitors who
reach an available form over HTTPS or loopback. Closed/unavailable setup,
status failures and insecure public HTTP do not expose an eligible form. No
course-preview setup/login form is provided. Password-change population is an
authenticated account with a usable password credential, including ordinary
accounts and installation administrators; it remains eligible
while viewing a course preview because account security is a real global
operation. Re-renders do not duplicate an
exposure, and double clicks do not create overlapping attempts. Tracking throws
or unavailable tracking must not change the operation, loading state or outcome.
Session-store failure after an API commit is `session_unavailable`, distinct from
credential rejection. The consumer computes an aggregate weekly terminal-success
to attempt ratio by surface; it does not perform a per-person event join.

Payloads contain no login identifier, username, password, setup code, contact,
raw error, account profile, URL, query, referrer or free-form content. Existing pageview handling
must never receive setup codes because codes are kept out of URLs. No event is
used to decide whether initialization has completed.

The phone/email identifier form uses the existing installation exposure,
attempt and result events with the same triggers, deduplication and payload
allowlists. No identifier or contact-type field is added. Historical username
and current contact-identifier forms measure the same initialization/login
funnel; these events cannot measure contact verification or infer contact type.
The existing `local_password_change` surface value is retained for analytics
consumer compatibility as password change now uses the standard password fact;
it no longer implies a separate credential provider. Earlier funnel comparisons
must account for the expanded eligible password-change population.

## Compatibility and rollout

Existing ordinary credentials, roles and demo ownership are preserved during upgrade.
New bootstrap state is persisted in SQL with migration provenance; zero users is
not a signal to open setup. A rollout can disable the Web surface while retaining
standard password login and console recovery. Downgrades must preserve a reader for
installation accounts rather than clearing completion state or restoring a universal
verification code.

Schema downgrade must refuse to remove the local-account mapping while local
bindings exist, including soft-deleted bindings. A code rollback that retains
the supported local-account reader and recovery command is distinct from
dropping the schema that makes those accounts resolvable.

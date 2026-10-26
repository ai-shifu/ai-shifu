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
The contact is an unverified local identifier; setup does not send a verification
message, bind a contact credential or claim an existing contact account.
After completion, `/admin-login` provides local password login even when learner
password login is disabled. Existing
phone/email/OAuth administrators retain their existing login route.

A repository-resolved, verified local password identity also satisfies learner
trial-entry and login-interaction gates. These gates use the same persisted
identity fact as the public local-password marker, rather than inferring login
from a username or administrator role. This does not verify contact ownership,
grant a purchase, or bypass payment gates. Temporary identities and unverified
local credentials do not satisfy the local-identity branch of login checks;
existing phone/email behavior remains unchanged.

The code is short lived, single use and bound to the installation's persistent
state and selected browser origin. It cannot authenticate an arbitrary account
or reset passwords. Completed setup remains closed after service restart, cache
loss or user deletion. Existing database upgrades default to closed legacy state.

Local password recovery is a server-console action that revokes old sessions.
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

The local account binding and `local_password` credential own the identifier.
The user's internal identity remains `local:<business ID>`; the identifier is not
copied to public contact fields, the display name or ordinary phone/email
credentials. A verified password credential establishes local authentication,
not contact ownership. An independently verified learner with the same contact
is a separate account: ordinary contact login or password reset must not discover,
merge with or recover the local administrator. Local recovery stays console-only.
New initialization accepts no standalone username. Existing preview username
bindings are preserved by a forward migration as legacy identities; login and
console recovery accept those existing names, without permitting new ones. A
legacy `username` login payload remains a compatibility read only. Downgrade
must refuse to strand newly created phone/email local accounts.

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
authenticated account with a verified local credential; it remains eligible
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

## Compatibility and rollout

Existing credentials, roles and demo ownership are preserved during upgrade.
New bootstrap state is persisted in SQL with migration provenance; zero users is
not a signal to open setup. A rollout can disable the Web surface while retaining
local password login and console recovery. Downgrades must preserve a reader for
local credentials rather than clearing completion state or restoring a universal
verification code.

Schema downgrade must refuse to remove the local-account mapping while local
bindings exist, including soft-deleted bindings. A code rollback that retains
the supported local-account reader and recovery command is distinct from
dropping the schema that makes those accounts resolvable.

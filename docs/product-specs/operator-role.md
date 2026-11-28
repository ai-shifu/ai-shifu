---
title: Operator Role Design
status: implemented
owner_surface: shared
last_reviewed: 2026-11-24
canonical: true
---

# Operator Role Design

## Context

Before the operator role, the account-level authorization model exposed one
durable role flag, `is_creator`. Creator access is used for authoring surfaces, creator
orders, and several admin-facing entry points. Course ownership and shared
course permissions are handled separately through `created_user_bid` and
`AiCourseAuth`.

The separate operator role preserves existing creator behavior. Because this repository is open source and commonly
self-hosted, a fresh deployment must get an operator without manual database
edits. Being the first account to sign in is not proof of owning the
deployment, so the operator comes from an explicit bootstrap account instead.

## Goals

- Add a durable account-level `operator` role without replacing `creator`.
- Preserve existing creator logic while making authoring shared permissions
  grant the account-level creator capability they require.
- Ensure a deployment without any operator gets a bootstrap `admin` account
  that is both a creator and an operator.
- Surface the new role in backend DTOs and frontend user state so future
  operator-specific UI can rely on it.

## Non-Goals

- Full RBAC redesign is out of scope for this change.
- This change does not alter course owner semantics.
- We will not automatically promote every `/admin` login to operator.
- Existing creator-only routes stay as they are unless a
  route is explicitly meant for operator access.

## Authorization Model

### Account-level flags

- `state`: account lifecycle state (unregistered, registered, trial, paid)
- `is_creator`: creator capability flag
- `is_operator`: platform operations capability flag

### Course-level permissions

- Course owner: `created_user_bid`
- Shared permissions: `AiCourseAuth.auth_type` mapped to `view`, `edit`,
  `publish`

### Role semantics

- `is_creator`: authoring capability for the user's own course surfaces
- `is_operator`: platform operations capability for operator-specific admin
  surfaces
- course owner/shared `view` permissions: independent from account roles
- shared `edit` / `publish` permissions: authoring collaboration permissions
  that grant `is_creator` if the target account is not already a creator

## Bootstrap Rules

### Bootstrap admin account

Sign-in never grants `is_operator`, including to the first verified account of
a fresh deployment. An open instance could otherwise be taken over by whoever
signs in before its owner.

`flask console bootstrap_admin` runs on every API container start. When no
active account has `is_operator`, it creates the `admin` username account with
a random password, or with `BOOTSTRAP_ADMIN_PASSWORD` when an automated
environment sets it, and grants:

- `is_creator = true`, running the creator-grant post-auth extensions
- `is_operator = true`
- ownership of the bundled demo course when the deployment holds exactly one
  course, counting published and draft records together, and every record of
  it is still owned by the demo importer

A generated password is printed once to the command output (the container
log), never to application logs; a configured password is never printed. When
an operator already exists, or the `admin` username is taken, the command does
nothing. The pinned, latest, development and runtime-harness Compose stacks all
run it. The development and runtime-harness stacks enable password login
themselves. The pinned and latest stacks read `LOGIN_METHODS_ENABLED` from
`docker/.env`: the generated template enables password login, but an existing
`.env` that lists only `phone` must add `password` before `admin` can sign in.
The runtime-harness browser setup reads the generated password from the API
container log, as an operator would.

### Existing deployments upgrading later

When a deployment upgrades after this role is introduced, the migration should
backfill `is_operator` for the earliest active verified account if the instance
does not already have any operator. This preserves the self-hosted bootstrap
behavior without broadening operator access to every existing creator.

### Admin login context

Keep the existing creator auto-grant flow for explicit admin login context as
is. Do not extend that automatic flow to `is_operator`, because doing so would
make operator access too broad for self-hosted deployments.

### Shared permission creator grants

Sharing a course with `view` permission remains a course-level permission only.
Sharing with `edit` or `publish` grants authoring capability, so the target user
is promoted to creator and the creator-grant post-auth extensions run after the
permission transaction commits. The billing trial hook is idempotent and skips
users who already have an active paid plan, trial subscription, trial order, or
legacy trial grant.

Historical repair is explicit. Use
`flask console billing backfill-authoring-permission-creators` for users who
already have authoring shared permissions but missed the role or trial grant,
and use `flask console billing backfill-trial-plans --all` for existing
creators who only missed the trial plan. Deployments must not run either
backfill automatically at startup.

### Manual follow-up

This implementation only prepares the durable flag and bootstrap behavior. A
future follow-up may add explicit operator-grant commands or UI management
surfaces.

## Backend Changes

- Add `is_operator` to `user_users` and create a new Alembic migration.
- Extend `UserAggregate` to carry `is_operator`.
- Extend DTO serialization so `/user/info` and login responses expose
  `is_operator`.
- Extend `mark_user_roles(...)` so it can persist both `is_creator` and
  `is_operator`.
- Grant both roles only through `flask console bootstrap_admin`
  (`service/user/admin_bootstrap.py`); phone, email and Google sign-in never
  grant `is_operator`.

## Frontend Changes

- Extend frontend `UserInfo` typing to include `is_operator`.
- Preserve the existing login-state logic.
- Allow future UI to read `is_operator` from the same user payload already used
  for `is_creator`.

## Compatibility

- Creator checks continue to work because `is_creator` stays intact.
- Course owner and shared permission checks stay unchanged.
- `/admin` creator flows continue to function as before.
- New operator behavior is additive and low-risk.

## Verification

The admin bootstrap is in `service/user/admin_bootstrap.py`.
`test_admin_bootstrap.py` covers account creation, skips, demo course
assignment and rollback, and the sign-in tests check that the first account
gets no roles. `test_repository_boundaries.py` covers durable role updates.

- Backend tests for DTO serialization and the admin bootstrap role grants.
- Frontend type check to ensure the new field does not break user state
  consumers.

---
title: Operator Role Design
status: implemented
owner_surface: shared
last_reviewed: 2026-04-17
canonical: true
---

# Operator Role Design

## Context

The current account-level authorization model exposes a single durable role
flag: `is_creator`. Creator access is used for authoring surfaces, creator
orders, and several admin-facing entry points. Course ownership and shared
course permissions are handled separately through `created_user_bid` and
`AiCourseAuth`.

The project now needs a separate operator role without breaking the existing
creator behavior. Because this repository is open source and commonly
self-hosted, the first real account in a fresh deployment must automatically
receive both creator and operator access so the instance is usable without
manual database edits.

## Goals

- Add a durable account-level `operator` role without replacing `creator`.
- Preserve all existing creator logic and course-level permission behavior.
- Ensure the first verified real account in a fresh deployment becomes both a
  creator and an operator.
- Surface the new role in backend DTOs and frontend user state so future
  operator-specific UI can rely on it.

## Non-Goals

- Full RBAC redesign is out of scope for this change.
- This change does not alter course owner semantics.
- We will not automatically promote every `/admin` login to operator.
- Existing creator-only routes stay as they are unless a
  route is explicitly meant for operator access.

## Existing Model

### Account-level flags

- `state`: account lifecycle state (unregistered, registered, trial, paid)
- `is_creator`: creator capability flag

### Course-level permissions

- Course owner: `created_user_bid`
- Shared permissions: `AiCourseAuth.auth_type` mapped to `view`, `edit`,
  `publish`

## Proposed Model

### New account-level flag

Add `is_operator` to `user_users` as a durable boolean-like small integer field
mirroring the existing `is_creator` storage pattern.

### Role semantics

- `is_creator`: authoring capability for the user's own course surfaces
- `is_operator`: platform operations capability for operator-specific admin
  surfaces
- course owner/shared permissions: unchanged and still independent from account
  roles

## Bootstrap Rules

### First verified account

When the first verified real account is detected in a fresh deployment, grant:

- `is_creator = true`
- `is_operator = true`

This extends the current bootstrap path that already grants creator access to
the first verified account.

### Existing deployments upgrading later

When a deployment upgrades after this role is introduced, the migration should
backfill `is_operator` for the earliest active verified account if the instance
does not already have any operator. This preserves the self-hosted bootstrap
behavior without broadening operator access to every existing creator.

### Admin login context

Keep the existing creator auto-grant flow for explicit admin login context as
is. Do not extend that automatic flow to `is_operator`, because doing so would
make operator access too broad for self-hosted deployments.

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
- Update the first-account bootstrap path to grant both roles.
- Keep Google OAuth bootstrap aligned with the same "verified account only"
  rule so unverified Google profiles do not consume the first-account slot.

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

- Backend tests for DTO serialization and first-account bootstrap role grants.
- Frontend type check to ensure the new field does not break user state
  consumers.

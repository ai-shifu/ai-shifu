---
title: Operator Course Creator Transfer
status: implemented
owner_surface: shared
last_reviewed: 2026-04-17
canonical: true
---

# Operator Course Creator Transfer

## Goal

Allow operators to transfer a course creator from the admin course-management
list without changing course content, course configuration, or existing shared
permissions.

## Product Rules

- Entry: `Admin -> Operations -> Course Management -> More -> Transfer Creator`
- Only operators can trigger the transfer.
- The target creator is resolved by `email` or `phone`.
- If the target user does not exist, create the user automatically.
- If the target user is newly created, or exists but is still unregistered,
  grant the two onboarding demo-course permissions using the same logic as the
  shared-permission flow.
- After transfer, the new user becomes the course creator.
- Existing shared permissions are preserved as-is.
- The previous creator does not receive any special fallback permission.
- Creator-facing ownership checks, dashboard ownership, and order ownership are
  expected to follow the new creator because they already derive from
  `created_user_bid`.

## Data Scope

Update only top-level course ownership records:

- `shifu_draft_shifus.created_user_bid`
- `shifu_published_shifus.created_user_bid`

Do not rewrite content/history provenance tables:

- `shifu_draft_outline_items`
- `shifu_published_outline_items`
- `shifu_log_draft_structs`
- `shifu_log_published_structs`
- `ai_course_auth`

## Backend Design

### Route

Add an operator-only endpoint:

- `POST /shifu/admin/operations/courses/<shifu_bid>/transfer-creator`

Request body:

```json
{
  "contact_type": "email",
  "identifier": "teacher@example.com"
}
```

Response body:

```json
{
  "shifu_bid": "course-bid",
  "previous_creator_user_bid": "old-user",
  "target_creator_user_bid": "new-user",
  "created_new_user": true,
  "granted_demo_permissions": true
}
```

### Transfer Flow

1. Require operator role.
2. Load the latest draft/published course and reject missing or builtin demo
   courses.
3. Normalize and validate `contact_type` + `identifier`.
4. Resolve the target user with `load_user_aggregate_by_identifier(...)`.
5. If not found, create with `ensure_user_for_identifier(...)`.
6. If the user is unregistered, promote to `USER_STATE_REGISTERED`.
7. Upsert the credential for the provided identifier.
8. Mark the target user as creator with `mark_user_roles(..., is_creator=True)`.
9. Update all rows for the shifu bid in `DraftShifu` and `PublishedShifu` so
   legacy creator checks do not keep matching stale draft revisions.
10. Commit the ownership update first, then clear both the shifu permission
    cache for the previous and new creator and the cached shifu-creator
    mapping used by request context hydration.

### Reuse

Reuse the shared-permission and activation-order helpers for:

- contact normalization and validation
- user lookup / auto-create
- credential upsert
- unregistered-user promotion
- demo-course permission grant

## Frontend Design

### UX

- Replace the current placeholder action with a real dialog.
- Show course id, course name, current creator, target contact type, and target
  identifier input.
- Reuse the existing email/phone validation pattern already used by the shifu
  permission dialog.
- Confirm copy should explicitly state that content, configuration, and shared
  permissions are unchanged.

### Frontend Wiring

- Add one new API entry in `src/cook-web/src/api/api.ts`.
- Keep the implementation inside `src/app/admin/operations/page.tsx` for the
  first version; extract later only if the dialog grows.
- Refresh the current course list after success.

## Verification

- Backend tests for:
  - transfer to an existing user
  - transfer to a new user
  - transfer to an unregistered user
  - demo-course permission grant for new/unregistered targets
  - shared permissions remain unchanged
  - old owner loses creator-only ownership checks
- Frontend tests for:
  - opening the dialog
  - validation
  - successful submit refresh
  - failure handling

## Follow-up Safeguards

- Operator course-list `updated_at` filtering must match the same aggregated
  latest-activity timestamp shown in the table, including outline activity.
- Course activity aggregation should query only the latest outline row per
  course so the operator list does not scale linearly with all outline
  history rows.

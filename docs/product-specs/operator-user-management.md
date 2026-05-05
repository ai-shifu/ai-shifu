---
title: Operator User Management
status: implemented
owner_surface: shared
last_reviewed: 2026-04-17
canonical: true
---

# Operator User Management

## Context

Operators already have a course management surface under `Admin -> Operations`. This task adds a sibling user management page that lists all active users with practical search filters for operations workflows.

## Goals

- Add `User Management` under the existing `Operations` submenu.
- Keep the page layout and interaction style aligned with the existing operator course management page.
- Expose a backend operator-only list API for user records.
- Expose a backend operator-only detail API for a single user record.
- Support the following search filters:
  - user ID
  - identifier (mobile, email, or user ID keyword depending on site mode)
  - nickname
  - user status
  - user role
  - created time range
- Show the following list columns:
  - user ID
  - mobile
  - nickname
  - user status
  - user role
  - login methods
  - registration source
  - total paid amount
  - last login time
  - last learning time
  - learning courses
  - created courses
  - created time
  - updated time
- Provide a separate user detail page with:
  - basic info
  - overview metrics
  - learning course list
  - created course list

## Data Model Notes

Primary source tables:

- `user_users`
  - `user_bid`
  - `user_identify`
  - `nickname`
  - `language`
  - `state`
  - `is_creator`
  - `is_operator`
  - `deleted`
  - `created_at`
  - `updated_at`
- `user_auth_credentials`
  - `provider_name`
  - `identifier`
  - `state`
  - `deleted`

## Backend Plan

- Keep operator admin endpoints grouped under the existing `/api/shifu/admin/operations/...` namespace for consistency with course management.
- Add a new list endpoint:
  - `GET /api/shifu/admin/operations/users`
- Add a new detail endpoint:
  - `GET /api/shifu/admin/operations/users/{user_bid}/detail`
- Implement the query in `src/api/flaskr/service/shifu/admin.py` to reuse the existing operator permission guard style.
- Default behavior:
  - only include `deleted = 0` users
  - paginate via `PageNationDTO`
  - sort by `created_at desc`, then `id desc`
- Filter behavior:
  - `user_bid`: exact match
  - `identifier`: partial match against resolved phone/email/user ID fields
  - `nickname`: partial match
  - `user_status`: exact match on canonical state value
  - `user_role`: one of `regular`, `creator`, `learner`, `operator`
  - `start_time` / `end_time`: created time range
- Response item should contain raw, UI-friendly values rather than already translated labels so the frontend can own display copy.

## Frontend Plan

- Add a new route: `src/cook-web/src/app/admin/operations/users/page.tsx`
- Add a user detail route: `src/cook-web/src/app/admin/operations/users/[user_bid]/page.tsx`
- Add a small adjacent type file for payload shapes.
- Reuse the same page composition patterns as the operator course page:
  - search card
  - table card
  - pagination
  - error/loading/empty states
  - operator access guard
- Add the submenu entry under `Operations`.
- Use a dedicated i18n namespace `module.operationsUser`.
- Render course-list columns as compact summaries in-table and show the full
  course list in a dialog to keep the main table readable.

## Role Display Rules

To keep the page simple and the column singular, display one resolved role label:

- `operator` when `is_operator = 1`
- else `creator` when `is_creator = 1`
- else `learner` when the user has learning, purchase, or permission records
- else `regular`

Filter semantics follow the same resolved role rules.

## Login Methods Display Rules

- Use unique provider names from `user_auth_credentials`.
- If credentials are absent, infer a fallback login method from `user_identify`:
  - digits only -> `phone`
  - contains `@` -> `email`
- Return a string array so the frontend can render localized joined labels.

## Verification Plan

- Backend:
  - focused pytest for operator user listing query and route permission/filter behavior
- Frontend:
  - focused page test for list rendering, filters, and operator redirect
  - focused detail page test for user detail rendering and course list interactions
  - existing admin menu/layout test update for the new submenu entry
- Broad checks after implementation:
  - `cd src/api && pytest -q`
  - `cd src/api && pytest tests/service/shifu/test_admin_users.py -q`
  - `cd src/cook-web && npm run test -- src/app/admin/operations/users/page.test.tsx src/app/admin/layout.test.tsx`
  - `cd src/cook-web && npm run type-check && npm run lint`

---
title: Operator Course Users Section
status: implemented
owner_surface: frontend
last_reviewed: 2026-11-09
canonical: true
---

## Operator Course Users Section

### Goal

Add an operator-facing user data section to the course detail page under `运营 -> 课程管理 -> 课程详情` so operators can inspect course-related users without leaving the course context.

### Scope

- Keep the existing course detail route at `src/web/src/app/admin/operations/[shifu_bid]/page.tsx`
- Add a dedicated backend API under the shifu admin surface for course-related users
- Reuse existing user, course-permission, order, and learning records; do not add new tables in the first version
- Keep the UI style aligned with the existing operator course detail and course list pages

### User Range

The list should include the union of users who are related to the current course via:

- active course permissions (`ai_course_auth`)
- successful course orders, including zero-paid redemptions
- non-reset learning progress records
- the current course creator

### Filters

First version filters:

- `keyword`: fuzzy match against user bid, phone, email, nickname
- `user_role`: all / operator / creator / student / normal
- `learning_status`: all / not_started / learning / completed
- `payment_status`: all / paid / unpaid
- `page`
- `page_size`

### List Fields

The operator course user list should show:

- user ID
- phone / email
- nickname
- user role
- learning progress
- learning status
- paid flag
- total paid amount (course-scoped)
- last learning time
- joined course time
- last login time

### Data Contract

Recommended response payload:

- paginated response
- each item includes:
  - `user_bid`
  - `mobile`
  - `email`
  - `nickname`
  - `user_role`
  - `learned_lesson_count`
  - `total_lesson_count`
  - `learning_status`
  - `is_paid`
  - `total_paid_amount`
  - `last_learning_at`
  - `joined_at`
  - `last_login_at`

### Backend Notes

- Reuse the same course visibility resolution as the existing operator course detail page
- Reuse the current outline source (latest draft when present, otherwise published) to compute course lesson totals
- Treat learning progress as distinct visible lesson records with non-reset progress entries
- Derive learning status from learned lesson count vs total lesson count
- Use `user_token.created` as the current best available login timestamp source
- Derive `joined_at` from the earliest applicable successful order, active
  course permission, or learning progress. The current creator's course
  creation timestamp also participates.

### Frontend Notes

- Add explicit search and reset buttons in the user filter area
- Keep the user section as a regular bottom card on the course detail page
- Use the existing shared table, input, select, and pagination components
- Follow `module.operationsCourse` i18n namespace for all new strings

### Verification

- `admin_operations/courses_users.py` implements the operator user list.
- `test_admin_course_detail.py` covers the related-user union, filters, and
  redemption orders. The Cook Web course-detail suite covers the users tab.

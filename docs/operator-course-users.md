## Operator Course Users Section

### Goal

Add an operator-facing user data section to the course detail page under `运营 -> 课程管理 -> 课程详情` so operators can inspect course-related users without leaving the course context.

### Scope

- Keep the existing course detail route at `src/cook-web/src/app/admin/operations/[shifu_bid]/page.tsx`
- Add a dedicated backend API under the shifu admin surface for course-related users
- Reuse existing user, course-permission, order, and learning records; do not add new tables in the first version
- Keep the UI style aligned with the existing operator course detail and course list pages

### User Range

The list should include the union of users who are related to the current course via:

- active course permissions (`ai_course_auth`)
- successful paid orders
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
- Derive `joined_at` from the earliest available timestamp across paid order, active course permission, and learning progress record

### Frontend Notes

- Add explicit search and reset buttons in the user filter area
- Keep the user section as a regular bottom card on the course detail page
- Use the existing shared table, input, select, and pagination components
- Follow `module.operationsCourse` i18n namespace for all new strings

### Verification

- Add focused backend tests for the new operator course users route and filter behavior
- Add focused frontend tests for the new user section rendering and search trigger behavior
- Run focused frontend lint/test and focused backend pytest coverage for touched files

---
title: Operator Course Detail Page
status: implemented
owner_surface: shared
last_reviewed: 2026-04-17
canonical: true
---

## Operator Course Detail Page

### Goal

Add an operator-facing course detail page under `运营 -> 课程管理` so operators can open a course from the list and inspect its key metadata, operating metrics, and chapter structure in one place.

### Scope

- Keep the existing route entry at `src/cook-web/src/app/admin/operations/[shifu_bid]/page.tsx`
- Add a dedicated operator detail API under the shifu admin surface
- Show three sections on the page:
  - basic course information
  - metrics summary
  - chapter tree list

### Data Contract

The backend detail payload should return:

- `basic_info`
  - `shifu_bid`
  - `course_name`
  - `course_status`
  - creator identity fields
  - created / updated timestamps
- `metrics`
  - `learner_count`
  - `order_count`
  - `order_amount`
  - `follow_up_count`
  - `rating_score`
- `chapters`
  - nested outline nodes for the latest course version
  - each node carries chapter/lesson kind, learning permission, visibility,
    content status, and last modifier identity
- chapter detail endpoint
  - returns chapter `content` on demand when the operator opens the detail modal
  - resolves system prompt with fallback order:
    lesson -> chapter -> course
  - returns prompt source metadata so the modal can label where the prompt came
    from

### Backend Notes

- Reuse the operator visibility rules from the existing course list
- Reuse the latest draft-vs-published resolution used by the operator list:
  - prefer the latest draft row when present
  - still expose whether the course is published
- Build chapter data from the resolved latest outline source so the detail page reflects the latest editable structure

### Frontend Notes

- Keep the page aligned with the existing admin detail card style used in dashboard pages
- Use i18n keys in `module.operationsCourse`
- Keep the bottom section optimized for inspection rather than rich editing

### Verification

- Add focused backend tests for the new operator detail response
- Add focused frontend tests for the detail page loading, rendering, and back navigation
- Run targeted type, lint, and pytest coverage for touched files

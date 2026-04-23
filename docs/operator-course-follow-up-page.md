# Operator Course Follow-Up Page

## Goal

Add an operator-facing course follow-up page under `运营 -> 课程管理 -> 课程详情`
so operators can click the `追问数` metric card and inspect course-scoped
follow-up records, filters, and per-record conversation detail without leaving
the course context.

## Route And Entry

### Frontend route

- `src/cook-web/src/app/admin/operations/[shifu_bid]/follow-ups/page.tsx`
- URL: `/admin/operations/[shifu_bid]/follow-ups`

### Entry point

- keep the existing operator course detail page at
  `src/cook-web/src/app/admin/operations/[shifu_bid]/page.tsx`
- make the `追问数` metric card clickable
- clicking the card navigates to the follow-up page for the current course

### Navigation behavior

- show a top-level return button
- return target: the current course detail page
- keep the page inside the existing operator course context instead of adding a
  new first-level admin menu item

## Scope

- first version covers the course-scoped follow-up list only
- first version does **not** add a cross-course global follow-up page
- first version does **not** add export, manual status workflow, or operator
  annotations
- first version uses a detail drawer instead of a dedicated detail page

## Product Decisions

### Naming

- route and admin-facing naming should use `follow_up` / `follow-ups`
- backend implementation may continue to reuse existing `ask` / `mdask`
  storage concepts internally

### Record granularity

- one table row = one student follow-up record
- the list total should align with the course detail header `follow_up_count`
  metric

### Drawer pattern

- use a right-side drawer for follow-up detail
- do not navigate to a separate page for a single record in the first version

## Page Structure

### 1. Top bar

- back button
  - label: return to course detail
  - target: `/admin/operations/[shifu_bid]`
- page title: `追问数据`
- secondary text under the title should keep the filtered-result scope hint
- first version does **not** require a separate subtitle that repeats course
  name and course BID in the header

### 2. Summary cards

Show four summary cards at the top of the page:

- `追问总数`
- `追问用户数`
- `涉及节数`
- `最近追问时间`

These cards should be computed from the filtered course scope, not from a
global operator scope.

### 3. Filter area

First version filters:

- `keyword`
  - fuzzy match against:
    - `user_bid`
    - phone
    - email
    - nickname
- `chapter_keyword`
  - fuzzy match against chapter title or lesson title
- `start_time`
  - follow-up created-at lower bound
- `end_time`
  - follow-up created-at upper bound
- `page`
- `page_size`

#### Account display rule

The list and drawer should display the preferred account field by environment:

- CN view: prefer phone
- COM view: prefer email
- fallback order:
  - preferred contact
  - alternate contact
  - `user_bid`

### 4. List area

Recommended columns:

- `追问时间`
- `用户`
  - primary line: preferred account field or `user_bid`
  - secondary line: nickname
- `所属课时`
  - primary line: lesson title
  - secondary line: chapter title
- `追问内容`
  - single-line truncation
  - tooltip on hover
  - clicking the cell can also open the detail drawer
- `追问轮次`
  - display as `第 N 次`
- `操作`
  - `查看详情`

#### Empty states

- page empty: the course has no follow-up records
- filter empty: no follow-up records match the current filters

### 5. Detail drawer

The drawer should contain three sections:

#### Basic info

- user information
  - preferred account field
  - nickname
  - `user_bid`
- course and outline information
  - course name
  - chapter title
  - lesson title
- follow-up created time
- follow-up turn index

#### Current record

- current follow-up content
- current system answer

#### Timeline

- render the multi-turn ask/answer timeline for the same course progress record
- order by time ascending
- include both student and teacher messages
- highlight the currently selected follow-up turn

## Data Definitions

### Follow-up record definition

To stay aligned with the existing course detail metric, one follow-up record is
one row in `learn_generated_blocks` that satisfies:

- `shifu_bid = current course`
- `deleted = 0`
- `status = 1`
- `type = BLOCK_TYPE_MDASK_VALUE`
- `role = ROLE_STUDENT`

This is the same business definition currently used by the operator course
detail `follow_up_count` metric in `src/api/flaskr/service/shifu/admin.py`.

### Summary definitions

- `follow_up_count`
  - count of follow-up rows under the course and current filter scope
- `user_count`
  - distinct `user_bid` count from the filtered follow-up rows
- `lesson_count`
  - distinct lesson `outline_item_bid` count from the filtered follow-up rows
- `latest_follow_up_at`
  - max follow-up `created_at` under the filtered scope

### Turn index definition

- `turn_index` = the 1-based position of the current student follow-up within
  the same `progress_record_bid`, ordered by follow-up creation time ascending

### Answer matching definition

For the first version, answer resolution should reuse the existing
`LearnGeneratedBlock` pairing behavior already used by the follow-up backfill
logic:

- prefer the immediately following `BLOCK_TYPE_MDANSWER_VALUE`
- allow the teacher-side content block with the same position as the ask block
  when that is how the answer was recorded

This keeps the detail drawer aligned with the current runtime storage model
without forcing an early migration to a more complex event-only query path.

## Backend API Contract

### 1. Follow-up list

- `GET /api/shifu/admin/operations/courses/<shifu_bid>/follow-ups`

#### Query params

- `page`
- `page_size`
- `keyword`
- `chapter_keyword`
- `start_time`
- `end_time`

#### Suggested response

```json
{
  "summary": {
    "follow_up_count": 120,
    "user_count": 35,
    "lesson_count": 18,
    "latest_follow_up_at": "2026-04-21 10:20:30"
  },
  "page": 1,
  "page_size": 20,
  "total": 120,
  "page_count": 6,
  "items": [
    {
      "generated_block_bid": "ask-block-1",
      "progress_record_bid": "progress-1",
      "user_bid": "user-1",
      "mobile": "13800001234",
      "email": "",
      "nickname": "user-1",
      "chapter_outline_item_bid": "chapter-1",
      "chapter_title": "Chapter 1",
      "lesson_outline_item_bid": "lesson-1",
      "lesson_title": "Lesson 1",
      "follow_up_content": "Why is this value calculated like this?",
      "turn_index": 3,
      "created_at": "2026-04-21 10:20:30"
    }
  ]
}
```

### 2. Follow-up detail

- `GET /api/shifu/admin/operations/courses/<shifu_bid>/follow-ups/<generated_block_bid>/detail`

#### Suggested response

```json
{
  "basic_info": {
    "generated_block_bid": "ask-block-1",
    "progress_record_bid": "progress-1",
    "user_bid": "user-1",
    "mobile": "13800001234",
    "email": "",
    "nickname": "user-1",
    "course_name": "Course A",
    "shifu_bid": "course-a",
    "chapter_title": "Chapter 1",
    "lesson_title": "Lesson 1",
    "created_at": "2026-04-21 10:20:30",
    "turn_index": 3
  },
  "current_record": {
    "follow_up_content": "Why is this value calculated like this?",
    "answer_content": "Because the current branch uses ...",
    "source_output_content": "Definition block: current branch formula",
    "source_output_type": "interaction",
    "source_position": 2,
    "source_element_bid": "element-1",
    "source_element_type": "rich_text"
  },
  "timeline": [
    {
      "role": "student",
      "content": "First follow-up question",
      "created_at": "2026-04-21 10:00:00",
      "is_current": false
    },
    {
      "role": "teacher",
      "content": "First follow-up answer",
      "created_at": "2026-04-21 10:00:03",
      "is_current": false
    }
  ]
}
```

## Backend Notes

- reuse the existing operator course resolution logic:
  - latest draft when present
  - otherwise published
- reuse the current outline tree resolution to map lesson IDs to:
  - chapter title
  - lesson title
  - chapter path data needed by the list and drawer
- keep the course detail metric and follow-up list on the same counting rule
- prefer `LearnGeneratedBlock` as the primary source in v1 because it matches
  the existing course detail metric and makes pagination stable
- note that the backend already uses `LearnGeneratedElement` to resolve
  follow-up sources such as anchor snapshots; any broader refinement beyond
  that existing resolution flow can remain out of scope for v1 unless the
  current data source proves insufficient during implementation

## Frontend Notes

- reuse the existing admin shared table capability layer:
  - `AdminTableShell`
  - `AdminPagination`
  - `AdminTooltipText`
  - `useAdminResizableColumns`
- keep the page visual language aligned with the current operator course detail
  page
- use the `module.operationsCourse` i18n namespace for the first version to
  keep strings co-located with course detail semantics
- make the follow-up metric card clickable as a full-card affordance, not just
  a small inline button

## Open Questions For Implementation

- whether the list summary should reflect the full course scope only or the
  active filter scope
  - recommended first version: reflect the active filter scope so operators can
    immediately understand filtered subsets
- whether follow-up content in the drawer should support copy-to-clipboard in
  v1
  - recommended first version: optional, can be deferred

## Verification

- add focused backend tests for:
  - list route basic response
  - user keyword filter
  - chapter keyword filter
  - time range filter
  - summary metric alignment
  - detail route answer pairing and timeline ordering
- add focused frontend tests for:
  - metric-card navigation from course detail page
  - follow-up page rendering
  - filter interactions
  - drawer open behavior
- run the smallest relevant checks first:
  - targeted backend pytest modules
  - targeted frontend tests
  - touched-file pre-commit / lint / type-check coverage as needed

# Dashboard Entry Page (v2) - Task List

## Phase 0 - Discovery and Design

- [x] Confirm requirement: add dashboard entry page with total metrics + course list, and click-through to current detail page
- [x] Inspect current dashboard route and related APIs (`/admin/dashboard`, `/api/dashboard/shifus/{shifu_bid}/...`, `/api/order/admin/orders`)
- [x] Create technical design doc: `docs/dashboard-entry-page.md`
- [x] Create this task list in `tasks.md`

## Backend (Flask API)

- [x] Add DTOs in `src/api/flaskr/service/dashboard/dtos.py` for entry summary and course list items
- [x] Implement aggregation function in `src/api/flaskr/service/dashboard/funcs.py` for dashboard entry metrics
- [x] Add endpoint `GET /api/dashboard/entry` in `src/api/flaskr/service/dashboard/routes.py`
- [x] Enforce permission and course scope based on current operator visibility
- [x] Support filters: `start_date`, `end_date`, `keyword`, `page_index`, `page_size`
- [x] Add backend tests in `src/api/tests/service/dashboard/` for metric correctness, pagination, and permission checks

## Frontend (Cook Web)

- [x] Move current dashboard detail view to route: `src/cook-web/src/app/admin/dashboard/shifu/[shifu_bid]/page.tsx`
- [x] Implement new dashboard entry page at `src/cook-web/src/app/admin/dashboard/page.tsx`
- [x] Add API definition in `src/cook-web/src/api/api.ts`: `getDashboardEntry`
- [x] Add new TS types in `src/cook-web/src/types/dashboard.ts` for entry response payload
- [x] Build entry KPI cards (courses, learners, orders, generations)
- [x] Build course list UI with click navigation to detail route
- [x] Preserve existing detail behaviors (charts, learner table, learner detail sheet)
- [x] Handle loading/error/empty states aligned with current admin pages

## i18n

- [x] Add new dashboard entry keys in `src/i18n/en-US/modules/dashboard.json`
- [x] Add new dashboard entry keys in `src/i18n/zh-CN/modules/dashboard.json`
- [x] Run `python scripts/check_translations.py`
- [x] Run `python scripts/check_translation_usage.py --fail-on-unused`
- [x] Run `cd src/cook-web && npm run i18n:keys`

## QA and Validation

- [x] Run backend tests: `cd src/api && pytest tests/service/dashboard -q`
- [x] Run frontend checks: `cd src/cook-web && npm run lint && npm run type-check`
- [x] Run repository hooks: `pre-commit run -a`
- [ ] Manual smoke test: open `/admin/dashboard` and verify KPI totals and course list
- [ ] Manual smoke test: click one course and verify detail page data loads correctly
- [ ] Manual smoke test: verify date range filter behavior on entry and detail pages

# Teacher Analytics Dashboard (v1) - Task List

## Phase 0 - Discovery & Design

- [x] Inspect existing course/progress/follow-up/profile logic (backend + Cook Web)
- [x] Write design doc: `docs/teacher-analytics-dashboard.md`
- [x] Create this task list: `tasks.md`

## Backend (Flask API)

- [ ] Add new module skeleton: `src/api/flaskr/service/dashboard/` (`__init__.py`, `dtos.py`, `funcs.py`, `routes.py`)
- [ ] Implement permission checks: require `view` permission via `shifu_permission_verification(app, user_id, shifu_bid, "view")`
- [ ] Implement published outline loader (from `LogPublishedStruct` + `PublishedOutlineItem`) and flatten to the “required outline set”
- [ ] Implement “latest progress record” selection per `(user_bid, outline_item_bid)` using `max(id)` subquery (exclude `LEARN_STATUS_RESET`, `deleted=0`)
- [ ] Implement grouped follow-up queries from `LearnGeneratedBlock` (MDASK/MDANSWER) with time-range filters
- [ ] Implement endpoint: `GET /api/dashboard/shifus/{shifu_bid}/outlines`
- [ ] Implement endpoint: `GET /api/dashboard/shifus/{shifu_bid}/overview` (KPIs + chart-ready series)
- [ ] Implement endpoint: `GET /api/dashboard/shifus/{shifu_bid}/learners` (pagination, keyword search, sorting)
- [ ] Implement endpoint: `GET /api/dashboard/shifus/{shifu_bid}/learners/{user_bid}` (progress + variables + follow-up summary)
- [ ] Implement endpoint: `GET /api/dashboard/shifus/{shifu_bid}/learners/{user_bid}/followups` (pagination + filters)
- [ ] Add swagger schemas for DTOs (`@register_schema_to_swagger`) and keep responses compatible with `make_common_response`
- [ ] Add backend tests under `src/api/tests/service/dashboard/` (permission, outline selection, latest-record correctness, pagination)
- [ ] (Optional) Add DB indexes/migration if performance requires it (e.g., `learn_generated_blocks(shifu_bid,type,created_at)`)

## Frontend (Cook Web)

- [ ] Add chart deps: `echarts` + `echarts-for-react` in `src/cook-web/package.json`
- [ ] Add reusable chart primitives:
- [ ] Create `src/cook-web/src/components/charts/EChart.tsx` (client-only `next/dynamic` wrapper around `echarts-for-react`)
- [ ] Create `src/cook-web/src/components/charts/ChartCard.tsx` (standard title/subtitle/actions chrome)
- [ ] Add shared chart option builders: `src/cook-web/src/lib/charts/options.ts`
- [ ] Add new API definitions in `src/cook-web/src/api/api.ts` for dashboard endpoints
- [ ] Add TS types: `src/cook-web/src/types/dashboard.ts` (overview, learner list, learner detail, follow-up items)
- [ ] Add i18n namespace:
- [ ] Create `src/i18n/en-US/modules/dashboard.json`
- [ ] Create `src/i18n/zh-CN/modules/dashboard.json`
- [ ] Run i18n validation scripts when implemented (`python scripts/check_translations.py`, `python scripts/check_translation_usage.py --fail-on-unused`)
- [ ] Add admin navigation entry for dashboard in `src/cook-web/src/app/admin/layout.tsx`
- [ ] Add page: `src/cook-web/src/app/admin/dashboard/page.tsx`
- [ ] Implement header controls (course selector + date range filter)
- [ ] Implement KPI cards section (learners, completion rate, follow-ups, last active)
- [ ] Implement charts section (progress distribution, follow-up trend, top outlines)
- [ ] Implement learner table (pagination, keyword search, sorting)
- [ ] Implement learner detail `Sheet` with tabs (progress, follow-ups, personalization)
- [ ] Implement loading + error states consistent with existing admin pages (`Loading`, `ErrorDisplay`)
- [ ] (Optional) Add frontend tests for chart wrappers and dashboard page (Jest)

## QA / Quality Gates

- [ ] Run backend tests: `cd src/api && pytest`
- [ ] Run frontend checks: `cd src/cook-web && npm run lint && npm run type-check && npm test` (as needed)
- [ ] Run repo pre-commit: `pre-commit run -a`
- [ ] Manual smoke test:
- [ ] Load `/admin/dashboard`
- [ ] Switch shifu/course
- [ ] Change date range
- [ ] Open learner detail, browse follow-ups, verify personalization values

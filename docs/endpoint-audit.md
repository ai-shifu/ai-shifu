## Legacy Web Endpoint Audit

### Context
- Legacy React app (`src/web/`) has been removed in favour of the unified Cook Web frontend.
- Before deleting backend surface area, we need a traceable record of which HTTP routes were unique to the legacy client.

### Methodology
- Examined commit `HEAD^^` (last revision that still contained `src/web`) and parsed every `.ts/.tsx/.js/.jsx` file for `/api/...` string literals, ignoring inline (`//`) and block (`/* ... */`) comments.
- Collected the same endpoints from the current Cook Web tree (`src/cook-web/**`, including `src/cook-web/src/c-api`).
- Normalised URLs by stripping query strings to compare route paths.

### Findings

**Counts**
- Legacy `src/web`: 29 unique endpoints.
- Current `src/cook-web`: 33 unique endpoints.
- Overlap: 26 endpoints (remain required for Cook Web).

**Endpoints only used by legacy `src/web`**
- `/api/course/get-course-info` — course metadata fetch used by the legacy learner UI.
- `/api/study/reset-study-progress` — lesson reset endpoint triggered from the legacy learner UI.

These endpoints can be retired from the backend once consumers are removed. Note: Cook Web calls `POST /user/verify_sms_code` via a relative path string (`'POST /user/verify_sms_code'`), so that login flow remains active in the unified frontend.

**Endpoints still shared between Cook Web and legacy `src/web`**
- `/api/click2cash/generate-active-order`
- `/api/order/apply-discount`
- `/api/order/init-order`
- `/api/order/order-test`
- `/api/order/query-order`
- `/api/order/reqiure-to-pay`
- `/api/study/get_lesson_study_record`
- `/api/study/get_lesson_tree`
- `/api/study/query-script-into`
- `/api/study/run`
- `/api/study/script-content-operation`
- `/api/user/generate_chk_code`
- `/api/user/get_profile`
- `/api/user/info`
- `/api/user/login`
- `/api/user/register`
- `/api/user/require_reset_code`
- `/api/user/require_tmp`
- `/api/user/reset_password`
- `/api/user/send_sms_code`
- `/api/user/submit-feedback`
- `/api/user/update_info`
- `/api/user/update_openid`
- `/api/user/update_password`
- `/api/user/update_profile`
- `/api/user/upload_avatar`

Cook Web still depends on these API routes and the supporting services/tests must remain.

**Endpoints only used by Cook Web**
- `/api/config`
- `/api/config/route`
- `/api/i18n`
- `/api/i18n/route`
- `/api/learn/shifu/`
- `/api/llm/debug-prompt`
- `/api/shifu/upfile`

These are unique to Cook Web and are not candidates for deletion.

### Next Steps
- Remove the legacy-only routes and associated service logic from `src/api`.
- Update automated tests alongside removals to keep coverage intact.
- Use this audit as the authoritative reference when reviewing backend deletions during this refactor.

## Legacy Web Endpoint Audit

### Context
- Legacy React app (`src/web/`) has been removed in favour of the unified Cook Web frontend.
- Before deleting backend surface area, we need a traceable record of which HTTP routes were unique to the legacy client.

### Methodology
- Examined commit `HEAD^^` (last revision that still contained `src/web`) and parsed every `.ts/.tsx/.js/.jsx` file for `/api/...` string literals, ignoring inline (`//`) and block (`/* ... */`) comments.
- Collected the same endpoints from the current Cook Web tree (`src/cook-web/**`, including `src/cook-web/src/c-api`).
- Normalised URLs by stripping query strings to compare route paths.

### Findings

**Current Cook Web surface (post-refactor)**
- Cook Web references 22 distinct `/api/...` endpoints today:
  - `/api/click2cash/generate-active-order`
  - `/api/config`
  - `/api/i18n`
  - `/api/learn/shifu/`
  - `/api/order/apply-discount`
  - `/api/order/init-order`
  - `/api/order/query-order`
  - `/api/order/reqiure-to-pay`
  - `/api/shifu/upfile`
  - `/api/study/get_lesson_study_record`
  - `/api/study/query-script-into`
  - `/api/study/run`
  - `/api/study/script-content-operation`
  - `/api/user/get_profile`
  - `/api/user/info`
  - `/api/user/require_tmp`
  - `/api/user/send_sms_code`
  - `/api/user/submit-feedback`
  - `/api/user/update_info`
  - `/api/user/update_openid`
  - `/api/user/update_profile`
  - `/api/user/upload_avatar`
- All other `/api/...` paths previously referenced by the legacy `src/web` client have now been deleted from Cook Web.

**Legacy-only endpoints removed from the backend**
- `/api/course/get-course-info`
- `/api/study/get_lesson_tree`
- `/api/study/reset-study-progress`
- `/api/user/generate_chk_code`
- `/api/user/register`
- `/api/user/login`
- `/api/user/require_reset_code`
- `/api/user/reset_password`
- `/api/user/update_password`
- `/api/user/send_mail_code`
- `/api/user/verify_mail_code`
- `/api/order/order-test`

These removals eliminate the final dependencies on the deprecated `src/web` React application. Remaining endpoints listed above are still exercised by Cook Web and must be kept functional.

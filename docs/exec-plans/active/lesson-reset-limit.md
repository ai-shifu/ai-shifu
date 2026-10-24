# Lesson reset limit backed by SQL

## Purpose / Big Picture

Repeated lesson resets regenerate teaching text and audio, so a few learners can
drive unusual delivery cost. Cap the number of effective resets an ordinary
learner may perform on one lesson of one course with a single deployment
setting, `LESSON_RESET_LIMIT`, and persist the usage in a new SQL table so the
count survives restarts, cache eviction and Redis failures.

This supersedes PR #3091, which kept the counter, an admission lock and 24-hour
empty-reset receipts in Redis. Redis in this deployment is not durable storage,
so a flush or eviction would silently hand every learner a fresh allowance.

## Progress

- [x] 2026-10-24 CST: Reviewed PR #3091 and the current reset path. Confirmed
  that existing tables cannot count resets exactly: one reset may retire several
  sibling progress rows, empty resets leave nothing behind, and agent sessions
  cover only 2.0 lessons.
- [x] 2026-10-24 CST: User chose an event table over a counter column or a
  per-lesson counter row, a default of `0` meaning unlimited, and a fresh branch
  from `main` with PR #3091 closed.
- [x] 2026-10-24 CST: Added `LESSON_RESET_LIMIT`, the
  `learn_lesson_reset_records` model and migration `a7c1e3f5b9d2`, the
  SQL-only `lesson_reset_limit` module, the reset-status route, error code
  4021 and eight-locale translations.
- [x] 2026-10-24 CST: Wired the learner UI: availability check while a reset
  dialog is open, exhausted copy instead of the destructive confirmation,
  updated-lesson notice without a reset link, retry-safe request ids.
- [x] 2026-10-24 CST: Backend reset suites (177 tests) and the affected web
  suites pass locally.
- [ ] Production release: apply the migration before or immediately after the
  image rolls in China, set `LESSON_RESET_LIMIT=10` in both regions' API
  ConfigMaps, and verify one ordinary learner is blocked on the eleventh reset.

## Surprises & Discoveries

- `learn_progress_records` rows are learning attempts, not reset operations. A
  concurrent Ask can create a sibling row, so one reset retires several rows;
  counting rows with status 608 overcounts.
- PR #3091's exec plan records that Redis was chosen only because a schema
  change was refused at the time. That constraint no longer applies.
- The reset path already takes `FOR UPDATE` on the live progress rows and the
  live agent session. Two concurrent resets therefore serialize on those locks,
  and the second finds nothing live and is treated as empty. No extra lock is
  needed to keep the SQL count exact.
- A learner reset used to discard both the published and the draft preview
  agent session (`preview_mode=None`). The reset now passes the explicit scope,
  so an author's preview survives a learner reset of the same lesson.

## Decision Log

- Store one row per effective reset in `learn_lesson_reset_records`. The quota
  is `COUNT(*)` of rows with `counted=1` and `deleted=0` for the same user,
  course and lesson. Rows are written inside the reset transaction, so a failed
  reset writes nothing and a committed reset is always counted.
- Record exempt (owner/collaborator) and preview resets too, with `counted=0`,
  so support can see every reset without them affecting quota.
- Keep the row minimal but extensible: `progress_record_bid` for tracing,
  `preview_mode`, `counted`, `request_id` for idempotent retries, `deleted` to
  refund one use by hand. Per-course or per-user allowances belong in a future
  policy table; this table does not change for them.
- `LESSON_RESET_LIMIT` defaults to `0`, meaning unlimited, so an unconfigured
  deployment behaves exactly as before. Production sets `10`.
- Empty resets (no live progress rows and no live published session) are not
  recorded and not counted; they return success as before.
- A retry carrying the same `X-Request-ID` as a recorded reset returns success
  without touching anything, so a lost response cannot clear learning the
  learner has since started or spend a second use. The receipt is hashed and
  unique per user.
- Exemption reuses the existing owner/collaborator check from
  `preview_permissions.py`, not the Redis-cached permission helper.
- The client checks availability only while a reset dialog is open. A failed
  availability read falls back to "ready"; the reset request remains the
  authority and answers code 4021 when exhausted. There is no "temporarily
  unavailable" state because there is no Redis dependency.
- Historical resets are not backfilled. Quota counts from the first reset after
  the migration is applied.

## Outcomes & Retrospective

Backend and learner UI are implemented on branch `feat/lesson-reset-limit`.
Production is unchanged until the PR merges, the migration runs and the limit
is configured. The Redis guard, lock renewal thread, Lua scripts and 24-hour
receipts from PR #3091 are gone; the whole limit is about 150 lines of SQL
service code plus one additive table.

## Context and Orientation

- Reset entry: `src/api/flaskr/service/learn/learn_funcs.py:reset_learn_record`,
  called from `DELETE /api/learn/shifu/<shifu_bid>/records/<outline_bid>` in
  `routes.py`. Availability: `GET .../records/<outline_bid>/reset-status`.
- Limit helpers: `src/api/flaskr/service/learn/lesson_reset_limit.py`.
- Model: `LearnLessonResetRecord` in `src/api/flaskr/service/learn/models.py`;
  migration `src/api/migrations/versions/a7c1e3f5b9d2_add_learn_lesson_reset_records.py`.
- Web: `src/web/src/api/lesson.ts`, `src/web/src/hooks/useLessonResetStatus.ts`,
  `CourseCatalog/ResetChapterButton.tsx`, `LessonUpdateNotice.tsx`.
- Translations: `server.learn.resetLimitReached` in
  `src/i18n/<lang>/modules/backend/learn.json`;
  `module.chat.lessonUpdateReviewAvailable` in `src/i18n/<lang>/modules/chat.json`.

## Plan of Work

1. Declare the setting and the table; generate the migration from the model.
2. Replace the Redis guard with SQL helpers that run inside the caller's unit
   of work: exemption, lesson-in-course check, count, receipt lookup, record.
3. Admit or refuse inside `reset_learn_record` after the row locks, before any
   state change; record the reset in the same transaction.
4. Expose availability over HTTP for the dialog; pass the client trace id to
   the reset for receipts.
5. Show exhausted copy in the two reset surfaces and drop the reset link from
   the updated-lesson notice when exhausted.

## Concrete Steps

- `src/api/flaskr/common/config.py`: `LESSON_RESET_LIMIT` (int, default 0).
- `src/api/flaskr/service/learn/models.py`: `LearnLessonResetRecord`.
- `src/api/migrations/versions/a7c1e3f5b9d2_add_learn_lesson_reset_records.py`.
- `src/api/flaskr/service/learn/lesson_reset_limit.py` (new).
- `src/api/flaskr/service/learn/learn_funcs.py`: admission, scoped discard,
  recording.
- `src/api/flaskr/service/learn/routes.py`: `reset_request_id` and
  `lesson_reset_status_api`.
- `src/api/flaskr/service/learn/preview_permissions.py`:
  `has_shifu_staff_permission` made public.
- `src/api/error_codes.json`: `server.learn.resetLimitReached` = 4021.
- Web client, hook, components and tests listed above.

## Validation and Acceptance

- `pytest tests/service/learn/test_lesson_reset_limit.py` covers: empty reset
  free; limit reached on the third effective reset with progress preserved;
  limit 0 unlimited; lessons and learners independent; owner and collaborator
  recorded but unlimited; retry with the same request id neither clears new
  learning nor charges; agent-session-only lessons count; learner reset leaves
  the draft preview session; preview reset not counted; foreign lesson rejected.
- `tests/service/learn/test_learn_route_contracts.py` covers the status route's
  preview permission and identity, trace-id pass-through, and an HTTP round
  trip that ends in code 4021.
- Web: `lesson.test.ts`, `useLessonResetStatus.test.tsx`,
  `ResetChapterButton.test.tsx`, `LessonUpdateNotice.test.tsx`,
  `NewChatComp.lessonUpdateNotice.test.tsx`.
- Release acceptance: with `LESSON_RESET_LIMIT=10`, an ordinary learner resets
  one lesson ten times, the eleventh attempt shows the exhausted dialog and
  content remains; `SELECT COUNT(*) FROM learn_lesson_reset_records WHERE
  user_bid=? AND outline_item_bid=? AND counted=1` returns 10; another lesson
  still resets; the course owner is never blocked.

## Idempotence and Recovery

- The migration is additive; `downgrade` drops the table. Rolling back the
  image without the downgrade is safe because old code never reads the table.
- China rolls the image before the migration is run by hand; during that
  window only the reset and reset-status endpoints fail with an unknown-table
  error. Run the migration first when possible.
- To relax the cap, set `LESSON_RESET_LIMIT=0` or a higher value and roll the
  API pods; rows are kept. To refund one use, set `deleted=1` on that row.

## Interfaces and Dependencies

- Env: `LESSON_RESET_LIMIT` (int >= 0, default 0).
- HTTP: `GET /api/learn/shifu/<shifu_bid>/records/<outline_bid>/reset-status?preview_mode=`
  returns `{ "can_reset": boolean }`; `DELETE .../records/<outline_bid>` now
  reads `X-Request-ID` and may answer code 4021.
- Analytics: `lesson_reset_blocked` with `source` (`catalog` or
  `lesson_update`) and `reason` (`limit_reached`).

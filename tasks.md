# Backend Test Completion Plan (SQLite + Mock Redis + Mock LLM)

## Goals
- Run backend tests against SQLite (no MySQL dependency).
- Provide a reusable mock Redis client for tests.
- Ensure all LLM calls in tests are mocked unless a test opts out.

## Current State (as of 2026-01-20)
- `src/api/tests/conftest.py` builds a full `create_app()` and runs Alembic migrations.
- Some tests hand-roll SQLite apps (e.g. `tests/service/learn/*`), and some tests stub LLM/Redis ad-hoc.
- Multiple modules import `redis_client` at module scope, so patching `flaskr.dao.redis_client` alone is insufficient.

## Plan
1. **SQLite-first test bootstrap**
   - Set required env vars in `src/api/tests/conftest.py` *before* `create_app()`:
     - `SQLALCHEMY_DATABASE_URI=sqlite:///...`
     - `SECRET_KEY`, `UNIVERSAL_VERIFICATION_CODE`
     - `SKIP_DB_MIGRATIONS_FOR_TESTS=1` (avoid MySQL-specific migrations)
   - After app creation, call `dao.db.create_all()` inside app context.
   - Add a teardown step to `dao.db.session.remove()` and optionally `dao.db.drop_all()` at session end.
   - Decide SQLite path strategy:
     - Prefer file-based SQLite in `/tmp` for multi-connection stability.
     - Keep in-memory only for isolated unit tests that create their own app.

2. **Mock Redis client (shared)**
   - Add a small in-memory Redis stub (e.g. `src/api/tests/common/fixtures/fake_redis.py`):
     - Support: `get`, `set`, `setex`, `getex`, `delete`, `incr`, `ttl`, `lock`
     - Lock object should implement `acquire()` and `release()`; no-op but deterministic.
   - Create an autouse fixture in `src/api/tests/conftest.py` to:
     - Patch `flaskr.dao.redis_client`
     - Patch module-scope imports (`... import redis_client as redis`) in:
       - `flaskr.service.user.phone_flow`
       - `flaskr.service.user.email_flow`
       - `flaskr.service.user.utils`
       - `flaskr.service.user.common`
       - `flaskr.service.user.auth.providers.google`
       - `flaskr.service.config.funcs`
       - `flaskr.service.shifu.funcs`
       - `flaskr.service.learn.context_v2`
       - `flaskr.service.learn.runscript_v2`
       - `flaskr.service.order.funs`
   - Ensure `tests/test_redislock.py` runs without a real Redis instance.

3. **Mock LLM calls (shared)**
   - Add a fixture (autouse by default) to stub:
     - `flaskr.api.llm.invoke_llm`
     - `flaskr.api.llm.chat_llm`
     - `flaskr.api.llm.get_allowed_models`
     - `flaskr.api.llm.get_current_models`
   - Provide a simple fake stream generator that returns deterministic chunks.
   - Allow opt-out for LLM-specific tests (e.g. `tests/test_llm.py`, `tests/test_openai.py`) via marker or fixture override.

4. **Test cleanup + alignment**
   - Replace per-test ad-hoc Redis/LLM stubs with shared fixtures.
   - Normalize SQLite usage:
     - Keep specialized SQLite unit tests as-is if they are intentionally isolated.
     - For integration-style tests, rely on the shared app fixture.

5. **Validation**
   - Run backend tests locally:
     - `cd src/api && pytest`
   - Spot-check: redis lock test, user identify flow, learn context tests, LLM tests.

## Deliverables
- Updated `src/api/tests/conftest.py` with SQLite + mock fixtures.
- New mock utility for Redis (and optional LLM helpers).
- Updated tests to rely on the shared mocks.

## Progress (as of 2026-01-20)
- SQLite + mock Redis/LLM fixtures are in place and used across tests.
- Converted the following previously skipped integration tests to unit tests:
  - `tests/test_check_code.py`, `tests/test_sms.py`, `tests/test_feishu.py`
  - `tests/test_fmt_prompt.py`, `tests/test_fmt_prompt_new.py`
  - `tests/test_redislock.py`, `tests/test_query_order.py`
  - `tests/test_active.py`, `tests/test_edun.py`
  - `tests/test_profile.py`, `tests/test_user.py`
  - `tests/test_mdflow_adapter.py`
- Current test run: `214 passed, 15 skipped` (`cd src/api && pytest`).
- Converted `tests/test_discount.py` to coupon unit coverage.
- Converted `tests/test_fix_discount.py` to coupon application unit test.
- Converted `tests/test_order.py` to init order unit coverage.
- Converted `tests/test_pingpp.py` to provider request unit tests.
- Converted `tests/test_wx_pub_order.py` to generate_charge unit coverage.
- Converted `tests/test_learn_api.py` to learn info/tree unit tests.
- Converted `tests/test_shifu_utils.py` to resource + creator unit tests.
- Converted `tests/test_shifu_funcs.py` to summary error-handling unit test.
- Converted `tests/test_chapter.py` to shifu outline tree unit test.
- Converted `tests/test_study_record.py` to learn record unit coverage.
- Converted `tests/test_sudy.py` to empty learn record unit test.

## Remaining Skipped Tests
- `tests/service/tts/test_tts_text_preprocess.py` (skips when app fixture disabled)

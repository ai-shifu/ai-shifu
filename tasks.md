AI‑Shifu – Work Items Status and Next Steps

- [x] 1) First verified user becomes admin/creator and owns demo course
  - Status: Not complete (partially implemented, currently ineffective)
  - Evidence:
    - First-user hook exists: `src/api/flaskr/service/user/phone_flow.py:96` and `src/api/flaskr/service/user/email_flow.py:79` call `init_first_course()` on new user creation.
    - Implementation bug: `init_first_course()` sets `course.created_user_id = user_id` but the column is `created_user_bid` in `shifu_published_shifus` (see `src/api/flaskr/service/shifu/models.py:602`). The wrong attribute means ownership is never persisted.
    - Permission check uses creator on DraftShifu: `src/api/flaskr/service/shifu/funcs.py:404` checks `DraftShifu.created_user_bid`, but `init_first_course()` only touches PublishedShifu, leaving Draft ownership unset.
  - Impact:
    - First verified user is not persisted as owner of the demo course; creator permissions may not apply as intended.
  - Fix Plan:
    - Change `created_user_id` -> `created_user_bid` in `init_first_course()`.
    - Also set creator on the corresponding DraftShifu (if present) to align with permission checks.
    - Optionally, guard for multiple demo courses and select by known demo shifu_bid.
  - Done:
    - Implemented in `src/api/flaskr/service/user/phone_flow.py` to write `created_user_bid` on `PublishedShifu` and also update the corresponding `DraftShifu.created_user_bid`.
    - Ran pre-commit hooks; all checks passed.

- [x] 2) docker/.env.example vs docker-compose for MySQL/Redis are inconsistent
  - Status: Not complete
  - Evidence:
    - Dev compose expects service DNS names: MySQL `ai-shifu-mysql`, Redis `ai-shifu-redis` (see `docker/docker-compose-dev.yml:1`, `docker/docker-compose.yml:1`).
    - `.env.example.full` defaults `REDIS_HOST="localhost"` (see `docker/.env.example.full:336`), causing containerized API to attempt Redis on loopback instead of `ai-shifu-redis`.
    - Minimal template leaves `SQLALCHEMY_DATABASE_URI` empty; for Docker it should point to `mysql://root:ai-shifu@ai-shifu-mysql:3306/ai-shifu?charset=utf8mb4` (see top-level env in `docker/docker-compose.yml:1`). Dev compose does not override this, so a copied `.env` with blanks or localhost will fail to start.
  - Impact:
    - Users following the examples cannot start services reliably with dev compose because the API cannot reach MySQL/Redis.
  - Fix Plan:
    - In `.env.example.minimal`, provide Docker-friendly defaults for MySQL/Redis when used with the bundled compose (and comment that these are for Docker).
    - In `.env.example.full`, either set Docker-safe defaults or add prominent comments with the exact values for Docker usage.
    - Optionally add an `.env.example.docker` with correct values referenced by docs.
  - Done:
    - Updated `docker/.env.example.minimal` to include Docker-ready defaults: `SECRET_KEY=ai-shifu`, `SQLALCHEMY_DATABASE_URI` using `ai-shifu-mysql`, and `REDIS_HOST=ai-shifu-redis`.
    - Updated `docker/.env.example.full` defaults: `SQLALCHEMY_DATABASE_URI` points to `ai-shifu-mysql` and `REDIS_HOST=ai-shifu-redis`.

- [ ] 3) “Clone and auto-start” docs are unclear
  - Status: Not complete
  - Evidence:
    - README describes copying `.env` and starting compose, but does not provide a single “works out-of-the-box” example with the exact Docker values for `SQLALCHEMY_DATABASE_URI` and `REDIS_HOST` that match bundled services (see `README.md:44`–`README.md:61`).
    - Dev workflow (`docker/docker-compose-dev.yml`) relies fully on `.env` for DB/Redis; current examples mislead toward `localhost`.
  - Impact:
    - New users cloning the repo may fail to start services on first try and need to iterate on env values.
  - Fix Plan:
    - Add a “One‑liner quick start” section showing: `cp .env.example.minimal .env && sed -i ...` or provide an example `.env` file that just works with included MySQL/Redis.
    - Explicitly document the Docker service hostnames and the recommended `SQLALCHEMY_DATABASE_URI` string for Docker.
    - Clarify dev vs prod compose differences, and where env overrides come from.

Notes
- The user role flags `is_admin` and `is_creator` are persisted on the legacy user model and exposed in the `UserInfo` DTO (see `src/api/flaskr/service/user/repository.py:119`). These work, but demo course ownership must be fixed as above to align creator permissions with shifu ownership checks.

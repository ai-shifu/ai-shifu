# User Management Refactor Notes

## Legacy Persistence Layer
- `user_info` (SQLAlchemy model `User`, File: `src/api/flaskr/service/user/models.py:18`)
  - Stores core profile fields (`user_id`, `username`, `name`, `email`, `mobile`, `user_state`, locale data, admin flags, OSS avatar details).
  - Referenced directly across services for authentication, profile updates, learning flows, and admin tooling. Key modules:
    - `src/api/flaskr/service/user/common.py` (token validation, profile updates, SMS/email verification).
    - `src/api/flaskr/service/user/user.py` (temporary user generation, OSS avatar upload, WeChat openid updates).
    - `src/api/flaskr/service/user/admin.py` (admin user list pagination).
    - `src/api/flaskr/service/profile/funcs.py` (profile CRUD + language handling).
    - `src/api/flaskr/service/learn/**` (multiple input/output handlers, continue flows, context loader, etc.).
    - `src/api/flaskr/service/order/funs.py` & `feishu_funcs.py` (order ownership + conversion reconciliation).
    - `src/api/flaskr/service/feedback/funs.py` (feedback association).
    - Admin plugin: `src/api/flaskr/plugins/ai_shifu_admin_api/src/service/user/funcs.py` & related routes.
- `user_conversion` (Model `UserConversion`, `src/api/flaskr/service/user/models.py:76`)
  - Tracks anonymous/temp users and conversion metadata (`conversion_id/source/status`) used during onboarding.
  - Consumed in `service/user/user.py` (temp user creation), `service/order/funs.py` and `feishu_funcs.py` (conversion linkage).
- `user_token` (Model `UserToken`, `src/api/flaskr/service/user/models.py:124`)
  - Historical token store; current flows primarily rely on Redis but model persists issuance records.
  - Read/written in `service/user/common.py` (token issuance paths).
- `user_verify_code` (Model `UserVerifyCode`, `src/api/flaskr/service/user/models.py:145`)
  - Persists verification code dispatch records for SMS/email.
  - Managed through `service/user/utils.py` (`send_sms_code`, `send_email_code`, and helpers).

## Service & Utility Touchpoints
- `src/api/flaskr/service/user/common.py`
  - Central login/validation logic (`validate_user`, `get_user_info`, `update_user_info`).
  - Handles SMS/email code issuance & verification, Redis coordination, state transitions to `USER_STATE_REGISTERED`.
- `src/api/flaskr/service/user/user.py`
  - Anonymous/temp user bootstrap, WeChat OAuth bridge, avatar uploads to OSS, token generation wrappers.
- `src/api/flaskr/service/user/admin.py`
  - Admin-side pagination & DTOs (`UserItemDTO`, `get_user_list`).
- `src/api/flaskr/service/user/utils.py`
  - Shared helpers: JWT token creation, captcha generation, language normalization, outbound SMS/email infrastructure.
- `src/api/flaskr/command/import_user.py`
  - CLI ingestion path touching `User` for bulk imports and course enrollment automation.

## API, Plugin, and Route Entry Points
- `src/api/flaskr/route/user.py`
  - Public REST endpoints for user info retrieval/update, temp login, SMS/email verification, avatar upload, plus optional token middleware.
- `src/api/flaskr/plugins/ai_shifu_admin_api/src/route/admin_users.py`
  - Admin REST surface for listing/updating users leverages `service/user` and plugin-specific services.
- `src/api/flaskr/plugins/ai_shifu_admin_api/src/middleware/auth.py`
  - Admin auth middleware reads `User` state flags for permission checks.
- `src/api/flaskr/service/profile/funcs.py`
  - Exposed via profile routes, mutates `User` columns (avatar/lang) alongside dedicated profile table.

## Cross-Service Dependencies to Audit During Refactor
- Learning flows (`src/api/flaskr/service/learn/…`) heavily couple to `User` for personalization, outline progress, and contact details.
- Order services (`src/api/flaskr/service/order/…`) expect `User` records for entitlement checks.
- Feedback service (`src/api/flaskr/service/feedback/funs.py`) links submissions to `User`.
- Test suites reference legacy models (e.g., `src/api/tests/test_order.py`, `test_discount.py`, `test_wx_pub_order.py`).


## Target Model Snapshot
- `user_users` (Model `UserInfo`, `src/api/flaskr/service/user/models.py:165`)
  - Business-keyed user record with `user_bid` (indexed), soft-delete flag, state enum (1101-1104), created/updated timestamps.
  - Lacks explicit SQLAlchemy relationships; future services must manage joins manually.
- `user_auth_credentials` (Model `AuthCredential`, `src/api/flaskr/service/user/models.py:188`)
  - Credential store keyed by `credential_bid` and `user_bid` (indexed) with provider metadata (`provider_name`, `subject_id`, `subject_format`, `identifier`).
  - Includes soft-delete, state flag (1201/1202), and `raw_profile` text column for provider payload storage.
  - No foreign key constraints; relies on application logic for referential integrity.

## Legacy Credential Mapping Plan
| Legacy Source | New `provider_name` | `subject_id` | `subject_format` | `identifier` | Additional Notes |
| --- | --- | --- | --- | --- | --- |
| `User.mobile` (phone login) | `phone` | existing mobile number | `phone` | same as `subject_id` | mark verified users (`user_state >= USER_STATE_REGISTERED`) as `state=1202`; capture SMS verification history in `raw_profile` if available. |
| `User.email` (email login) | `email` | normalized email | `email` | same as `subject_id` | enforce lowercase normalization prior to insert; consider historic verification status from email flow. |
| `User.user_open_id`/`User.user_unicon_id` (WeChat) | `wechat` | respective value | `open_id` / `unicon_id` | fallback identifier (email/phone) | create two credential records per user when both exist; persist original payload in `raw_profile`. |
| Future Google OAuth payload | `google` | Google subject (`sub`) | `google` | primary email from Google profile | persist full Google profile JSON in `raw_profile`; link to existing user via email/phone before new user creation. |
| Placeholder for other providers (Apple/Facebook) | `apple` / `facebook` | provider-specific subject | format per provider | email or unique account id | follow same data contract as Google once implemented; may require additional metadata columns later. |

## DTO & Response Contract Review
- `UserInfo` DTO (`src/api/flaskr/service/common/dtos.py:15`)
  - Encapsulates legacy `user_id` alongside login/state fields. Stringifies state labels (Chinese) and exposes `wx_openid` key in JSON output.
  - Refactor impact: introduce `user_bid` as primary id, preserve backwards-compatible `user_id` only during migration, and externalize state localization from DTO to i18n layer.
- `UserToken` DTO (`src/api/flaskr/service/common/dtos.py:43`)
  - Wrapper returning `{ userInfo, token }` payload after login/verification flows.
  - Refactor impact: ensure factory-generated credentials populate both `token` and normalized `UserInfo` plus issued credential metadata when applicable.
- `UserItemDTO` (`src/api/flaskr/service/user/admin.py:11`)
  - Admin list item view built on legacy `user_id`/`mobile`/`username` fields.
  - Refactor impact: rework to consume `user_bid`, surface display name from `user_users.nickname`, and drop direct `mobile` exposure in favor of credential lookup utilities.
- Responses via `make_common_response` (`src/api/flaskr/route/common.py:70`)
  - Wrap all user endpoints with `{"code": 0, "message": "success", "data": ...}` schema.
  - Refactor impact: continue using shared envelope but define explicit DTOs for new endpoints (e.g., credential lists) and update swagger registration accordingly.
- Admin plugin services (`src/api/flaskr/plugins/ai_shifu_admin_api/src/service/user/funcs.py`)
  - Reuse `UserInfo` for admin auth and profile management.
  - Refactor impact: provide adapter translating `UserInfo` to admin-specific view while sourcing data from `user_users` and aggregated credentials.

## Observations
- No dedicated repository abstraction; services query SQLAlchemy models directly.
- Redis is used alongside SQL tables for token and verification workflows (key prefixes defined in app config).
- New models `UserInfo` (`user_users`) and `AuthCredential` (`user_auth_credentials`) already exist but are not yet wired into business logic.
- Migration effort must cover both application services and auxiliary tooling (CLI commands, admin plugin, tests).

## Migration Strategy: user_auth_credentials
1. Generate `credential_bid` per record using `generate_id` utility (per provider instance).
2. Derive `user_bid` lookup from migrated `user_users` row (fallback to deterministic hash of legacy `user_id` during migration if needed).
3. Provider-specific handling:
   - **Phone (`phone`)**: include entries for non-empty `User.mobile`; normalize to E.164 if possible, `subject_id`/`identifier` identical; `subject_format=phone`; set `state=1202` when legacy `user_state >= USER_STATE_REGISTERED`.
   - **Email (`email`)**: lowercase before insert, `subject_format=email`; flag verified state using existing email verification flows; capture historical verification metadata in `raw_profile` (`{"verified_on": ..., "source": ...}` when available).
   - **WeChat (`wechat`)**: create up to two records per user: one for `user_open_id` with `subject_format=open_id`, another for `user_unicon_id` with `subject_format=unicon_id`; choose `identifier` as associated email/phone when present, otherwise reuse `subject_id`; embed original OAuth payload (`wx_openid`, `wx_unionid`, timestamps) in `raw_profile`.
   - **Google (`google`)**: migration placeholder—no historical data yet; ensure schema supports future inserts by keeping provider_name unique per subject.
   - **Other third-party providers**: skip during initial migration; design repo utilities to allow future replays without duplicating credentials.
4. Default `state` to `1202` for credentials that have passed verification flows, otherwise `1201`; `deleted=0`.
5. Wrap inserts in manageable batches (e.g., 500 users) to avoid long transactions; use SQLAlchemy bulk operations with explicit flush to monitor memory.
6. Guard against duplicates by checking existing `provider_name` + `identifier` before insert; log collisions for manual review.
7. Include `created_at`/`updated_at` timestamps mirroring source `user_info.created`/`updated` when available; fallback to `func.now()` otherwise.

## Migration Strategy: user_users
0. Base revision: leverage Alembic migration `6abcf5af2758_add_new_user_models` (down_revision `63a0479d46e3`) which creates `user_users` and `user_auth_credentials`; subsequent data migration will be issued as a new revision after schema deployment.
1. Source data from legacy `user_info` rows, iterating in deterministic batches (e.g., primary key asc).
2. For each record:
   - Derive `user_bid` from existing `user_id` (preserve UUID for continuity); maintain secondary map for quick lookup during credential migration.
   - Populate `nickname` from `username` when present, otherwise fallback to `name` or empty string.
   - Copy `avatar` from `user_avatar`; if missing, leave empty string.
   - Set `birthday` using `user_birth` when valid; fallback to `NULL` to avoid invalid default date values.
   - Normalize `language` via current helper (`get_user_language`) to enforce casing conventions.
   - Translate legacy `user_state` (0/1/2/3) to new constants (1101/1102/1103/1104) using mapping defined in `service.user.consts`.
   - Capture admin flags (`is_admin`, `is_creator`) for follow-up migration (e.g., dedicated admin table or profile entries); retain extract in migration audit logs so privilege data is not lost.
   - Set `deleted=0` for active users; evaluate legacy soft-deletion once policies are defined (currently none).
   - Copy `created_at`/`updated_at` from legacy `created`/`updated` timestamps; fallback to `func.now()` if null.
3. Write rows into `user_users` using bulk INSERT or SQLAlchemy bulk_save_objects with periodic flush/commit (e.g., every 500 users) to control transaction size.
4. Maintain audit log table or CSV exporting old `id` to new `user_bid` mapping for rollback and debugging.
5. After migration, update services to reference `user_users` via `user_bid`; keep compatibility layer translating legacy `user_id` where required until code refactor completes.

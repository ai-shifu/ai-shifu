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

## Legacy Credential Mapping Plan
| Legacy Source | New `provider_name` | `subject_id` | `subject_format` | `identifier` | Additional Notes |
| --- | --- | --- | --- | --- | --- |
| `User.mobile` (phone login) | `phone` | existing mobile number | `phone` | same as `subject_id` | mark verified users (`user_state >= USER_STATE_REGISTERED`) as `state=1202`; capture SMS verification history in `raw_profile` if available. |
| `User.email` (email login) | `email` | normalized email | `email` | same as `subject_id` | enforce lowercase normalization prior to insert; consider historic verification status from email flow. |
| `User.user_open_id` (WeChat/OpenID) | `wechat` (legacy) | stored open id | `wechat_openid` | fallback to linked email/mobile if present | preserve `wx` payload in `raw_profile`; treat as third-party credential pending factory support. |
| Future Google OAuth payload | `google` | Google subject (`sub`) | `google` | primary email from Google profile | persist full Google profile JSON in `raw_profile`; link to existing user via email/phone before new user creation. |
| Placeholder for other providers (Apple/Facebook) | `apple` / `facebook` | provider-specific subject | format per provider | email or unique account id | follow same data contract as Google once implemented; may require additional metadata columns later. |
- `user_users` (Model `UserInfo`, `src/api/flaskr/service/user/models.py:165`)
  - Business-keyed user record with `user_bid` (indexed), soft-delete flag, state enum (1101-1104), created/updated timestamps.
  - Lacks explicit SQLAlchemy relationships; future services must manage joins manually.
- `user_auth_credentials` (Model `AuthCredential`, `src/api/flaskr/service/user/models.py:188`)
  - Credential store keyed by `credential_bid` and `user_bid` (indexed) with provider metadata (`provider_name`, `subject_id`, `subject_format`, `identifier`).
  - Includes soft-delete, state flag (1201/1202), and `raw_profile` text column for provider payload storage.
  - No foreign key constraints; relies on application logic for referential integrity.

## Observations
- No dedicated repository abstraction; services query SQLAlchemy models directly.
- Redis is used alongside SQL tables for token and verification workflows (key prefixes defined in app config).
- New models `UserInfo` (`user_users`) and `AuthCredential` (`user_auth_credentials`) already exist but are not yet wired into business logic.
- Migration effort must cover both application services and auxiliary tooling (CLI commands, admin plugin, tests).

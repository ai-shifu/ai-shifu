# Backend: Add `user_identify` to `user_users`

Goal: Add a new column `user_identify` to table `user_users` (model: `UserInfo` in `src/api/flaskr/service/user/models.py`) to store either phone (for SMS verification) or email (for email/Google verification). The column must be indexed but NOT unique (business layer guarantees uniqueness).

Referenced flows (for setting value):
- Phone SMS verification: `src/api/flaskr/service/user/phone_flow.py::verify_phone_code`
- Email verification: `src/api/flaskr/service/user/email_flow.py::verify_email_code`
- Google OAuth: `src/api/flaskr/service/user/auth/providers/google.py::GoogleAuthProvider.handle_oauth_callback`

Current PR context:
- New user entity `user_users` already exists as `UserInfo` with `user_bid`, `nickname`, `avatar`, `birthday`, `language`, `state`, `deleted`, `created_at`, `updated_at`.
- Legacy `User` is still the primary source for auth, then synchronized to `UserInfo` via repository helpers.

Implementation plan

1) Model change
- Add `user_identify = Column(String(255), nullable=False, default="", index=True, comment="User identifier: phone or email")` to `UserInfo` in `src/api/flaskr/service/user/models.py`.
- Keep DB free of uniqueness constraints; enforce via business logic only.

2) Alembic migration
- Generate migration: `cd src/api && FLASK_APP=app.py flask db migrate -m "add user_identify to user_users"`.
- Ensure migration adds the column with an index (non-unique).
- Data backfill (online-safe):
  - For existing rows: join legacy `user_info` on `user_users.user_bid = user_info.user_id`.
  - Set `user_identify = lower(email)` if email is present; otherwise set to `mobile` (if present); otherwise fallback to `user_bid` (UUID).
- Downgrade path: drop index, then drop column.

3) Business logic updates
- Add a small repository helper (optional) `set_user_identify(user_bid: str, value: str)` to set/normalize and flush.
- Update phone flow to explicitly set phone:
  - In `verify_phone_code`, after syncing entity, set `user_entity.user_identify = phone` and flush.
- Update email flow to explicitly set email:
  - In `verify_email_code`, after syncing entity, set `user_entity.user_identify = normalized_email` and flush.
- Update Google OAuth to explicitly set email:
  - In `GoogleAuthProvider.handle_oauth_callback`, after syncing entity, set `user_entity.user_identify = email` and flush.
- Ensure no code path sets DB-level uniqueness; any cross-user dedupe remains in service layer.

4) Tests
- Add tests under `src/api/tests/service/user/`:
  - `test_phone_flow_sets_user_identify.py`: verify SMS flow sets `user_identify` to phone.
  - `test_email_flow_sets_user_identify.py`: verify email flow sets to normalized email.
  - `test_google_oauth_sets_user_identify.py`: mock Google profile and ensure value set to email.
- Include backfill verification (optional): create pre-existing users and run a short script or assert migration effects via an integration test if feasible.

5) Operational checklist
- Run: `cd src/api && pytest` and `pre-commit run -a`.
- Apply migrations locally: `FLASK_APP=app.py flask db upgrade`.
- Validate end-to-end by performing each login flow once and checking `user_users.user_identify`.

Acceptance criteria
- Column exists with index and no unique constraint.
- Phone verification sets `user_identify` to the phone used.
- Email/Google verification sets `user_identify` to the email used.
- Existing records have sensible backfilled values (email preferred over phone, lowercase email; fallback to user_bid/UUID).
- All tests pass and pre-commit hooks are clean.

Notes
- The service currently syncs legacy `User` → `UserInfo`. We set `user_identify` in the flow handlers to reflect the verification method used for that session.
- No API schema change is required unless consumers need to read `user_identify`. If needed, extend the relevant DTO/endpoint in a follow-up.

---

# Frontend Google OAuth integration (Cook Web)

Backend work landed in commits `c074c961`, `67d17a21`, and `073eadf0`, exposing `/api/user/oauth/google` and `/api/user/oauth/google/callback`. The next milestone is wiring the Cook Web frontend to the new provider.

## Feature configuration & documentation
- [x] Extend `src/cook-web/src/config/environment.ts` to recognize the `'google'` login method flag, surface a `googleOauthRedirect` fallback, and expose the values through `/api/config` so the backend remains the source of truth.
- [x] Document the required environment variables (`NEXT_PUBLIC_LOGIN_METHODS_ENABLED`, `NEXT_PUBLIC_DEFAULT_LOGIN_METHOD`, optional `NEXT_PUBLIC_GOOGLE_OAUTH_REDIRECT`) in `src/cook-web/src/config/ENVIRONMENT_CONFIG.md` and `README.md`.
- [x] Update sample env files (`src/cook-web/.env.example`, if present) to show how to enable Google login locally.

## API layer & auth utilities
- [x] Add `googleOauthStart` and `googleOauthCallback` entries to `src/cook-web/src/api/api.ts` and regenerate typed wrappers via `src/cook-web/src/api/index.ts`.
- [x] Create a focused helper in `src/cook-web/src/hooks` (e.g., `useGoogleAuth.ts`) that:
  - calls `googleOauthStart` with the computed redirect URI and optional state persistence,
  - exchanges `code`/`state` via `googleOauthCallback`,
  - funnels successful responses through `useUserStore.login`.
- [x] Ensure the helper reuses `useAuth.callWithTokenRefresh` semantics or equivalent error handling/toasts for consistency.

## UI flows
- [x] Add a dedicated Google sign-in button component under `src/cook-web/src/components/auth` (icon, copy, loading state) with translations (`auth.googleLogin`, `auth.googleLoginError`, etc.).
- [x] Update `src/cook-web/src/app/login/page.tsx` to:
  - surface the Google option when `'google'` is enabled in `environment.loginMethodsEnabled`,
  - trigger the helper on click (popup vs. full redirect decision documented),
  - gracefully fall back when the feature flag is off.
- [x] Create a callback handler route (e.g., `src/cook-web/src/app/login/google-callback/page.tsx`) that reads `code`, `state`, and optional `redirect` params, invokes the helper, drives loading/error UI, and then redirects to the intended page while stripping OAuth params from the URL.
- [x] Update terms acceptance UX if Google login must also require acknowledging the policies (align with `TermsCheckbox`).

## State management & persistence
- [x] Extend `src/cook-web/src/store/useUserStore.ts` to clear OAuth query parameters after login (`removeParamFromUrl`) and to handle Google-provided avatar/name defaults.
- [x] Ensure guest token bootstrap (`registerTmp`) still runs before starting the OAuth flow so outbound requests include a temporary token if required by the backend start endpoint.
- [x] Verify logout clears any Google-specific session storage (state cache) to avoid stale OAuth runs.

## Internationalization & assets
- [ ] Add English/Chinese translations for the new Google login strings in `src/cook-web/public/locales/en-US.json` and `zh-CN.json`.
- [ ] Provide an accessible label/aria description for the Google login button icon.

## QA & tooling
- [ ] Add a Cypress/Playwright e2e smoke (or update existing auth suite) that exercises the OAuth start flow behind a mock Google redirect.
- [ ] Add unit tests for the new hook (mocking API layer) to assert success/error paths and state updates.
- [ ] Validate the flow locally against the Flask backend: ensure `state` TTL handling works and the user lands in `/main` authenticated.
- [ ] Run `npm run lint`, `npm run test`, and project `pre-commit` hooks before merging.

## Roll-out checklist
- [ ] Coordinate with backend to set `GOOGLE_OAUTH_REDIRECT_URI` to the new Cook Web callback URL in each environment.
- [ ] Update release notes / internal docs to announce Google login availability.

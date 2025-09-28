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
- [ ] Add a dedicated Google sign-in button component under `src/cook-web/src/components/auth` (icon, copy, loading state) with translations (`auth.googleLogin`, `auth.googleLoginError`, etc.).
- [ ] Update `src/cook-web/src/app/login/page.tsx` to:
  - surface the Google option when `'google'` is enabled in `environment.loginMethodsEnabled`,
  - trigger the helper on click (popup vs. full redirect decision documented),
  - gracefully fall back when the feature flag is off.
- [ ] Create a callback handler route (e.g., `src/cook-web/src/app/login/google-callback/page.tsx`) that reads `code`, `state`, and optional `redirect` params, invokes the helper, drives loading/error UI, and then redirects to the intended page while stripping OAuth params from the URL.
- [ ] Update terms acceptance UX if Google login must also require acknowledging the policies (align with `TermsCheckbox`).

## State management & persistence
- [ ] Extend `src/cook-web/src/store/useUserStore.ts` to clear OAuth query parameters after login (`removeParamFromUrl`) and to handle Google-provided avatar/name defaults.
- [ ] Ensure guest token bootstrap (`registerTmp`) still runs before starting the OAuth flow so outbound requests include a temporary token if required by the backend start endpoint.
- [ ] Verify logout clears any Google-specific session storage (state cache) to avoid stale OAuth runs.

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

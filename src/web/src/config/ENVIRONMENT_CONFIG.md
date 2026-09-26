# Frontend Configuration Reference

## Ownership And Loading

The frontend has two configuration requests with different owners:

| Request               | Owner                                    | Response and use                                                                                |
| --------------------- | ---------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `/api/config`         | Next.js (`src/app/api/config/route.ts`)  | Only `apiBaseUrl`; locates the backend.                                                         |
| `/api/runtime-config` | Flask (`src/api/flaskr/route/config.py`) | Public login, payment, branding, legal, and analytics settings in the shared response envelope. |

[initializeEnvData.ts](../lib/initializeEnvData.ts) loads the backend payload
into [envStore.ts](../store/envStore.ts). Components consume that store.
[environment.ts](environment.ts) supplies bootstrap defaults; it is not a second
browser configuration service. A successful Next `/api/config` fallback proves
only backend-location discovery, not that runtime settings loaded successfully.

## Frontend Environment

For local setup, follow the [frontend README](../../README.md). Put the
backend origin in `src/web/.env.local`, without an `/api` suffix:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:5800
```

| Variable                            | Read by                           | Timing and fallback                                                                                     |
| ----------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_BASE_URL`          | Next server and browser bootstrap | Server runtime takes precedence over the browser build value; unset resolves to an empty base.          |
| `NEXT_PUBLIC_LOGIN_METHODS_ENABLED` | Browser bootstrap                 | Build-time fallback, default `phone`; backend runtime settings replace it.                              |
| `NEXT_PUBLIC_DEFAULT_LOGIN_METHOD`  | Browser bootstrap                 | Build-time fallback, default `phone`; invalid or disabled values fall back to the first enabled method. |

Next server initialization can also read unprefixed login, branding, legal URL,
redirect, and currency defaults through `environment.ts`. Payment channels
bootstrap from fixed defaults; `PAYMENT_CHANNELS_ENABLED` is read only by Flask.
Those server defaults do not replace the Flask configuration consumed by
browser initialization. Configure the backend for those product capabilities.
Do not add `NEXT_PUBLIC_` prefixes to backend variables or put secret keys in
the frontend environment. Restart the affected local process after environment
changes; rebuild when changing a browser build-time fallback.

On custom domains the Next route may return an empty base so the browser uses
same-origin `/api` ingress. Localhost frontend/backend origins retain the
configured backend base even when their ports differ. See
[route-utils.ts](../app/api/config/route-utils.ts) and its tests for the host
comparison contract. The development proxy is described in the frontend README.

## Backend Runtime Settings

Configure these in `src/api/.env` for manual development, or the backend
service environment for deployment. The config service may supply persisted
settings, and entitled teacher/domain branding can override global values.
The public response is an allowlisted projection, not an environment dump.

| Capability  | Backend configuration                                                                           | Runtime output                                                                    |
| ----------- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Login       | `LOGIN_METHODS_ENABLED`, `DEFAULT_LOGIN_METHOD`                                                 | `loginMethodsEnabled`, `defaultLoginMethod`                                       |
| WeChat      | `WECHAT_APP_ID` plus backend OAuth credentials                                                  | `wechatAppId`, derived `enableWechatCode`; custom domains disable this OAuth flow |
| Billing     | `BILL_ENABLED`, `BILL_CREDIT_PRECISION`                                                         | `billingEnabled`, `billingCreditPrecision`                                        |
| Payments    | `PAYMENT_CHANNELS_ENABLED`, `STRIPE_ENABLED`, `STRIPE_PUBLISHABLE_KEY`, `PAY_ORDER_EXPIRE_TIME` | Public channel, Stripe, and checkout-expiry settings                              |
| Course tree | `UI_ALWAYS_SHOW_LESSON_TREE`                                                                    | `alwaysShowLessonTree`                                                            |
| Branding    | `LOGO_WIDE_URL`, `LOGO_SQUARE_URL`, `FAVICON_URL`                                               | `logoWideUrl`, `logoSquareUrl`, `faviconUrl`                                      |
| Navigation  | `HOME_URL`, `CONTACT_US_URL`, `OFFICIAL_SITE_URL`                                               | `homeUrl`, `contactUsUrl`, `officialSiteUrl`                                      |
| Analytics   | `ANALYTICS_UMAMI_SCRIPT`, `ANALYTICS_UMAMI_SITE_ID`                                             | `umamiScriptSrc`, `umamiWebsiteId`                                                |
| Debug UI    | `DEBUG_ERUDA_ENABLED`                                                                           | `enableEruda`                                                                     |
| Prices      | `CURRENCY_SYMBOL`, `DEFAULT_SHIFU_PRICE`, `MIN_SHIFU_PRICE`                                     | `currencySymbol`, `defaultCoursePrice`, `minimumPaidCoursePrice`                  |
| Legal links | `LEGAL_AGREEMENT_URL_<LOCALE>`, `LEGAL_PRIVACY_URL_<LOCALE>`                                    | Locale-indexed `legalUrls`                                                        |

Legal suffixes use uppercase locale codes with underscores, for example
`EN_US` and `ZH_CN`. Supported locales are defined by
[locales.json](../../../i18n/locales.json); the backend DTO and route enumerate
the supported legal fields. Missing configuration is returned as an empty URL;
UI fallback behavior belongs to the legal-link components.

`HOME_URL` defaults to `/admin` and accepts relative or absolute destinations.
Teacher branding can override it. An explicit `/c/<shifu_bid>` course request
keeps its course target. Private payment and OAuth credentials stay on the
backend; a publishable Stripe key is the public exception listed above.

The former `NEXT_PUBLIC_WECHAT_*`, `NEXT_PUBLIC_UI_*`,
`NEXT_PUBLIC_ANALYTICS_*`, `NEXT_PUBLIC_DEBUG_ERUDA_ENABLED`, and
`NEXT_PUBLIC_STRIPE_*` settings have no active readers for these capabilities.
Use the backend names in the table instead.

## Verification

From `src/web`, run the configuration-parser and Next configuration-route tests:

```bash
npm test -- --runInBand --runTestsByPath src/config/environment.test.ts src/app/api/config/route.test.ts
```

`initializeEnvData.ts` has no dedicated test suite. These tests do not verify
its backend payload mapping, fallback behavior, or store updates; changes to
that bootstrap path need focused regression coverage.

In a local running setup, inspect the two requests separately: Next should
return the expected backend base; Flask should return the configured public
values. Confirm the store-driven UI follows that payload. Do not treat the
bootstrap defaults or a successful frontend page load as proof of backend
configuration delivery.

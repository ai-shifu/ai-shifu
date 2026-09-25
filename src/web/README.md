# Web Frontend

AI-Shifu's Next.js frontend serves learners, teachers, and operators.
It shares translations with the backend under `../i18n/` and uses the npm
lockfile in this directory.

## Local Development

Use Node.js 22.16.0, as pinned in [package.json](package.json). Start the
backend on port 5800 using the
[local installation steps](../../INSTALL_MANUAL.md#step-5-manual-installation-development).

In a second terminal, run from the repository root:

```bash
cd src/web
npm ci
cp -n .env.example .env.local
```

Set the backend origin in `.env.local`, keeping any existing local settings:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:5800
```

Use an origin without an `/api` suffix. Then start the frontend:

```bash
npm run dev -- --hostname 127.0.0.1
```

Bind the frontend to loopback as well as the backend: its development proxy
can reach an API configured with the Docker template's demo authentication.

Open [http://localhost:3000](http://localhost:3000). Routes live under
`src/app/`; the authoring and operator entry is `/admin`, and the legacy
`/main` entry redirects there.

During `npm run dev`, Next.js rewrites backend `/api/*` requests to the
configured API origin, defaulting to `http://127.0.0.1:5800`. This proxy is
disabled for production builds. The repository's Docker Compose setup supplies
the production ingress; see the [installation manual](../../INSTALL_MANUAL.md)
for deployment.

## Runtime And Authentication Configuration

The frontend's `/api/config` route returns only `apiBaseUrl`. The backend
`/api/runtime-config` endpoint supplies login methods and other runtime
settings. See the [environment reference](src/config/ENVIRONMENT_CONFIG.md)
for the full configuration contract.

To enable Google login, configure the backend environment:

```bash
LOGIN_METHODS_ENABLED=phone,google
DEFAULT_LOGIN_METHOD=google
```

Also configure `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` on
the backend. Register the frontend callback URL with Google; for this local
setup it is `http://localhost:3000/login/google-callback`. Set the backend's
`GOOGLE_OAUTH_REDIRECT_URI` to that exact URL to make the callback explicit.
Without that override, the backend uses `HOST_URL` or the request origin plus
`/login/google-callback`. Keep the client secret on the backend.

The frontend variables `NEXT_PUBLIC_LOGIN_METHODS_ENABLED` and
`NEXT_PUBLIC_DEFAULT_LOGIN_METHOD` in `.env.example` are build-time fallbacks;
they do not enable backend authentication methods. Restart the affected dev
servers after changing environment settings.

## Validation

Run these commands from `src/web/`, choosing the checks relevant to the change:

| Check              | Command                                        |
| ------------------ | ---------------------------------------------- |
| Focused unit tests | `npm test -- --runInBand path/to/file.test.ts` |
| Unit suite         | `npm run test:ci`                              |
| Type checking      | `npm run type-check`                           |
| Lint               | `npm run lint`                                 |
| Formatting         | `npm run format:check`                         |
| Browser tests      | `npm run test:e2e`                             |

Browser tests expect a running Docker dev stack at `http://localhost:8080`
by default; `AI_SHIFU_BASE_URL` overrides the target. They do not start the
stack. Install the browser once with `npx playwright install chromium`.
To run only the smoke project and its authentication setup, use
`npm run test:e2e -- --project=runtime-harness-smoke`.
Follow the [repository reliability guide](../../docs/RELIABILITY.md)
when diagnosing smoke failures.

## Contributor References

- [Frontend collaboration rules](AGENTS.md)
- [Frontend workflow skills](SKILL.md)
- [Engineering baseline](../../docs/engineering-baseline.md)
- [Product localization guide](../../docs/references/i18n.md)
- [Product analytics contracts](../../docs/references/frontend-product-analytics.md)

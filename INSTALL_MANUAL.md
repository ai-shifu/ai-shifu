# INSTALL FROM SOURCE CODE STEP BY STEP

## Prerequisites

### Architecture Overview

AI-Shifu consists of two main components:

```bash
src/
├── api/          # Backend API service (Flask/Python)
└── web/          # Frontend (Next.js)
```

- **api**: Backend API service built with Flask
- **web**: Frontend for creating, managing, and learning courses, built with Next.js

### Required Tools and Services

- **Python 3.11** for the backend, matching the Docker image
- **Node.js 22.23.4** for the frontend
- **MySQL 8.0** for database storage, matching the Compose stack
- **Redis 7** for caching, Live session coordination, and background jobs
- **FFmpeg** for audio processing when running the backend outside Docker
- **Docker & Docker Compose** (recommended for easy deployment)

### Required LLM Configuration

Configure at least one LLM provider and map `LLM_MODEL_1_ID` to a text model served by that provider. `LLM_MODEL_1_ID` is required and has no default. `LLM_MODEL_1_NAME` is optional; an omitted or blank name displays the configured model ID. Supported providers include:

- **OpenAI** API Key
- **Baidu ERNIE** API credentials
- **ByteDance Volcengine Ark** API Key
- **SiliconFlow** API Key
- **Zhipu GLM** API Key
- **DeepSeek** API Key
- **Alibaba Qwen** API Key

### Optional Services

- **Alibaba Cloud OSS** for file storage
- **Alibaba Cloud SMS** for phone verification
- **Langfuse** for LLM tracking
- **Email SMTP** for email verification

## Installation Steps

### Step 1: Clone the Repository

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
cd ai-shifu
```

### Step 2: Set Up Environment Variables

Create private configuration from the full template (Python 3.10 or newer on
a POSIX host is required; no Python packages need to be installed):

```bash
python3 scripts/prepare_env.py
```

For Docker-based workflows, configure at least one LLM provider key (for example `OPENAI_API_KEY`, `ERNIE_API_KEY` or `BIGMODEL_API_KEY`) and set `LLM_MODEL_1_ID` to a text model ID available through that provider. `LLM_MODEL_1_NAME` is optional; omit it or leave it blank to display the configured model ID. The template intentionally leaves both values empty, but only the ID is required. Database defaults match the bundled services; review security settings before production use.

### Step 3: Configure Environment Variables

Edit `docker/.env` and configure the required settings.

#### Required Variables (MUST be configured)

These variables are essential for the application to run:

1. **Database Connection**
   - `SQLALCHEMY_DATABASE_URI`: MySQL connection string
   - Bundled Compose default: `mysql://root:ai-shifu@ai-shifu-mysql:3306/ai-shifu?charset=utf8mb4`
   - For manual installation, use the local connection settings in Step 5.2.

2. **Security (automatically provisioned)**
   - `SECRET_KEY`: signing and encryption key, generated once by the installer
   - Keep the saved value for the lifetime of the instance, including upgrades
   - Run the installer separately for independent dev/test/prod environments

3. **LLM Provider** (at least one required)
   - Choose from: OpenAI, ERNIE, ARK, SiliconFlow, GLM, DeepSeek, Qwen
   - See `docker/.env.example.full` for specific provider configurations

4. **Numbered Course Models**
   - `LLM_MODEL_1_ID`: required physical text model ID served by the configured provider; no default. Model 1 is always the course default.
   - `LLM_MODEL_<1..9>_NAME`: optional display name, shared across interface languages. Omitted, empty or whitespace-only names display the corresponding configured model ID.
   - Configure optional `LLM_MODEL_2_ID` through `LLM_MODEL_9_ID` to add options. A nonblank ID enables a number even without a name; a name without an ID does not. Gaps are allowed; identifiers never shift when another number is removed.
   - A configured provider failure is an error, not a reason to silently switch models. Live voice remains separate.

#### Configuration Reference

- `docker/.env.example.full`: canonical template that lists every environment variable with defaults, descriptions, and grouping (Database, Redis, Auth, LLM, etc.). The installer creates `docker/.env` from it and fills only its empty `SECRET_KEY` placeholder. Configure other settings in the resulting file.
- **Docker reminder**: configure a provider API key and `LLM_MODEL_1_ID` for latest-image, pinned-release and local-development Compose modes. Update database/Redis URLs if you are not using the bundled services.

#### Important Notes

- All sensitive values (API keys, passwords) should be kept secure
- Never commit `.env` files to version control
- For production deployments, use environment-specific configurations
- Refer to the example files for detailed explanations of each variable

#### Secret key preservation and recovery

- The installer automatically generates and saves an independent `SECRET_KEY`;
  no manual key entry is required.
- Securely back up `.env` and reuse it across restarts, upgrades, and all
  replicas.
- Keep existing keys. If configuration is lost, restore the original file
  instead of generating a new key; changing it invalidates sessions and can
  make encrypted configuration unreadable.

#### Trusted reverse proxies and client IPs

The backend ignores `X-Forwarded-For` unless the immediate connection comes
from a network listed in `TRUSTED_PROXY_CIDRS`. The backend default is empty
because proxy addresses differ between deployments. The bundled Compose files
instead place nginx on a dedicated network with a stable address and trust only
that address. If `AI_SHIFU_NGINX_IP` or `AI_SHIFU_PROXY_SUBNET` is overridden,
set both consistently and update `TRUSTED_PROXY_CIDRS` to the nginx address as
a single-host `/32`. Custom deployments should list only exact nginx and CDN
egress CIDRs, separated by commas; do not trust an entire Docker or private
network merely for convenience.

Nginx must continue appending its TCP peer with
`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`. A CDN in front
of nginx must overwrite or correctly append its own forwarding chain, and its
egress CIDRs must also be listed. The backend walks the chain from right to
left and selects the first untrusted address. Invalid chains fall back to the
immediate TCP peer.

Keep the API port private. The bundled production Compose files expose only
nginx; the development API port is bound to loopback. If a custom deployment
publishes the API directly, firewall it so clients cannot bypass the trusted
proxy path. Verify the resolved address in request logs before enabling IP
security thresholds.

#### Optional Gemini Live Voice Follow-Up

Gemini Live is disabled by default. Leave `GEMINI_LIVE_ENABLED=false` until
the browser-direct flow has been verified in the target environment. To expose
the allowlisted Live follow-up model, configure a valid `GEMINI_API_KEY`, keep
Redis available for authenticated session bindings and capacity leases, and
then set:

```bash
GEMINI_LIVE_ENABLED=true
```

The supported Live follow-up model is `gemini-3.8-live` (Gemini 3.8 Live).
The Gemini model discovery response must advertise `bidiGenerateContent` for
this model. Earlier Live models and the Extended Thinking variant are not
supported; saved courses must select `Gemini Live` in their follow-up settings.
Known unsupported Live selections remain disabled and cannot invoke text/SSE
generation or obtain a Live credential.
Live session setup omits `thinkingConfig`, which this model does not support.

Live readiness is separate from ordinary HTTP health. On startup, every
enabled API worker schedules a single background task to resolve the effective
(environment or DB-backed) flag and
initializes the shared Redis recovery guard without minting
a credential. Redis eviction policies are not an admission prerequisite.
`noeviction` is recommended for retaining credential-risk records: with an
evicting policy, records may disappear before Google credentials expire,
undercounting outstanding credentials or interrupting ownership. Capacity
guarantees depend on record retention. A missing accounting marker or a
changed Redis run ID starts the full shared 15-minute safety window; repeated
worker starts and probes do not reset or shorten it. Do not delete accounting
records to bypass this window.
If startup config/Redis lookup fails (including a DB lookup falling back to
disabled), one daemon task per API worker retries every 30 seconds,
at most 20 times. It stops once the marker is initialized, even while warming;
an explicit environment-off switch completes the first attempt without retries.
Longer outages still
require the deployment readiness gate below; retries do not bypass it.
Gunicorn preload skips preparation in the master; the existing `post_fork`
hook initializes it after per-worker connection pools and tracing are reset.
Initialization is idempotent per process, including non-preloaded app factories.
The Celery bootstrap creates its Flask app with `serving_http=False`, recorded
before route registration. That process-local role skips Live preparation in
both the prefork parent and queue/beat workers; it does not change rollout flags
or start an unnecessary readiness thread in Celery children.
Neither the initial lookup nor retries run on the HTTP/startup thread. Config
cache reads use an isolated Redis client with one-second connect/read timeouts;
the existing DB lookup stays within that one background task. A stalled DB
operation is not joined and does not create replacement tasks or block workers.

Before announcing Live availability, query
`GET /api/learn/live-follow-up/readiness` through the normal authenticated API
transport and require `data.status == "ready"`. Other bounded statuses are
`warming`, `unavailable`, and `disabled`; `retry_after_ms` is a suggested probe
interval, not a credential expiry. The probe allocates no user/session capacity
and reads only explicit overrides or bounded cached configuration, with no DB
fallback; a cold/missing config cache is `unavailable` until background lookup
or the existing config service populates it. A cache miss after startup
schedules repopulation in the same single worker-local task slot, never inline.
An active (including stalled) task is not replaced, and new task starts have a
30-second cooldown after completion or start failure. Each task retains the
initial-plus-20 retry budget. Capability validation reuses the
same resolved flag rather than performing another shared-cache lookup.
Confirmed database absence is cached as separate metadata for 24 hours, so
the supported default-off state settles as `disabled`; transient database
failures never create this marker. The normal config service's positive cache
writes take precedence immediately when a flag is created or updated. The probe
returns no credentials or Redis identifiers. Startup probing uses bounded
Redis socket waits; a Live outage must not fail ordinary `/health` or text
follow-ups. The original follow-up panel also probes before enabling new Live
input and refreshes while unavailable, without automatically connecting,
requesting microphone permission, or exposing an internal countdown. Mint-time
admission still enforces the same guard atomically after readiness succeeds.
The probe also requires the allowlisted model's discovered Bidi capability;
a disabled/missing Gemini provider, absent model, or text-only capability returns
`unavailable` even when Redis is ready. Discovery retains the existing startup
lifecycle: after correcting provider configuration or a startup ListModels
failure, restart API workers and verify readiness. Probes do not call Gemini.

The API mints a one-use, short-lived Gemini credential constrained to the
selected model, voice, and server-built prompt. The browser then opens the
Gemini Live WebSocket directly, so the AI-Shifu ingress does not need a
WebSocket Upgrade route. Production still needs HTTPS for microphone access,
and the browser must be able to reach `generativelanguage.googleapis.com`.
The server must also reach the token-creation API. If `GEMINI_API_URL` is set,
token creation reuses that HTTPS base URL, including any proxy path prefix,
and appends `/v1beta/auth_tokens`; an existing terminal `/v1beta` is reused
instead of duplicated. If unset, token creation uses Google's official API.
Only configure a trusted proxy because it receives the API key and private
course context. This setting never changes the browser's Gemini WebSocket
destination. Token requests do not follow redirects or fall back to another
host when the configured endpoint fails.
Disable the flag to roll back Live without changing courses that use text
follow-up models.

### Step 4: Build Latest Docker Images & Start the Stack

1. Ensure `docker/.env` contains a provider API key and `LLM_MODEL_1_ID` mapped to a configured text model. `LLM_MODEL_1_NAME` is optional. For an existing database, complete [Upgrading to numbered models](#upgrading-to-numbered-models) before enabling traffic.
2. Build the backend and frontend images tagged as `:latest` from the repo root:

```bash
docker build -t aishifu/ai-shifu-api:latest -f src/api/Dockerfile .
git rev-parse HEAD > src/web/.app-build-sha
docker build -t aishifu/ai-shifu-web:latest -f src/web/Dockerfile .
```

The Git-ignored marker records the source revision before Docker excludes the
Git directory. The user menu can then show the frontend release and commit.

3. Start the containers with the compose bundle that tracks the `:latest` tags:

```bash
cd docker
docker compose -f docker-compose.latest.yml up -d
```

`docker-compose.latest.yml` uses images tagged `:latest`, including local
builds. That tag does not guarantee a cached image is current: run
`docker compose -f docker-compose.latest.yml pull` before `up -d` when you
want to replace local images with the published ones. For a fresh pinned
release installation, use the following instructions instead.

#### Fresh pinned-release installation

Requires Docker Compose 2.24.4+. After creating `docker/.env` in Step 2,
run this command from `docker/` to start the pinned images:

```bash
docker compose -f docker-compose.yml -f docker-compose.secret-key.yml up -d
```

Keep both `-f` options on every Compose command for this new deployment,
including restarts and upgrades.

Existing pinned deployments must retain their original commands and effective
key until a deliberate migration. Adding the overlay can activate a previously
ignored `.env` value and break existing sessions or encrypted configuration.

### Step 5: Manual Installation (Development)

This section covers manual installation for development purposes or when you need more control over the setup.

#### Step 5.1: Set Up Database Services

Start MySQL and Redis services on your local machine or use Docker:

```bash
# Using Docker for databases only
docker run -d --name mysql -p 127.0.0.1:3306:3306 -e MYSQL_ROOT_PASSWORD=ai-shifu -e MYSQL_DATABASE=ai-shifu mysql:8.0
docker run -d --name redis -p 127.0.0.1:6379:6379 redis:7-alpine
```

#### Step 5.2: Configure Environment for Local Development

For a fresh local setup, provision a separate configuration in the backend
directory. Run this from the repository root; existing configuration is
validated and preserved.

```bash
python3 scripts/prepare_env.py --output src/api/.env
```

Verification bypass is disabled by default, including for `ENV=development`.
The API and frontend commands below bind to loopback. Before making the
application remotely accessible, configure a secure HTTPS endpoint and keep the
generated `SECRET_KEY` unchanged. The first administrator uses a phone number
or email address and a password. SMS, SMTP and OAuth are optional for subsequent
learner login or notifications.
See [First Administrator Setup](#first-administrator-setup) and
[Local Demo Login](#local-demo-login).

Edit `src/api/.env`, retaining the provider key and required `LLM_MODEL_1_ID`
mapping. Replace Docker service hostnames with the addresses of your local
services:

```bash
# Update database URLs for local services
SQLALCHEMY_DATABASE_URI="mysql://root:ai-shifu@127.0.0.1:3306/ai-shifu?charset=utf8mb4"
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
FLASK_APP=app.py
```

#### Step 5.3: Start Backend API

```bash
# From the repository root
cd src/api

# Install Python dependencies
pip install -r requirements.txt

# Initialize a fresh installation, or migrate an existing one without reopening setup
flask console prepare-installation

# Start the API server
gunicorn -w 4 -b 127.0.0.1:5800 'app:app' --timeout 300 --log-level debug
```

Complete `prepare-installation` before starting any worker or beat process;
their application plugins may also initialize database state. Compose waits
for the API to finish its preparation and begin listening before starting those
Python processes. For the development stack, the known migration-residue repair
runs inside `prepare-installation --repair-development` so the same process
retains the original fresh-schema snapshot.

The HTTP server does not process queued jobs. For background billing, TTS,
and user tasks, open another terminal with the same Python environment and
`src/api/.env`, then run:

```bash
cd src/api
python -m celery -A celery_app:celery_app worker --loglevel info
```

For scheduled billing jobs, run one beat scheduler in another terminal:

```bash
cd src/api
python -m celery -A celery_app:celery_app beat --loglevel info
```

The bundled Compose stack starts these processes as separate services.

Verify the local worker connection and registered task names from `src/api`:

```bash
python -m celery -A celery_app:celery_app inspect ping
python -m celery -A celery_app:celery_app inspect registered
```

A `pong` proves worker connectivity, not successful business processing. On a
local disposable dataset, trigger the background operation being developed and
check both its worker `received` / `succeeded` messages and the expected saved
result. For scheduled jobs, also verify the single beat process dispatches the
due task. HTTP health and an idle worker alone do not validate that path.
The isolated Celery configuration and entrypoint tests cover wiring without
sending billing tasks to a running environment.

#### Step 5.4: Start Frontend

```bash
# In a second terminal, from the repository root
cd src/web
# Install the versions pinned in package-lock.json
npm ci

# For a fresh setup; preserve an existing local configuration
cp -n .env.example .env.local
```

Set the backend origin in `src/web/.env.local` (without an `/api` suffix):

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:5800
```

```bash
# Start development server
npm run dev -- --hostname 127.0.0.1
```

The frontend is available at `http://localhost:3000`. See the [frontend README](src/web/README.md) for
authentication configuration and frontend validation commands.

#### Step 5.5: Install the Code-Quality Hooks (Contributors)

If you plan to commit changes, install the lefthook git hooks so the same
pre-commit checks that run in CI also run locally. **Without this step the
checks are silently skipped on commit.**

Install lefthook for your platform.

macOS (Homebrew):

```bash
brew install lefthook
```

Linux or Windows (npm):

```bash
npm install -g @evilmartians/lefthook
```

Then install the remaining development tools from the repository root:

```bash
# From the repository root
python -m pip install ruff==0.17.3 commitizen==4.16.2 pre-commit-hooks==6.0.0 markdown-it-py==4.0.0
(cd src/web && npm ci)   # provides prettier + eslint
lefthook install

# Verify the toolchain (reports anything missing and how to install it)
python scripts/check_dev_tools.py
```

## Upgrading to numbered models

This applies to latest-image, pinned-release, development Compose and manual installations.

1. Configure provider credentials plus `LLM_MODEL_1_ID`. Add optional model IDs
   for numbers 2-9 as needed. Set optional names to customize labels; omitted or
   blank names display their configured model IDs. Remove the obsolete `LLM_ALLOWED_MODELS`,
   `LLM_ALLOWED_MODEL_DISPLAY_NAMES` and the old fixed-level model variables; they are no longer read.
2. This change requires no database migration, course-data cleanup or cleanup report.
3. Deploy matching API/workers and web. Verify a legacy course uses model 1 and
   that changing unrelated course settings preserves its saved model value.
4. Check invocation records for the original selection, effective number,
   physical model and fallback reason. Billing uses the actual invoked model.

Blank selections, old model IDs, old fixed-level aliases and unconfigured numbers use
model 1 without modifying course rows. If a removed number is configured again,
courses still referencing it automatically resume using it. Do not reuse numbers
without considering those references. Existing physical-model callers and Live
voice follow-up retain their separate contracts.

See the [numbered-model deployment runbook](docs/exec-plans/completed/numbered-course-models.md#deployment-runbook).
Do not roll back to a build that treats newly saved numeric choices as physical IDs.

## Upgrading existing profile-onboarding prompts for Spanish

When upgrading an installation that already saved the profile-onboarding
assistant prompt, run the Spanish prompt backfill from the upgraded API runtime
before exposing `es-ES` in the learner UI. The runtime needs database and LLM
access. For the Docker Compose installation above, run from the repository root:

```bash
cd docker
docker compose -f docker-compose.latest.yml exec -T ai-shifu-api python scripts/backfill_profile_onboarding_assistant_prompts.py
docker compose -f docker-compose.latest.yml exec -T ai-shifu-api python scripts/backfill_profile_onboarding_assistant_prompts.py --apply
```

For a source-checkout installation, run from the repository root instead:

```bash
cd src/api
python scripts/backfill_profile_onboarding_assistant_prompts.py
python scripts/backfill_profile_onboarding_assistant_prompts.py --apply
```

The first command previews whether a prompt is missing; the second generates
and publishes it, also filling any other missing supported locales in the
saved map. `already_present` is a successful no-op. If generation or a
concurrent operator edit fails, the saved configuration stays unchanged; rerun
after resolving the error. See the
[script notes](src/api/scripts/README.md)
for the other statuses. This is an explicit rollout step; database migrations
do not call the LLM.

## Troubleshooting

### Common Issues

1. **Database Connection Failed**
   - Ensure MySQL is running and accessible
   - Check database credentials in `.env`
   - Run `flask console prepare-installation` to initialize or migrate tables

2. **Redis Connection Failed**
   - Ensure Redis is running and accessible
   - Check Redis configuration in `.env`

3. **LLM API Errors**
   - Verify API keys are correct
   - Check API base URLs
   - Ensure the model name matches your provider
   - If startup reports missing `LLM_MODEL_1_ID`, configure that binding; provider credentials alone are insufficient. Missing `LLM_MODEL_1_NAME` does not block startup; it displays the configured model ID

4. **Frontend Build Failures**
   - Ensure Node.js version is 22.23.4
   - Reinstall the locked dependencies from `src/web`: `npm ci`
   - Check for environment variable issues

5. **Pre-commit Hooks Not Running / "command not found"**
   - Make sure you ran `lefthook install` once in this clone
   - Run `python scripts/check_dev_tools.py` to see which tools are missing and how to install them

### Log Files

- API logs: Check terminal/container output and `LOGGING_PATH`, which defaults
  to `logs/ai-shifu.log` relative to the backend's working directory
  (`src/api/logs/ai-shifu.log` for the manual commands above).
- Frontend logs: Check browser console or terminal output

## Access the Application

### Manual Installation

- Frontend: `http://localhost:3000` (or configured `PORT`)
- Course authoring and administration: `http://localhost:3000/admin`
- API: `http://localhost:5800`

### First Administrator Setup

This flow requires API and Web images containing the first-run setup feature.
Rebuild from the matching source or pull a published release containing it;
cached `:latest` images and older pinned releases do not acquire new commands
by changing the Compose file. Pinned Compose keeps its image tags and uses the
legacy migration command only when an older image lacks the feature. It never
falls back after a new preparation command fails.

Normal Compose startup runs `flask console prepare-installation`. It captures
whether the schema is genuinely new before applying migrations. New instances
start in pending setup; existing or unknown schemas remain closed even if user
tables are empty. Restarting, clearing Redis or deleting users never reopens
completed initialization.

For a fresh Docker installation, run this from `docker/` on the server:

```bash
docker compose -f docker-compose.latest.yml exec ai-shifu-api \
  flask console setup-code --origin http://localhost:8080
```

Open `http://localhost:8080/admin` (or `/setup`), paste the console code and
enter a phone number or email address and choose a password. The code expires
after 20 minutes, works once and is bound to the exact selected origin. Reissuing a
code invalidates the previous one. Keep it out of URLs and shared logs. The
identifier is not verified by setup; SMTP, SMS and OAuth services are not
required. The account receives administrator and teacher permissions plus the
bundled demo course where applicable.

For a manual development install with Web on port 3000, run
`flask console setup-code --origin http://localhost:3000` from `src/api` instead.
For a remote browser use your exact HTTPS origin, such as the origin configured
for your deployment, in `--origin`. Plain public HTTP is not supported by the
setup/local-login forms; use HTTPS or access loopback through an SSH tunnel.

After setup, use `/admin-login` with the same phone/email identifier and password.
This entry is available independently of learner `LOGIN_METHODS_ENABLED`; configure learner
SMS/email/Google sign-in later as needed. Setup creates a normal account and a
standard password credential; the administrator role controls access to the
administrator area. Setup does not verify contact ownership or fabricate a
verified phone/email credential. Use a phone number or email address you control:
after you configure contact verification, normal verification-code login and
password recovery refer to this same administrator account. An existing account
with the requested identifier is not overwritten, merged or promoted by setup.
Existing administrators keep their original login
methods during upgrade, and ordinary new user registration does not claim the
administrator role on a managed installation.

For a headless installation, use the same initialization service directly:

```bash
docker compose -f docker-compose.latest.yml exec ai-shifu-api \
  flask console create-admin
```

The command prompts for a phone/email identifier and a hidden, confirmed
password. For local administrator recovery, run:

```bash
docker compose -f docker-compose.latest.yml exec ai-shifu-api \
  flask console reset-admin-password --identifier owner@example.com
```

Enter the account's actual login identifier in place of `owner@example.com`.
Recovery prompts for a hidden new password and revokes the previous sessions. It does not reopen
Web setup. An existing installation can explicitly create its first local
administrator through the server-console command without replacing existing
accounts or demo ownership. For development Compose, replace the file with
`docker-compose.dev.yml` and the service with `ai-shifu-api-dev`.

Identifiers are trimmed; email addresses are case-insensitive and preserve dots
and plus-tags. Email identifiers are limited to 254 characters. Phone numbers
use the application's current mainland-China format: 11 ASCII digits beginning
with `1`, optionally prefixed by `+86`. This does not add international SMS
support. Standalone usernames cannot create new administrators. Accounts created
with the earlier preview's username design retain login and console recovery
compatibility; use the old name as the identifier for those existing accounts.
The forward migration converts preview `local_password` credentials to the
existing `password` type while preserving password hashes, account IDs and roles.
Contact-based preview accounts adopt their contact as the normal account
identity. The migration checks all bindings and contact collisions before
conversion; a collision stops the upgrade rather than selecting, merging or
overwriting an account. Resolve such a conflict with a reviewed maintenance plan
on a backup or disposable copy before retrying the production upgrade. Stop API
and worker account writes while applying this data migration. Downgrade refuses
while installation account bindings exist: retain compatible code or restore a
reviewed pre-upgrade backup rather than reversing live account identities. No
online configuration or account is changed by this patch itself.

### Local Demo Login

The first administrator uses the independent setup flow above. Ordinary
phone login requires a code issued by the configured SMS provider.
Email login likewise requires a code issued through the configured SMTP provider.
The Docker environment example leaves `UNIVERSAL_VERIFICATION_CODE` empty;
there is no default login code.
For an isolated local demo or automated test, explicitly set
`ENV=development` and a nonblank `UNIVERSAL_VERIFICATION_CODE` in your local
environment, then select the development factory:

```bash
gunicorn -w 1 -b 127.0.0.1:5800 'app:create_development_app()' --timeout 300
```

The development Compose and runtime harness select this factory explicitly;
neither template supplies a default universal code. Use a synthetic test
phone number and keep these servers isolated. The development factory refuses
environments other than `development` or `testing`. Tests constructing a Flask
app directly can opt in with `enable_development_verification_codes(app)` from
`flaskr.service.user.verification_codes` after setting that environment.

The normal `app:app` and `create_app()` entrypoints never enable the bypass,
even if both `ENV=development` and a universal code are accidentally configured.
Production and unknown environments also reject the bypass after a development
app's configuration changes. An actually issued code still follows normal
expiry, attempt limits, and single-use consumption, including when its value
happens to match a legacy universal setting.

### Upgrading Existing Verification-Code Deployments

Upgrade the API image or source to a release containing this fix; changing the
Compose file alone does not update older pinned images. Remove
`UNIVERSAL_VERIFICATION_CODE` from deployment environment files, Compose
overrides, and secret/configuration stores, use the normal `app:app` production
entrypoint with `ENV=production`, and recreate API containers/processes so the
new code and configuration take effect. Configure and verify a real SMS or
email provider before opening login and password recovery to users. Verify
normal issued-code login and password recovery in a controlled environment.
These steps are operator actions; the patch does not change running deployments
or assume whether any existing production installation was exposed.

# INSTALL FROM SOURCE CODE STEP BY STEP

## Prerequisites

### Architecture Overview

AI-Shifu consists of two main components:

```bash
src/
├── api/          # Backend API service (Flask/Python)
└── web/          # Cook Web frontend (Next.js)
```

- **api**: Backend API service built with Flask
- **web**: Cook Web frontend for creating, managing, and learning courses, built with Next.js

### Required Tools and Services

- **Python 3.11+** for backend API
- **Node.js 22.16.0** for frontend applications
- **MySQL 8.0+** for database storage
- **Redis** for caching and session management
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

Copy the full environment template (already aligned with the Docker defaults):

```bash
cp docker/.env.example.full docker/.env
```

For Docker-based workflows, configure at least one LLM provider key (for example `OPENAI_API_KEY`, `ERNIE_API_KEY` or `GLM_API_KEY`) and set `LLM_MODEL_1_ID` to a text model ID available through that provider. `LLM_MODEL_1_NAME` is optional; omit it or leave it blank to display the configured model ID. The template intentionally leaves both values empty, but only the ID is required. Database defaults match the bundled services; review security settings before production use.

### Step 3: Configure Environment Variables

Edit the `.env` file and configure the required settings.

#### Required Variables (MUST be configured)

These variables are essential for the application to run:

1. **Database Connection**
   - `SQLALCHEMY_DATABASE_URI`: MySQL connection string
   - Example: `mysql://root:password@localhost:3306/ai-shifu?charset=utf8mb4`

2. **Security**
   - `SECRET_KEY`: JWT signing key for authentication
   - Generate secure key: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
   - **Important**: Use different keys for dev/test/prod environments

3. **LLM Provider** (at least one required)
   - Choose from: OpenAI, ERNIE, ARK, SiliconFlow, GLM, DeepSeek, Qwen
   - See `.env.example.full` for specific provider configurations

4. **Numbered Course Models**
   - `LLM_MODEL_1_ID`: required physical text model ID served by the configured provider; no default. Model 1 is always the course default.
   - `LLM_MODEL_<1..9>_NAME`: optional display name, shared across interface languages. Omitted, empty or whitespace-only names display the corresponding configured model ID.
   - Configure optional `LLM_MODEL_2_ID` through `LLM_MODEL_9_ID` to add options. A nonblank ID enables a number even without a name; a name without an ID does not. Gaps are allowed; identifiers never shift when another number is removed.
   - A configured provider failure is an error, not a reason to silently switch models. Live voice remains separate.

#### Configuration Reference

- `docker/.env.example.full`: canonical template that lists every environment variable with defaults, descriptions, and grouping (Database, Redis, Auth, LLM, etc.). Copy it to `.env` and edit in place.
- **Docker reminder**: configure a provider API key and `LLM_MODEL_1_ID` for latest-image, pinned-release and local-development Compose modes. Update database/Redis URLs if you are not using the bundled services.

#### Important Notes

- All sensitive values (API keys, passwords) should be kept secure
- Never commit `.env` files to version control
- For production deployments, use environment-specific configurations
- Refer to the example files for detailed explanations of each variable

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
docker build -t aishifu/ai-shifu-cook-web:latest -f src/web/Dockerfile .
```

3. Start the containers with the compose bundle that tracks the `:latest` tags:

```bash
cd docker
docker compose -f docker-compose.latest.yml up -d
```

`docker-compose.latest.yml` always uses the most recent images (from Docker Hub or your own local builds). Use `docker-compose.yml` instead if you need pinned release tags for reproducible environments.

### Step 5: Manual Installation (Development)

This section covers manual installation for development purposes or when you need more control over the setup.

#### Step 5.1: Set Up Database Services

Start MySQL and Redis services on your local machine or use Docker:

```bash
# Using Docker for databases only
docker run -d --name mysql -p 3306:3306 -e MYSQL_ROOT_PASSWORD=ai-shifu -e MYSQL_DATABASE=ai-shifu mysql:latest
docker run -d --name redis -p 6379:6379 redis:latest
```

#### Step 5.2: Configure Environment for Local Development

Keep the provider key and required `LLM_MODEL_1_ID` mapping from Step 3, and update your `.env` file for local development:

```bash
# Update database URLs for local services
SQLALCHEMY_DATABASE_URI="mysql://root:ai-shifu@localhost:3306/ai-shifu"

# Update API base URL
REACT_APP_BASEURL="http://localhost:5800"
```

#### Step 5.3: Start Backend API

```bash
cd src/api
# Copy the environment configuration from docker directory
cp ../../docker/.env .env

# Install Python dependencies
pip install -r requirements.txt

# Initialize database
flask db upgrade

# Start the API server
gunicorn -w 4 -b 0.0.0.0:5800 'app:app' --timeout 300 --log-level debug
```

#### Step 5.4: Start Web Frontend & CMS

```bash
cd src/web
# Install Node.js dependencies
npm install  # or use pnpm install

# Start development server
npm run dev
```

Cook Web (which now serves both the learner experience and authoring console) will be available at `http://localhost:3000`.

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
python -m pip install ruff==0.16.5 commitizen==4.16.2 pre-commit-hooks==6.0.0 markdown-it-py==4.0.0
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

See the [numbered-model deployment runbook](docs/exec-plans/active/numbered-course-models.md#deployment-runbook).
Do not roll back to a build that treats newly saved numeric choices as physical IDs.

## Troubleshooting

### Common Issues

1. **Database Connection Failed**
   - Ensure MySQL is running and accessible
   - Check database credentials in `.env`
   - Run `flask db upgrade` to initialize tables

2. **Redis Connection Failed**
   - Ensure Redis is running and accessible
   - Check Redis configuration in `.env`

3. **LLM API Errors**
   - Verify API keys are correct
   - Check API base URLs
   - Ensure the model name matches your provider
   - If startup reports missing `LLM_MODEL_1_ID`, configure that binding; provider credentials alone are insufficient. Missing `LLM_MODEL_1_NAME` does not block startup; it displays the configured model ID

4. **Frontend Build Failures**
   - Ensure Node.js version is 22.16.0
   - Clear node_modules and reinstall: `rm -rf node_modules && npm install`
   - Check for environment variable issues

5. **Pre-commit Hooks Not Running / "command not found"**
   - Make sure you ran `lefthook install` once in this clone
   - Run `python scripts/check_dev_tools.py` to see which tools are missing and how to install them

### Log Files

- API logs: Check gunicorn output or `/var/log/ai-shifu.log`
- Frontend logs: Check browser console or terminal output

## Access the Application

### Manual Installation

- User Interface: `http://localhost:3000` (or configured PORT)
- Script Editor: `http://localhost:3001`
- API: `http://localhost:5800`

### Default Login

- Use any phone number for registration/login
- Default verification code: `1024`

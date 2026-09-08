# AI-Shifu Configuration Scripts

This directory contains utility scripts for managing AI-Shifu configuration.

## generate_env_examples.py

Generates the environment configuration example file from the application's configuration definitions.

### Purpose

This script automatically generates `.env.example.full`, which contains every environment variable with defaults and documentation. Copy it to `.env` and set at least one LLM API key before starting Docker.

### Usage

From the `src/api` directory:

```bash
python scripts/generate_env_examples.py
```

### Output

The script generates one file in the `docker` directory:

- `.env.example.full` - Complete configuration reference used by Docker deployments

### Features

- Automatically extracts configuration from `flaskr.common.config`
- Groups variables by category (Database, Redis, Auth, LLM, etc.)
- Includes descriptions, types, and validation information
- Marks required variables clearly
- Handles multi-line descriptions
- Protects secret values by not including defaults
- Provides a summary of configuration requirements

### When to Use

Run this script when:

- Adding or editing environment variables in `config.py`
- Updating variable descriptions or requirements
- Refreshing the example template for onboarding/docs

### Example Output

The script provides helpful output:

```
✅ Generated full configuration: .env.example.full

📊 Summary:
  - Total variables: 151
  - Required variables: 2
  - Optional variables: 149

📌 Required variables that must be configured:
  [AUTH]
    - SECRET_KEY
    - UNIVERSAL_VERIFICATION_CODE
  [DATABASE]
    - SQLALCHEMY_DATABASE_URI
```

### Configuration Workflow

1. Run the generation script.
2. Copy `docker/.env.example.full` to `docker/.env`.
3. Edit `.env` and configure at least one LLM API key plus any other secrets you need.
4. Never commit `.env` to version control.

## harness_diagnostics.py

Summarizes backend log evidence for a specific `X-Request-ID` so browser smoke
failures can be traced back to request-scoped server activity.

### Usage

From the `src/api` directory:

```bash
python scripts/harness_diagnostics.py --request-id <request-id>
```

### Output

- request id and detection mode (`langfuse-configured` or `local-log-only`)
- explicit trace-id hints when they appear in logs
- a bounded excerpt of matching `ai-shifu.log*` lines
- when the local dev observability stack is reachable, a Loki/Tempo/Prometheus
  summary plus Grafana explore links for the same request context
- the default dev harness now boots the API through
  `scripts/repair_dev_migration_state.py` before rerunning Alembic, so
  diagnostics can assume the self-healing path is part of normal startup

## grant_white_label.py

Onboards a single creator to white-label (custom domain + branding) by writing
the manual billing entitlement and a verified custom-domain binding. This is the
fast-path operator tool: branding/custom-domain entitlements are granted
manually and decoupled from paid products.

### Purpose

- Sets `branding_enabled` / `custom_domain_enabled` on a reusable manual
  entitlement snapshot for the creator (idempotent upsert).
- Writes the supplied logo / home / contact URLs into
  `feature_payload.branding`, which `/runtime-config` serves to the learner app
  so `/c` pages render the creator's logo and favicon automatically.
- Binds and marks the custom domain `verified` so published/preview links point
  at the creator's own host.

### Usage

From the `src/api` directory:

```bash
python scripts/grant_white_label.py \
  --creator-bid <creator_bid> \
  --host learn.example.com \
  --logo-wide-url https://cdn.example.com/wide.png \
  --logo-square-url https://cdn.example.com/square.png \
  --favicon-url https://cdn.example.com/favicon.ico
```

Use `--dry-run` to preview the changes without writing. Use `--no-custom-domain`
to grant branding only (skips the domain entitlement and binding). DNS still
needs the customer to CNAME the host to our ingress, and the ingress host rule
must be added separately (see `deploy-config`).

# AI-Shifu Configuration Scripts

This directory contains utility scripts for managing AI-Shifu configuration.

## backfill_profile_onboarding_assistant_prompts.py

Run this once when adding a new supported language to an installation with an
existing profile-onboarding configuration. Use the upgraded API runtime, with its
database and LLM settings available, before exposing Spanish in the learner UI.
For a Docker Compose installation, run from the repository root:

```bash
cd docker
docker compose -f docker-compose.latest.yml exec -T ai-shifu-api python scripts/backfill_profile_onboarding_assistant_prompts.py --locale de-DE
docker compose -f docker-compose.latest.yml exec -T ai-shifu-api python scripts/backfill_profile_onboarding_assistant_prompts.py --locale de-DE --apply
```

For a source-checkout installation, run from the repository root instead:

```bash
cd src/api
python scripts/backfill_profile_onboarding_assistant_prompts.py --locale de-DE
python scripts/backfill_profile_onboarding_assistant_prompts.py --locale de-DE --apply
```

The first command previews the stored configuration without a model call or
write. `--apply` localizes the saved master prompt and atomically fills missing
registered locales, preserving existing translations. Omitting `--locale`
continues to target Spanish for compatibility with older runbooks. It prints only a status
and configuration revision plus the generated locale codes, never the prompt
text. If an older map lacks languages besides German, the existing save path
fills those missing languages in the same run. `already_present` means a
repeat run has nothing to do. `no_configuration` or `no_master_prompt` means
there is no saved prompt to translate; configure the onboarding prompt through
the operator UI if that feature is needed. A generation or concurrent-save
failure leaves the previous configuration intact; retry after resolving it.
Existing learner sessions retain their original frozen prompt.

## generate_env_examples.py

Generates the environment configuration example file from the application's configuration definitions.

### Purpose

This script automatically generates `.env.example.full`, which contains every environment variable with defaults and documentation. Copy it to `.env`, configure a provider API key, and set `LLM_MODEL_1_ID` to a text model served by that provider before starting Docker. Only model 1's ID is required and has no default; IDs 2-9 are optional. Every model name is optional: omitted or blank names display the configured model ID. A name without an ID does not enable an option.

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

The script reports current variable counts and required settings. Its required-settings output includes:

```
📌 Required variables that must be configured:
  [LLM]
    - LLM_MODEL_1_ID
      Routed text model for course model 1. Required; no default.
```

### Configuration Workflow

1. Run the generation script.
2. Copy `docker/.env.example.full` to `docker/.env`.
3. Edit `.env` and configure a provider API key, required `LLM_MODEL_1_ID` and any other secrets you need. Names are optional; blank names display the configured IDs. The template intentionally leaves model mappings empty.
4. For existing installations, complete [Upgrading to numbered models](../../../INSTALL_MANUAL.md#upgrading-to-numbered-models) before starting the new API or workers.
5. Never commit `.env` to version control.

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

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
  - Total variables: 106
  - Required variables: 3
  - Optional variables: 103

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

---

## generate_llm_model_map.py

Dynamically generates the LLM model mapping file by fetching model lists from configured providers.

### Purpose

This script connects to various LLM providers (OpenAI-compatible APIs, ARK/Volcengine, etc.) and generates a `model-map.json` file containing:

- **Aliases**: Maps provider-specific model names to canonical LiteLLM-recognized keys
- **max_tokens**: Override values for models not in LiteLLM's registry (now mostly inferred by pattern rules)

### Usage

From the `src/api` directory:

```bash
# Ensure your .env file has the required API keys configured
python scripts/generate_llm_model_map.py
```

### Output

The script generates/updates:

- `flaskr/api/llm/model-map.json` - Model aliases and max_tokens overrides

### Features

- Fetches models from OpenAI-compatible providers (DeepSeek, Qwen, Silicon, etc.)
- Fetches ARK/Volcengine endpoints and extracts foundation model names
- Canonicalizes model names using pattern rules (`LITELLM_CANONICAL_RULES`)
- Infers max_tokens using pattern rules (`MAX_TOKENS_PATTERN_RULES`)
- Reports models missing from LiteLLM's registry
- Automatically cleans up redundant entries

### Environment Variables

The script uses API keys from your `.env` file:

- `DEEPSEEK_API_KEY` - DeepSeek models
- `QWEN_API_KEY` - Alibaba Qwen models
- `SILICON_API_KEY` - SiliconFlow models
- `ARK_ACCESS_KEY_ID` / `ARK_SECRET_ACCESS_KEY` - Volcengine ARK models
- And more (see `config.py` for full list)

### When to Use

Run this script when:

- **Upgrading LiteLLM** - Re-check model mappings against the updated registry
- Adding support for a new LLM provider
- Updating model mappings after provider changes
- Debugging model resolution issues
- Verifying which models are available from your configured providers

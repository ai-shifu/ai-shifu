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

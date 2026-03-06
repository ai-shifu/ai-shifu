"""Ask provider registry and schema metadata."""

from typing import Any

from flaskr.service.shifu.shifu_draft_funcs import (
    ASK_PROVIDER_LLM,
    ASK_PROVIDER_DIFY,
    ASK_PROVIDER_COZE,
    ASK_PROVIDER_COZE_WORKFLOW,
    ASK_PROVIDER_VOLC_KNOWLEDGE,
    ASK_PROVIDER_MODE_PROVIDER_ONLY,
    ASK_PROVIDER_MODE_PROVIDER_THEN_LLM,
    normalize_ask_provider_config,
)


def get_default_ask_provider_config() -> dict[str, Any]:
    return {
        "provider": ASK_PROVIDER_LLM,
        "mode": ASK_PROVIDER_MODE_PROVIDER_ONLY,
        "config": {},
    }


def get_ask_provider_schema_registry() -> dict[str, dict[str, Any]]:
    """Return schema metadata for all supported ask providers."""
    return {
        ASK_PROVIDER_LLM: {
            "title": "LLM",
            "description": "Use built-in ask LLM only.",
            "default_config": {},
            "json_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        ASK_PROVIDER_DIFY: {
            "title": "Dify",
            "description": "Route ask to Dify chat app with minimal config.",
            "default_config": {
                "base_url": "https://api.dify.ai/v1",
                "api_key": "",
            },
            "json_schema": {
                "type": "object",
                "properties": {
                    "base_url": {
                        "type": "string",
                        "title": "Base URL",
                        "description": "Dify base URL, e.g. https://api.dify.ai/v1",
                    },
                    "api_key": {
                        "type": "string",
                        "format": "password",
                        "title": "API Key",
                        "description": "Dify app API key.",
                    },
                },
                "required": ["base_url", "api_key"],
                "additionalProperties": True,
            },
        },
        ASK_PROVIDER_COZE: {
            "title": "Coze",
            "description": "Route ask to Coze bot chat API with minimal config.",
            "default_config": {
                "base_url": "https://api.coze.com",
                "api_key": "",
                "bot_id": "",
            },
            "json_schema": {
                "type": "object",
                "properties": {
                    "base_url": {
                        "type": "string",
                        "title": "Base URL",
                        "description": "Coze base URL, e.g. https://api.coze.com",
                    },
                    "api_key": {
                        "type": "string",
                        "format": "password",
                        "title": "API Key",
                        "description": "Coze personal access token.",
                    },
                    "bot_id": {
                        "type": "string",
                        "title": "Bot ID",
                        "description": "Coze bot identifier.",
                    },
                },
                "required": ["base_url", "api_key", "bot_id"],
                "additionalProperties": True,
            },
        },
        ASK_PROVIDER_COZE_WORKFLOW: {
            "title": "Coze Workflow",
            "description": "Route ask to Coze workflow stream_run API with minimal config.",
            "default_config": {
                "base_url": "https://api.coze.cn",
                "api_key": "",
                "workflow_id": "",
                "query_parameter": "input",
                "parameters": {},
            },
            "json_schema": {
                "type": "object",
                "properties": {
                    "base_url": {
                        "type": "string",
                        "title": "Base URL",
                        "description": "Coze base URL, e.g. https://api.coze.cn",
                    },
                    "api_key": {
                        "type": "string",
                        "format": "password",
                        "title": "API Key",
                        "description": "Coze personal access token.",
                    },
                    "workflow_id": {
                        "type": "string",
                        "title": "Workflow ID",
                        "description": "Published Coze workflow id.",
                    },
                    "query_parameter": {
                        "type": "string",
                        "title": "Query Parameter",
                        "description": "Parameter name to put the user query into (default: input).",
                    },
                    "parameters": {
                        "type": "object",
                        "title": "Parameters (JSON)",
                        "description": "Static workflow parameters (JSON object).",
                    },
                    "bot_id": {
                        "type": "string",
                        "title": "Bot ID (optional)",
                        "description": "Required if your workflow run needs a bot context.",
                    },
                    "app_id": {
                        "type": "string",
                        "title": "App ID (optional)",
                        "description": "Only required when running workflows inside a Coze app.",
                    },
                    "connector_id": {
                        "type": "string",
                        "title": "Connector ID (optional)",
                        "description": "Channel id, default 1024 for API.",
                    },
                    "workflow_version": {
                        "type": "string",
                        "title": "Workflow Version (optional)",
                        "description": "Workflow version, only effective for library workflows.",
                    },
                    "ext": {
                        "type": "object",
                        "title": "Ext (JSON)",
                        "description": 'Extra fields, e.g. {"user_id":"u1"} or latitude/longitude.',
                    },
                },
                "required": ["base_url", "api_key", "workflow_id"],
                "additionalProperties": True,
            },
        },
        ASK_PROVIDER_VOLC_KNOWLEDGE: {
            "title": "Volcengine Knowledge Base",
            "description": "Route ask to Volcengine Knowledge Base search API with minimal config.",
            "default_config": {
                "account_id": "",
                "ak": "",
                "sk": "",
                "collection_name": "",
            },
            "json_schema": {
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "title": "Account ID",
                        "description": "Volcengine account id for V-Account-Id header.",
                    },
                    "ak": {
                        "type": "string",
                        "format": "password",
                        "title": "Access Key",
                        "description": "Volcengine AK.",
                    },
                    "sk": {
                        "type": "string",
                        "format": "password",
                        "title": "Secret Key",
                        "description": "Volcengine SK.",
                    },
                    "collection_name": {
                        "type": "string",
                        "title": "Collection Name",
                        "description": "Knowledge base collection name.",
                    },
                },
                "required": ["account_id", "ak", "sk", "collection_name"],
                "additionalProperties": True,
            },
        },
    }


def validate_ask_provider_specific_config(
    provider: str, config: Any
) -> tuple[bool, str | None]:
    """Lightweight validation against provider schema required fields."""
    registry = get_ask_provider_schema_registry()
    if provider not in registry:
        return False, "provider"
    if not isinstance(config, dict):
        return False, "config"

    schema = registry[provider].get("json_schema", {})
    required_fields = schema.get("required", [])
    for field in required_fields:
        value = config.get(field)
        if isinstance(value, str):
            if not value.strip():
                return False, field
        elif value is None:
            return False, field

    return True, None


def get_effective_ask_provider_config(raw_config: Any) -> dict[str, Any]:
    """
    Normalize persisted ask provider config.
    """
    return normalize_ask_provider_config(raw_config)


def get_ask_provider_metadata() -> dict[str, Any]:
    """Metadata endpoint payload for ask provider schema-driven UI."""
    registry = get_ask_provider_schema_registry()

    providers: list[dict[str, Any]] = []
    for provider in [
        ASK_PROVIDER_LLM,
        ASK_PROVIDER_DIFY,
        ASK_PROVIDER_COZE,
        ASK_PROVIDER_COZE_WORKFLOW,
        ASK_PROVIDER_VOLC_KNOWLEDGE,
    ]:
        item = registry[provider]
        providers.append(
            {
                "provider": provider,
                "title": item.get("title", provider),
                "description": item.get("description", ""),
                "default_config": item.get("default_config", {}),
                "json_schema": item.get("json_schema", {}),
            }
        )

    return {
        "feature_enabled": True,
        "default": get_default_ask_provider_config(),
        "modes": [
            {
                "value": ASK_PROVIDER_MODE_PROVIDER_ONLY,
                "title": "Provider Only",
            },
            {
                "value": ASK_PROVIDER_MODE_PROVIDER_THEN_LLM,
                "title": "Provider Then LLM",
            },
        ],
        "providers": providers,
    }

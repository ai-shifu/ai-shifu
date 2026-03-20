"""Ask provider registry and schema metadata."""

from typing import Any

from flaskr.i18n import _
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


def _translated_or_fallback(translated: str, key: str, fallback: str) -> str:
    if translated == key:
        return fallback
    return str(translated)


def _localize_provider_title(provider: str, fallback: str) -> str:
    if provider == ASK_PROVIDER_LLM:
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderOptions.llm"),
            "module.shifuSetting.askProviderOptions.llm",
            fallback,
        )
    if provider == ASK_PROVIDER_DIFY:
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderOptions.dify"),
            "module.shifuSetting.askProviderOptions.dify",
            fallback,
        )
    if provider == ASK_PROVIDER_COZE:
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderOptions.coze"),
            "module.shifuSetting.askProviderOptions.coze",
            fallback,
        )
    if provider == ASK_PROVIDER_COZE_WORKFLOW:
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderOptions.coze_workflow"),
            "module.shifuSetting.askProviderOptions.coze_workflow",
            fallback,
        )
    if provider == ASK_PROVIDER_VOLC_KNOWLEDGE:
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderOptions.volc_knowledge"),
            "module.shifuSetting.askProviderOptions.volc_knowledge",
            fallback,
        )
    return fallback


def _localize_provider_description(provider: str, fallback: str) -> str:
    if provider == ASK_PROVIDER_LLM:
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderDescriptions.llm"),
            "module.shifuSetting.askProviderDescriptions.llm",
            fallback,
        )
    if provider == ASK_PROVIDER_DIFY:
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderDescriptions.dify"),
            "module.shifuSetting.askProviderDescriptions.dify",
            fallback,
        )
    if provider == ASK_PROVIDER_COZE:
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderDescriptions.coze"),
            "module.shifuSetting.askProviderDescriptions.coze",
            fallback,
        )
    if provider == ASK_PROVIDER_COZE_WORKFLOW:
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderDescriptions.coze_workflow"),
            "module.shifuSetting.askProviderDescriptions.coze_workflow",
            fallback,
        )
    if provider == ASK_PROVIDER_VOLC_KNOWLEDGE:
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderDescriptions.volc_knowledge"),
            "module.shifuSetting.askProviderDescriptions.volc_knowledge",
            fallback,
        )
    return fallback


def _localize_provider_field_label(
    provider: str, field_name: str, fallback: str
) -> str:
    if provider == ASK_PROVIDER_DIFY and field_name == "base_url":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.dify.base_url.label"),
            "module.shifuSetting.askProviderFields.dify.base_url.label",
            fallback,
        )
    if provider == ASK_PROVIDER_DIFY and field_name == "api_key":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.dify.api_key.label"),
            "module.shifuSetting.askProviderFields.dify.api_key.label",
            fallback,
        )
    if provider == ASK_PROVIDER_COZE and field_name == "api_key":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.coze.api_key.label"),
            "module.shifuSetting.askProviderFields.coze.api_key.label",
            fallback,
        )
    if provider == ASK_PROVIDER_COZE and field_name == "bot_id":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.coze.bot_id.label"),
            "module.shifuSetting.askProviderFields.coze.bot_id.label",
            fallback,
        )
    if provider == ASK_PROVIDER_COZE_WORKFLOW and field_name == "api_key":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.coze_workflow.api_key.label"),
            "module.shifuSetting.askProviderFields.coze_workflow.api_key.label",
            fallback,
        )
    if provider == ASK_PROVIDER_COZE_WORKFLOW and field_name == "workflow_id":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.coze_workflow.workflow_id.label"),
            "module.shifuSetting.askProviderFields.coze_workflow.workflow_id.label",
            fallback,
        )
    if provider == ASK_PROVIDER_VOLC_KNOWLEDGE and field_name == "account_id":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.volc_knowledge.account_id.label"),
            "module.shifuSetting.askProviderFields.volc_knowledge.account_id.label",
            fallback,
        )
    if provider == ASK_PROVIDER_VOLC_KNOWLEDGE and field_name == "ak":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.volc_knowledge.ak.label"),
            "module.shifuSetting.askProviderFields.volc_knowledge.ak.label",
            fallback,
        )
    if provider == ASK_PROVIDER_VOLC_KNOWLEDGE and field_name == "sk":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.volc_knowledge.sk.label"),
            "module.shifuSetting.askProviderFields.volc_knowledge.sk.label",
            fallback,
        )
    if provider == ASK_PROVIDER_VOLC_KNOWLEDGE and field_name == "collection_name":
        return _translated_or_fallback(
            _(
                "module.shifuSetting.askProviderFields.volc_knowledge.collection_name.label"
            ),
            "module.shifuSetting.askProviderFields.volc_knowledge.collection_name.label",
            fallback,
        )
    return fallback


def _localize_provider_field_hint(provider: str, field_name: str, fallback: str) -> str:
    if provider == ASK_PROVIDER_DIFY and field_name == "base_url":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.dify.base_url.hint"),
            "module.shifuSetting.askProviderFields.dify.base_url.hint",
            fallback,
        )
    if provider == ASK_PROVIDER_DIFY and field_name == "api_key":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.dify.api_key.hint"),
            "module.shifuSetting.askProviderFields.dify.api_key.hint",
            fallback,
        )
    if provider == ASK_PROVIDER_COZE and field_name == "api_key":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.coze.api_key.hint"),
            "module.shifuSetting.askProviderFields.coze.api_key.hint",
            fallback,
        )
    if provider == ASK_PROVIDER_COZE and field_name == "bot_id":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.coze.bot_id.hint"),
            "module.shifuSetting.askProviderFields.coze.bot_id.hint",
            fallback,
        )
    if provider == ASK_PROVIDER_COZE_WORKFLOW and field_name == "api_key":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.coze_workflow.api_key.hint"),
            "module.shifuSetting.askProviderFields.coze_workflow.api_key.hint",
            fallback,
        )
    if provider == ASK_PROVIDER_COZE_WORKFLOW and field_name == "workflow_id":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.coze_workflow.workflow_id.hint"),
            "module.shifuSetting.askProviderFields.coze_workflow.workflow_id.hint",
            fallback,
        )
    if provider == ASK_PROVIDER_VOLC_KNOWLEDGE and field_name == "account_id":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.volc_knowledge.account_id.hint"),
            "module.shifuSetting.askProviderFields.volc_knowledge.account_id.hint",
            fallback,
        )
    if provider == ASK_PROVIDER_VOLC_KNOWLEDGE and field_name == "ak":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.volc_knowledge.ak.hint"),
            "module.shifuSetting.askProviderFields.volc_knowledge.ak.hint",
            fallback,
        )
    if provider == ASK_PROVIDER_VOLC_KNOWLEDGE and field_name == "sk":
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderFields.volc_knowledge.sk.hint"),
            "module.shifuSetting.askProviderFields.volc_knowledge.sk.hint",
            fallback,
        )
    if provider == ASK_PROVIDER_VOLC_KNOWLEDGE and field_name == "collection_name":
        return _translated_or_fallback(
            _(
                "module.shifuSetting.askProviderFields.volc_knowledge.collection_name.hint"
            ),
            "module.shifuSetting.askProviderFields.volc_knowledge.collection_name.hint",
            fallback,
        )
    return fallback


def _localize_mode_title(mode: str, fallback: str) -> str:
    if mode == ASK_PROVIDER_MODE_PROVIDER_ONLY:
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderModes.provider_only"),
            "module.shifuSetting.askProviderModes.provider_only",
            fallback,
        )
    if mode == ASK_PROVIDER_MODE_PROVIDER_THEN_LLM:
        return _translated_or_fallback(
            _("module.shifuSetting.askProviderModes.provider_then_llm"),
            "module.shifuSetting.askProviderModes.provider_then_llm",
            fallback,
        )
    return fallback


def _localize_provider_schema(
    provider: str, schema: dict[str, Any] | None
) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}

    localized_schema = dict(schema)
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return localized_schema

    localized_properties: dict[str, Any] = {}
    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, dict):
            localized_properties[field_name] = field_schema
            continue

        localized_field = dict(field_schema)
        localized_field["title"] = _localize_provider_field_label(
            provider,
            field_name,
            str(field_schema.get("title", field_name)),
        )
        localized_field["description"] = _localize_provider_field_hint(
            provider,
            field_name,
            str(field_schema.get("description", "")),
        )
        localized_properties[field_name] = localized_field

    localized_schema["properties"] = localized_properties
    return localized_schema


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
                "base_url": "",
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
                "api_key": "",
                "bot_id": "",
            },
            "json_schema": {
                "type": "object",
                "properties": {
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
                "required": ["api_key", "bot_id"],
                "additionalProperties": True,
            },
        },
        ASK_PROVIDER_COZE_WORKFLOW: {
            "title": "Coze Workflow",
            "description": "Route ask to Coze workflow run API.",
            "default_config": {
                "api_key": "",
                "workflow_id": "",
            },
            "json_schema": {
                "type": "object",
                "properties": {
                    "api_key": {
                        "type": "string",
                        "format": "password",
                        "title": "API Key",
                        "description": "Coze personal access token.",
                    },
                    "workflow_id": {
                        "type": "string",
                        "title": "Workflow ID",
                        "description": "Coze workflow identifier.",
                    },
                },
                "required": ["api_key", "workflow_id"],
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
                "title": _localize_provider_title(
                    provider, str(item.get("title", provider))
                ),
                "description": _localize_provider_description(
                    provider,
                    str(item.get("description", "")),
                ),
                "default_config": item.get("default_config", {}),
                "json_schema": _localize_provider_schema(
                    provider, item.get("json_schema", {})
                ),
            }
        )

    return {
        "feature_enabled": True,
        "default": get_default_ask_provider_config(),
        "modes": [
            {
                "value": ASK_PROVIDER_MODE_PROVIDER_ONLY,
                "title": _localize_mode_title(
                    ASK_PROVIDER_MODE_PROVIDER_ONLY, "Provider Only"
                ),
            },
            {
                "value": ASK_PROVIDER_MODE_PROVIDER_THEN_LLM,
                "title": _localize_mode_title(
                    ASK_PROVIDER_MODE_PROVIDER_THEN_LLM, "Provider Then LLM"
                ),
            },
        ],
        "providers": providers,
    }

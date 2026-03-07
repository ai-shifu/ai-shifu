"""Ask provider adapter registry and routing entrypoints."""

from typing import Any, Generator

from flask import Flask

from flaskr.service.shifu.shifu_draft_funcs import (
    ASK_PROVIDER_COZE,
    ASK_PROVIDER_DIFY,
    ASK_PROVIDER_LLM,
    ASK_PROVIDER_VOLC_KNOWLEDGE,
)

from .base import (
    AskProviderAdapter,
    AskProviderChunk,
    AskProviderConfigError,
    AskProviderRuntime,
)
from .coze_adapter import CozeAskProviderAdapter
from .dify_adapter import DifyAskProviderAdapter
from .llm_adapter import LlmAskProviderAdapter
from .volc_knowledge_adapter import VolcKnowledgeAskProviderAdapter


def get_ask_provider_adapter(provider: str) -> AskProviderAdapter | None:
    provider = (provider or "").strip().lower()
    if provider == ASK_PROVIDER_LLM:
        return LlmAskProviderAdapter()
    if provider == ASK_PROVIDER_DIFY:
        return DifyAskProviderAdapter()
    if provider == ASK_PROVIDER_COZE:
        return CozeAskProviderAdapter()
    if provider == ASK_PROVIDER_VOLC_KNOWLEDGE:
        return VolcKnowledgeAskProviderAdapter()
    return None


def stream_ask_provider_response(
    app: Flask,
    provider: str,
    user_id: str,
    user_query: str,
    messages: list[dict[str, Any]],
    provider_config: dict[str, Any],
    runtime: AskProviderRuntime | None = None,
) -> Generator[AskProviderChunk, None, None]:
    adapter = get_ask_provider_adapter(provider)
    if not adapter:
        raise AskProviderConfigError(f"unsupported provider: {provider}")
    yield from adapter.stream_answer(
        app, user_id, user_query, messages, provider_config, runtime
    )

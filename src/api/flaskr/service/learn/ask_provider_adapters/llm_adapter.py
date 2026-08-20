"""Built-in LLM ask provider adapter."""

from collections.abc import Generator
from typing import Any

from flask import Flask

from .base import (
    AskProviderChunk,
    AskProviderConfigError,
    AskProviderRuntime,
)
from .consts import ASK_PROVIDER_LLM


class LlmAskProviderAdapter:
    """Adapt direct LLM responses to the common ask stream."""

    provider = ASK_PROVIDER_LLM

    def stream_answer(
        self,
        app: Flask,
        user_id: str,
        user_query: str,
        messages: list[dict[str, Any]],
        provider_config: dict[str, Any],
        runtime: AskProviderRuntime | None = None,
    ) -> Generator[AskProviderChunk, None, None]:
        _ = (app, user_id, user_query, messages, provider_config)
        if runtime is None or runtime.llm_stream_factory is None:
            message = "llm runtime is not configured"
            raise AskProviderConfigError(message)

        for chunk in runtime.llm_stream_factory():
            current_content = getattr(chunk, "result", None)
            if isinstance(current_content, str) and current_content:
                yield AskProviderChunk(content=current_content)

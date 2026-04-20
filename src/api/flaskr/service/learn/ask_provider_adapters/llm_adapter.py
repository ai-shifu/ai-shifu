"""Built-in LLM ask provider adapter."""

from typing import Any, Generator

from flask import Flask

from flaskr.service.shifu.shifu_draft_funcs import ASK_PROVIDER_LLM

from .base import (
    AskProviderChunk,
    AskProviderConfigError,
    AskProviderRuntime,
)


class LlmAskProviderAdapter:
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
            raise AskProviderConfigError("llm runtime is not configured")

        for chunk in runtime.llm_stream_factory():
            current_content = getattr(chunk, "result", None)
            if isinstance(current_content, str) and current_content:
                yield AskProviderChunk(content=current_content)

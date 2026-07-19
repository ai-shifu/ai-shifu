"""Base contracts and errors for ask provider adapters."""

from dataclasses import dataclass
from typing import Any, Callable, Generator, Protocol

from flask import Flask


@dataclass
class AskProviderChunk:
    content: str


@dataclass
class AskProviderRuntime:
    """
    Runtime-only data injected by caller.

    ``llm_stream_factory`` is used by the built-in LLM adapter.
    ``llm_context_stream_factory`` lets retrieval-style adapters synthesize a
    natural-language answer: it receives the retrieved knowledge context text
    and returns a built-in LLM stream grounded on that context.
    """

    llm_stream_factory: Callable[[], Generator[Any, None, None]] | None = None
    llm_context_stream_factory: Callable[[str], Generator[Any, None, None]] | None = (
        None
    )


class AskProviderError(Exception):
    """Base exception for ask provider invocation errors."""


class AskProviderConfigError(AskProviderError):
    """Provider configuration is missing or invalid."""


class AskProviderTimeoutError(AskProviderError):
    """Provider request timed out."""


class AskProviderAdapter(Protocol):
    provider: str

    def stream_answer(
        self,
        app: Flask,
        user_id: str,
        user_query: str,
        messages: list[dict[str, Any]],
        provider_config: dict[str, Any],
        runtime: AskProviderRuntime | None = None,
    ) -> Generator[AskProviderChunk, None, None]: ...

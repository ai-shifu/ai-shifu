"""Base contracts and errors for ask provider adapters."""

from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any, Protocol

from flask import Flask


@dataclass
class AskProviderChunk:
    """Represent one normalized chunk from an ask provider."""

    content: str


@dataclass
class AskProviderRuntime:
    """Runtime-only data injected by caller.

    ``llm_stream_factory`` is used by the built-in LLM adapter.
    ``llm_context_stream_factory`` lets retrieval-style adapters synthesize a
    natural-language answer: it receives the retrieved knowledge context text
    and returns a built-in LLM stream grounded on that context.
    ``search_query`` is the learner's question as typed. ``user_query`` also
    carries the host's output-format and language instructions, so retrieval
    adapters search with this instead.
    """

    llm_stream_factory: Callable[[], Generator[Any, None, None]] | None = None
    llm_context_stream_factory: Callable[[str], Generator[Any, None, None]] | None = (
        None
    )
    search_query: str | None = None


def retrieval_query(user_query: str, runtime: AskProviderRuntime | None) -> str:
    """Return the text a retrieval adapter should search with."""
    if runtime is not None and runtime.search_query:
        return runtime.search_query
    return user_query


class AskProviderError(Exception):
    """Base exception for ask provider invocation errors.

    ``user_message`` optionally carries a localized, human-readable
    description safe to surface in the UI; the raw message stays for logs.
    """

    def __init__(self, message: str = "", user_message: str | None = None) -> None:
        """Store the raw provider error and optional UI-safe message."""
        super().__init__(message)
        self.user_message = user_message


class AskProviderConfigError(AskProviderError):
    """Provider configuration is missing or invalid."""


class AskProviderTimeoutError(AskProviderError):
    """Provider request timed out."""


class AskProviderAdapter(Protocol):
    """Define the streaming contract for ask-provider adapters."""

    provider: str

    def stream_answer(
        self,
        app: Flask,
        user_id: str,
        user_query: str,
        messages: list[dict[str, object]],
        provider_config: dict[str, object],
        runtime: AskProviderRuntime | None = None,
    ) -> Generator[AskProviderChunk, None, None]:
        """Stream answer chunks from the configured provider."""
        ...

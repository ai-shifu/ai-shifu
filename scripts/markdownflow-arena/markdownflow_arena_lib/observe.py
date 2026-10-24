"""Observe the unchanged production call inside one isolated manual worker."""

from __future__ import annotations

import time
from contextlib import suppress
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def chat_llm(
    *args: object,
    completion_observer: Callable[[dict], None],
    **kwargs: object,
) -> Iterator:
    """Pass through the real model flow; collect raw terminal chunks for the run.

    Each generation runs in a separate worker process. These temporary spies
    delegate to the original functions without altering inputs, chunks, retries,
    exceptions, metering, or tracing. No application process imports this module.
    Both attributes are restored when the generator finishes, fails, or closes.
    """
    from flaskr.api import llm

    resolve = llm.get_litellm_params_and_model
    iterate = llm._iter_stream_with_precontent_retry
    started = time.monotonic()
    metadata = {"finish_reason": None, "partial_response": False, "usage": None}

    def observe_route(model: str) -> tuple:
        resolved = resolve(model)
        metadata.update(
            model=model, provider_model=resolved[1], provider=resolved[2] or ""
        )
        return resolved

    def observe_chunks(*call_args: object, **call_kwargs: object) -> Iterator:
        parameters = call_args[5]
        metadata["parameters"] = {
            key: parameters[key]
            for key in (
                "temperature",
                "max_tokens",
                "reasoning_effort",
                "top_p",
                "seed",
            )
            if key in parameters
        }
        had_content = False
        try:
            for chunk in iterate(*call_args, **call_kwargs):
                if chunk.choices:
                    choice = chunk.choices[0]
                    metadata["finish_reason"] = (
                        choice.finish_reason or metadata["finish_reason"]
                    )
                    had_content = had_content or bool(choice.delta.content)
                usage = getattr(chunk, "usage", None)
                if usage:
                    metadata["usage"] = {
                        "input": usage.prompt_tokens,
                        "output": usage.completion_tokens,
                        "total": usage.total_tokens,
                    }
                    metadata["input_cache_tokens"] = llm._extract_input_cache(usage)
                yield chunk
        except Exception as error:
            metadata["partial_response"] = (
                had_content and llm._is_litellm_repeated_stream_chunk_error(error)
            )
            raise

    try:
        with (
            patch.object(llm, "get_litellm_params_and_model", observe_route),
            patch.object(llm, "_iter_stream_with_precontent_retry", observe_chunks),
        ):
            yield from llm.chat_llm(*args, **kwargs)
    finally:
        metadata["latency_ms"] = int((time.monotonic() - started) * 1000)
        # Diagnostics must not change the production call's outcome.
        with suppress(Exception):
            completion_observer(metadata)

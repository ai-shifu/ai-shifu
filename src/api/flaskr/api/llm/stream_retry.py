"""Classify and pace retries for LiteLLM streaming requests."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import litellm

if TYPE_CHECKING:
    from collections.abc import Callable


def _is_litellm_repeated_stream_chunk_error(exc: Exception) -> bool:
    message = str(exc)
    return (
        "repeating the same chunk" in message
        and exc.__class__.__module__.startswith("litellm")
    )


# How many times to re-issue a streaming request whose connection died before
# the first content token arrived. Rate limits have a separate, longer budget.
_STREAM_PRECONTENT_RETRY_ATTEMPTS = 1


def _is_rate_limit_error(exc: Exception) -> bool:
    """Recognize provider throttling without matching provider-specific message text."""
    rate_limit_type = getattr(
        getattr(litellm, "exceptions", None), "RateLimitError", None
    )
    return (isinstance(rate_limit_type, type) and isinstance(exc, rate_limit_type)) or (
        getattr(exc, "status_code", None) == 429
    )


def _wait_before_retry(delay: float, cancelled: Callable[[], bool] | None) -> None:
    """Wake promptly when an agent turn disconnects during a provider limit wait."""
    if cancelled is None:
        time.sleep(delay)
        return
    deadline = time.monotonic() + delay
    while True:
        if cancelled():
            raise asyncio.CancelledError
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.1))


def _retryable_stream_error_types() -> tuple:
    """Connection-level litellm stream errors that are safe to retry.

    Resolved lazily via getattr because tests stub the litellm module without
    an ``exceptions`` submodule. APIConnectionError covers connections that
    die before the response starts; MidStreamFallbackError is litellm's
    wrapper for an established stream dying mid-read (observed in production
    as TLS record corruption on the provider path: DECRYPTION_FAILED_OR_
    BAD_RECORD_MAC).
    """
    exceptions_mod = getattr(litellm, "exceptions", None)
    resolved = []
    for name in ("APIConnectionError", "MidStreamFallbackError"):
        exc_type = getattr(exceptions_mod, name, None)
        if isinstance(exc_type, type):
            resolved.append(exc_type)
    return tuple(resolved)


def _check_stream_cancelled(cancelled: Callable[[], bool] | None) -> None:
    """Stop before another provider read; deadline exceptions propagate unchanged."""
    if cancelled is not None and cancelled():
        raise asyncio.CancelledError

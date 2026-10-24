"""Accumulate diagnostic model usage without inventing provider-cache coverage."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic_ai.usage import RequestUsage, RunUsage

CACHE_REPORTED_REQUESTS = "mdf2_cache_reported_requests"
CACHE_REPORTED_INPUT_TOKENS = "mdf2_cache_reported_input_tokens"
CACHE_REPORTED_READ_TOKENS = "mdf2_cache_reported_read_tokens"


def accumulate_usage(
    previous: dict[str, int], current: RequestUsage | RunUsage
) -> dict[str, int]:
    """Retain legacy totals and optional cache counts across mixed-provider reloads.

    Cache coverage describes only requests whose provider explicitly reported a
    valid cached-token count. A positive native SDK cache count is retained even
    without that coverage, but cannot establish a hit-rate denominator.
    """
    result = {
        "requests": previous.get("requests", 0) + getattr(current, "requests", 1),
        "input_tokens": previous.get("input_tokens", 0) + current.input_tokens,
        "output_tokens": previous.get("output_tokens", 0) + current.output_tokens,
    }
    reported = current.details.get(CACHE_REPORTED_REQUESTS, 0)
    if current.cache_read_tokens or reported or "cache_read_tokens" in previous:
        result["cache_read_tokens"] = (
            previous.get("cache_read_tokens", 0) + current.cache_read_tokens
        )
    if reported or "cache_reported_requests" in previous:
        result["cache_reported_requests"] = (
            previous.get("cache_reported_requests", 0) + reported
        )
        result["cache_reported_input_tokens"] = previous.get(
            "cache_reported_input_tokens", 0
        ) + current.details.get(CACHE_REPORTED_INPUT_TOKENS, 0)
        result["cache_reported_read_tokens"] = previous.get(
            "cache_reported_read_tokens", 0
        ) + current.details.get(CACHE_REPORTED_READ_TOKENS, 0)
    return result

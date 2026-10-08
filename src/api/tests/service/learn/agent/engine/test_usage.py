"""Preserve legacy counters and avoid inventing native SDK cache coverage."""

from flaskr.service.learn.agent.engine.usage import accumulate_usage
from pydantic_ai.usage import RequestUsage, RunUsage


def test_unknown_cache_keeps_the_legacy_session_shape() -> None:
    result = accumulate_usage(
        {"requests": 2, "input_tokens": 80, "output_tokens": 5},
        RunUsage(requests=1, input_tokens=20, output_tokens=3),
    )
    assert result == {"requests": 3, "input_tokens": 100, "output_tokens": 8}


def test_native_sdk_cache_tokens_do_not_invent_reported_request_coverage() -> None:
    result = accumulate_usage(
        {}, RequestUsage(input_tokens=100, output_tokens=3, cache_read_tokens=40)
    )
    assert result == {
        "requests": 1,
        "input_tokens": 100,
        "output_tokens": 3,
        "cache_read_tokens": 40,
    }


def test_reported_zero_is_observable_without_discarding_native_cache_counts() -> None:
    result = accumulate_usage(
        {
            "requests": 1,
            "input_tokens": 100,
            "output_tokens": 3,
            "cache_read_tokens": 40,
        },
        RequestUsage(
            input_tokens=60,
            output_tokens=2,
            details={
                "mdf2_cache_reported_requests": 1,
                "mdf2_cache_reported_input_tokens": 60,
            },
        ),
    )
    assert result["cache_read_tokens"] == 40
    assert result["cache_reported_requests"] == 1
    assert result["cache_reported_input_tokens"] == 60
    assert result["cache_reported_read_tokens"] == 0


def test_mixed_native_and_reported_usage_keeps_a_matching_cache_denominator() -> None:
    result = accumulate_usage(
        {},
        RunUsage(
            requests=2,
            input_tokens=180,
            output_tokens=5,
            cache_read_tokens=50,
            details={
                "mdf2_cache_reported_requests": 1,
                "mdf2_cache_reported_input_tokens": 80,
                "mdf2_cache_reported_read_tokens": 10,
            },
        ),
    )
    assert result["cache_read_tokens"] == 50
    assert result["cache_reported_read_tokens"] == 10
    assert result["cache_reported_input_tokens"] == 80

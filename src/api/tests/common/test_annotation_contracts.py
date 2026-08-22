"""Protect callable and streaming annotations used by typed consumers."""

from collections.abc import Callable
from typing import get_origin, get_type_hints

from flaskr.api.tts.tencent_provider import TencentTTSProvider
from flaskr.dao import retry_on_deadlock
from flaskr.framework.plugin.inject import inject
from flaskr.framework.plugin.plugin_manager import extensible


def test_retry_decorator_keeps_callable_annotation_and_behavior() -> None:
    """Retain the wrapped function's call signature for retry decorators."""

    @retry_on_deadlock()
    def increment(value: int) -> int:
        return value + 1

    assert increment(1) == 2
    assert get_origin(get_type_hints(retry_on_deadlock)["return"]) is Callable


def test_plugin_wrappers_keep_callable_annotation_and_behavior() -> None:
    """Retain callable contracts for plugin wrappers when no manager is active."""

    @inject
    def double(value: int) -> int:
        return value * 2

    @extensible
    def triple(value: int) -> int:
        return value * 3

    assert double(2) == 4
    assert triple(2) == 6
    assert get_origin(get_type_hints(inject)["return"]) is Callable
    assert get_origin(get_type_hints(extensible)["return"]) is Callable


def test_tencent_stream_contract_exposes_chunk_iterator() -> None:
    """Expose Tencent streaming output as an iterator of its SSE chunk type."""
    return_type = TencentTTSProvider.stream_synthesize.__annotations__["return"]

    assert return_type == "Iterator[TencentSSEStreamChunk]"

"""Protect callable and streaming annotations used by typed consumers."""

from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import get_args, get_origin, get_type_hints

from flask_sqlalchemy.query import Query
from flaskr.api.tts.tencent_provider import TencentSSEStreamChunk, TencentTTSProvider
from flaskr.dao import retry_on_deadlock
from flaskr.dao.uow import unit_of_work
from flaskr.framework.plugin.inject import inject
from flaskr.framework.plugin.plugin_manager import extensible
from flaskr.service.billing.api import (
    credit_decimal_to_number,
    quantize_credit_amount,
    to_decimal,
)
from flaskr.service.order.raw_snapshots import legacy_stripe_snapshot_query
from flaskr.service.tts.api import create_streaming_tts_processor
from flaskr.service.tts.streaming_tts import StreamingTTSProcessor
from flaskr.service.user.repository import transactional_session


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


def test_tts_factory_annotation_is_runtime_resolvable() -> None:
    """Expose the factory's concrete processor type to runtime type tooling."""
    assert (
        get_type_hints(create_streaming_tts_processor)["return"]
        is StreamingTTSProcessor
    )


def test_billing_facade_annotations_preserve_numeric_contracts() -> None:
    """Expose the concrete numerical types delegated to billing primitives."""
    assert get_type_hints(quantize_credit_amount)["return"] is Decimal
    assert get_type_hints(credit_decimal_to_number)["return"] == int | float
    assert get_type_hints(to_decimal)["return"] is Decimal


def test_snapshot_query_annotation_is_runtime_resolvable() -> None:
    """Expose the query factory's concrete type to runtime annotation tooling."""
    assert get_type_hints(legacy_stripe_snapshot_query)["return"] is Query


def test_context_manager_and_stream_annotations_are_runtime_resolvable() -> None:
    """Expose iterator contracts to both static and runtime type consumers."""
    stream_return = get_type_hints(TencentTTSProvider.stream_synthesize)["return"]
    uow_return = get_type_hints(unit_of_work)["return"]
    transaction_return = get_type_hints(transactional_session)["return"]

    assert get_origin(stream_return) is Iterator
    assert get_args(stream_return) == (TencentSSEStreamChunk,)
    assert get_origin(uow_return) is Iterator
    assert get_args(uow_return) == (None,)
    assert get_origin(transaction_return) is Iterator
    assert get_args(transaction_return) == (None,)

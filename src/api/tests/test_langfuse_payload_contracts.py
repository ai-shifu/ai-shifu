"""Verify trace payload normalization and facade update contracts."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.api import langfuse as tracing


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (" ", None),
        ("hello", "hello"),
        ("[broken]", "[broken]"),
        ({"first": ["one", None], "second": "two"}, "one, two"),
        (["one", None, "two"], "one, two"),
        (12, "12"),
        ("{'first': 'one', 'second': 'two'}", "one, two"),
    ],
)
def test_trace_input_normalizes_nested_answers_to_readable_text(
    value: object, expected: str | None
) -> None:
    assert tracing.normalize_langfuse_input_value(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (" ", None),
        ("value", "value"),
        (12, "12"),
        ({"z": 1, "a": 2}, '{"a": 2, "z": 1}'),
        (("one", None, "two"), '["one", "two"]'),
        ((None, ""), None),
        ('{"z": 1, "a": 2}', '{"a": 2, "z": 1}'),
    ],
)
def test_trace_output_preserves_structured_values(
    value: object, expected: str | None
) -> None:
    assert tracing.normalize_langfuse_output_value(value) == expected


def test_non_json_dictionary_output_uses_readable_fallback() -> None:
    output = tracing.normalize_langfuse_output_value({"nested": {1, 2}})
    assert output is not None
    assert "nested" in output


def test_json_encoder_failure_keeps_normalized_output_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tracing.json, "dumps", Mock(side_effect=ValueError("encoding unavailable"))
    )
    assert (
        tracing.normalize_langfuse_output_value(["first", "second"]) == "first\nsecond"
    )


def test_usage_object_preserves_zero_and_omits_absent_fields() -> None:
    usage = SimpleNamespace(input="3", output=0, total=None)
    assert tracing._usage_to_details(usage) == {"input": 3, "output": 0}
    assert tracing._usage_to_details(SimpleNamespace()) is None
    assert tracing._usage_to_details(None) is None


def test_observation_end_updates_payload_before_forwarding_explicit_end_time() -> None:
    delegate = Mock()
    handle = tracing.LangfuseObservationHandle(delegate, trace_id="a" * 32)
    end_time = datetime(2026, 9, 20)
    assert (
        handle.end(
            output="done", usage=SimpleNamespace(input=2, output=3), end_time=end_time
        )
        is handle
    )
    assert delegate.method_calls[0].args == ()
    delegate.update.assert_called_once_with(
        output="done", usage_details={"input": 2, "output": 3}
    )
    delegate.end.assert_called_once_with(end_time=end_time)
    assert [call[0] for call in delegate.method_calls] == ["update", "end"]


def test_empty_trace_update_is_noop_and_public_update_is_explicit() -> None:
    delegate = Mock()
    handle = tracing.LangfuseObservationHandle(delegate)
    assert handle.update_trace(unknown="ignored", output=" ") is handle
    delegate.assert_not_called()
    delegate.update.assert_not_called()
    delegate.set_trace_as_public.assert_not_called()
    handle.update_trace(public=True, output="result")
    delegate.update.assert_called_once_with(output="result")
    delegate.set_trace_as_public.assert_called_once()


def test_root_trace_can_be_explicitly_public_without_legacy_link_parameters() -> None:
    client = Mock()
    trace, root = tracing.create_trace_with_root_span(
        client=client,
        trace_payload={"id": "a" * 32, "public": True},
        root_span_payload={"parent_observation_id": "ignored"},
    )
    client.start_observation.assert_called_once_with(
        trace_context={"trace_id": "a" * 32}, name="trace"
    )
    client.start_observation.return_value.set_trace_as_public.assert_called_once()
    assert trace.trace_id == root.trace_id == "a" * 32

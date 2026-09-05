"""Verify model gateway validation and settlement coordination."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.route import model_gateway_runtime as runtime


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None, [], {}])
def test_gateway_rejects_non_boolean_stream_before_tokenization(value: object) -> None:
    with pytest.raises(runtime.GatewayRequestError) as raised:
        runtime.prepare_gateway_chat_request(
            Flask(__name__),
            creator_bid="user-1",
            idempotency_key="request-1",
            payload={
                "model": "rated-model",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": value,
            },
        )
    assert raised.value.status_code == 400
    assert raised.value.code == "stream_invalid"


@pytest.mark.parametrize(("field", "limit"), [("messages", 256), ("tools", 128)])
def test_gateway_rejects_oversized_collections_before_tokenization(
    field: str, limit: int
) -> None:
    payload = {"model": "rated-model", "messages": [{"role": "user", "content": "hi"}]}
    payload[field] = [{}] * (limit + 1)
    with pytest.raises(runtime.GatewayRequestError) as raised:
        runtime.prepare_gateway_chat_request(
            Flask(__name__),
            creator_bid="user-1",
            idempotency_key="request-1",
            payload=payload,
        )
    assert raised.value.status_code == 400
    assert raised.value.code == f"{field}_invalid"


@pytest.mark.parametrize("release_fails", [False, True])
def test_settlement_failure_does_not_escape_stream_finalization(
    monkeypatch: pytest.MonkeyPatch, release_fails: bool
) -> None:
    reservation = runtime.GatewayChatReservation(
        creator_bid="user-1",
        request_id="request-1",
        model="rated-model",
        messages=[],
        input_tokens=1,
        max_output_tokens=32,
        reservation_bid="hold-1",
        usage_bid="usage-1",
        provider_options={},
    )
    monkeypatch.setattr(runtime, "_trace_for_request", lambda _reservation: None)
    monkeypatch.setattr(
        "flaskr.api.llm.stream_openai_chat_completion",
        lambda *_args, **_kwargs: iter(
            [{"choices": [{"delta": {"content": "hello"}}]}]
        ),
    )
    capture = Mock(side_effect=RuntimeError("credit_wallet_version_conflict"))
    release = Mock(
        side_effect=RuntimeError("database unavailable") if release_fails else None
    )
    monkeypatch.setattr(runtime, "capture_metered_operation_credits", capture)
    monkeypatch.setattr(runtime, "release_reserved_operation_credits", release)
    assert (
        len(list(runtime.stream_gateway_chat_request(Flask(__name__), reservation)))
        == 1
    )
    assert capture.call_count == 2
    assert release.call_count == 1
    assert release.call_args.kwargs["reason"] == "settlement_failed"


def test_settlement_retries_actual_usage_without_releasing_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reservation = SimpleNamespace(
        request_id="request-1", reservation_bid="hold-1", usage_bid="usage-1"
    )
    capture = Mock(side_effect=[RuntimeError("credit_wallet_version_conflict"), None])
    release = Mock()
    monkeypatch.setattr(runtime, "capture_metered_operation_credits", capture)
    monkeypatch.setattr(runtime, "release_reserved_operation_credits", release)
    runtime._capture_completed(Flask(__name__), reservation)
    assert capture.call_count == 2
    assert capture.call_args_list[0] == capture.call_args_list[1]
    release.assert_not_called()


def test_prepare_gateway_request_reserves_conservative_amount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = Flask(__name__)
    captured: dict[str, object] = {}

    def count_tokens(
        _model: str,
        _messages: list[dict[str, object]],
        *,
        tools: object = None,
    ) -> int:
        del tools
        return 12

    monkeypatch.setattr(
        "flaskr.api.llm.count_llm_chat_input_tokens",
        count_tokens,
    )
    monkeypatch.setattr(
        "flaskr.api.llm.resolve_llm_max_output_tokens",
        lambda _model, requested=None: int(requested or 4096),
    )
    monkeypatch.setattr(
        runtime,
        "estimate_llm_operation_credits",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="rated", consumed_credits=Decimal("3.5")
        ),
    )

    def reserve(_app: Flask, **kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace(status="reserved", reservation_bid="hold-1")

    monkeypatch.setattr(runtime, "reserve_operation_credits", reserve)
    monkeypatch.setattr(runtime, "generate_id", lambda _app: "usage-1")

    reservation = runtime.prepare_gateway_chat_request(
        app,
        creator_bid="user-1",
        idempotency_key="request-1",
        payload={
            "model": "rated-model",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 256,
            "temperature": 0.2,
        },
    )

    assert reservation.input_tokens == 12
    assert reservation.max_output_tokens == 256
    assert reservation.usage_bid == "usage-1"
    assert captured["creator_bid"] == "user-1"
    assert captured["amount"] == Decimal("3.5")
    assert captured["operation_type"] == "model_gateway_llm"
    assert reservation.provider_options == {"temperature": 0.2, "max_tokens": 256}


def test_prepare_gateway_request_rejects_reused_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = Flask(__name__)
    monkeypatch.setattr(
        "flaskr.api.llm.count_llm_chat_input_tokens",
        lambda *_args, **_kwargs: 1,
    )
    monkeypatch.setattr(
        "flaskr.api.llm.resolve_llm_max_output_tokens",
        lambda *_args, **_kwargs: 32,
    )
    monkeypatch.setattr(
        runtime,
        "estimate_llm_operation_credits",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="rated", consumed_credits=Decimal(1)
        ),
    )
    monkeypatch.setattr(
        runtime,
        "reserve_operation_credits",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="already_reserved", reservation_bid="hold-existing"
        ),
    )

    with pytest.raises(runtime.GatewayRequestError) as raised:
        runtime.prepare_gateway_chat_request(
            app,
            creator_bid="user-1",
            idempotency_key="request-reused",
            payload={
                "model": "rated-model",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert raised.value.status_code == 409
    assert raised.value.code == "idempotency_conflict"


def test_prepare_gateway_request_rejects_oversized_idempotency_key() -> None:
    with pytest.raises(runtime.GatewayRequestError) as raised:
        runtime.prepare_gateway_chat_request(
            Flask(__name__),
            creator_bid="user-1",
            idempotency_key="x" * 91,
            payload={
                "model": "rated-model",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert raised.value.code == "idempotency_key_required"


def test_non_stream_provider_failure_releases_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = Flask(__name__)
    released: dict[str, object] = {}
    reservation = runtime.GatewayChatReservation(
        creator_bid="user-1",
        request_id="request-1",
        model="rated-model",
        messages=[{"role": "user", "content": "hello"}],
        input_tokens=4,
        max_output_tokens=32,
        reservation_bid="hold-1",
        usage_bid="usage-1",
        provider_options={"max_tokens": 32},
    )
    monkeypatch.setattr(runtime, "_trace_for_request", lambda _reservation: object())
    monkeypatch.setattr(
        "flaskr.api.llm.complete_openai_chat_completion",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider down")),
    )
    monkeypatch.setattr(
        runtime,
        "release_reserved_operation_credits",
        lambda _app, **kwargs: released.update(kwargs),
    )

    with pytest.raises(RuntimeError, match="provider down"):
        runtime.complete_gateway_chat_request(app, reservation)

    assert released == {
        "reservation_bid": "hold-1",
        "reason": "provider_failed_before_response",
    }


def test_chunk_output_detection_includes_tool_calls() -> None:
    assert runtime._chunk_has_output(
        {"choices": [{"delta": {"tool_calls": [{"id": "call-1"}]}}]}
    )
    assert not runtime._chunk_has_output({"choices": [{"delta": {}}]})


def test_stream_setup_failure_releases_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = Flask(__name__)
    released: dict[str, object] = {}
    reservation = runtime.GatewayChatReservation(
        creator_bid="user-1",
        request_id="request-stream-setup",
        model="rated-model",
        messages=[{"role": "user", "content": "hello"}],
        input_tokens=4,
        max_output_tokens=32,
        reservation_bid="hold-stream-setup",
        usage_bid="usage-stream-setup",
        provider_options={"max_tokens": 32},
    )
    monkeypatch.setattr(
        runtime,
        "_trace_for_request",
        lambda _reservation: (_ for _ in ()).throw(RuntimeError("trace unavailable")),
    )
    monkeypatch.setattr(
        runtime,
        "release_reserved_operation_credits",
        lambda _app, **kwargs: released.update(kwargs),
    )

    with pytest.raises(RuntimeError, match="trace unavailable"):
        list(runtime.stream_gateway_chat_request(app, reservation))

    assert released == {
        "reservation_bid": "hold-stream-setup",
        "reason": "stream_failed_before_output",
    }

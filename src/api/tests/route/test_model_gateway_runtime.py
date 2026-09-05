"""Verify model gateway validation and settlement coordination."""

from __future__ import annotations

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


@pytest.mark.parametrize("stream", [False, True])
def test_prepare_gateway_request_uses_admission_not_reservation(
    monkeypatch: pytest.MonkeyPatch, stream: bool
) -> None:
    app = Flask(__name__)
    admitted = []
    claimed = []
    monkeypatch.setattr(
        runtime, "admit_creator_usage", lambda _app, **kwargs: admitted.append(kwargs)
    )
    monkeypatch.setattr(runtime, "has_complete_llm_rates", lambda _model: True)
    monkeypatch.setattr(
        runtime,
        "_claim_gateway_request",
        lambda _app, user, request_id: claimed.append((user, request_id)),
    )
    monkeypatch.setattr(
        "flaskr.api.llm.count_llm_chat_input_tokens", lambda *_args, **_kwargs: 12
    )
    monkeypatch.setattr(
        "flaskr.api.llm.resolve_llm_max_output_tokens",
        lambda _model, requested=None: requested or 4096,
    )
    gateway_request = runtime.prepare_gateway_chat_request(
        app,
        creator_bid="user-1",
        idempotency_key="k" * 90,
        payload={
            "model": "rated-model",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 4096,
            "stream": stream,
            "temperature": 0.2,
            "billing_source": "untrusted",
        },
    )
    assert gateway_request.input_tokens == 12
    assert len(gateway_request.request_id) == 36
    assert gateway_request.provider_options == {"max_tokens": 4096, "temperature": 0.2}
    assert admitted == [
        {"creator_bid": "user-1", "usage_scene": runtime.BILL_USAGE_SCENE_PROD}
    ]
    assert claimed == [("user-1", gateway_request.request_id)]
    assert not hasattr(gateway_request, "reservation_bid")


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


def test_stream_gateway_finalizes_the_usage_iterator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = []

    def stream(*_args: object, **_kwargs: object) -> object:
        try:
            yield {"choices": [{"delta": {"content": "hello"}}]}
            yield {"choices": [{"delta": {"content": "world"}}]}
        finally:
            closed.append(True)

    monkeypatch.setattr("flaskr.api.llm.stream_openai_chat_completion", stream)
    monkeypatch.setattr(runtime, "_trace_for_request", lambda _request: None)
    gateway_request = runtime.GatewayChatRequest(
        creator_bid="user-1",
        request_id="request-1",
        model="rated-model",
        messages=[],
        input_tokens=1,
        provider_options={},
    )
    chunks = runtime.stream_gateway_chat_request(Flask(__name__), gateway_request)
    next(chunks)
    chunks.close()
    assert closed == [True]


def test_non_stream_gateway_does_not_pass_billing_controls_to_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}
    monkeypatch.setattr(runtime, "_trace_for_request", lambda _request: None)
    monkeypatch.setattr(
        "flaskr.api.llm.complete_openai_chat_completion",
        lambda _app, **kwargs: captured.update(kwargs) or {"id": "reply"},
    )
    request = runtime.GatewayChatRequest(
        creator_bid="user-1",
        request_id="request-1",
        model="rated-model",
        messages=[],
        input_tokens=2,
        provider_options={"max_tokens": 128},
    )
    assert runtime.complete_gateway_chat_request(Flask(__name__), request) == {
        "id": "reply"
    }
    assert captured == {
        "user_id": "user-1",
        "span": None,
        "model": "rated-model",
        "messages": [],
        "request_id": "request-1",
        "fallback_input_tokens": 2,
        "max_tokens": 128,
    }

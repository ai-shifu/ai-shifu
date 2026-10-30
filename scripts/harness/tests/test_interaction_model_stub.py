"""Verify the deterministic model sidecar's OpenAI wire and answer lifecycle."""

# ruff: noqa: S101 -- pytest assertions define the wire-protocol test contract.

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

import pytest

from scripts.harness.interaction_model_stub import InteractionModelHandler

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(scope="module")
def model_server() -> Iterator[int]:
    """Run the real stateless HTTP handler on a local ephemeral port."""
    with ThreadingHTTPServer(("127.0.0.1", 0), InteractionModelHandler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            thread.join(timeout=1)


def _payload(messages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "model": "gpt-test",
        "messages": messages
        or [
            {
                "role": "user",
                "content": "Choose a learning path.\n\n?[{{e2e_answer}} Visible A//a | Visible B//b]",
            }
        ],
        "tools": [
            {"type": "function", "function": {"name": name, "parameters": {}}}
            for name in ("interact", "finish")
        ],
    }


def _request(
    port: int, method: str, path: str, body: bytes | None = None
) -> tuple[int, str, str]:
    connection = HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request(
            method, path, body=body, headers={"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        return (
            response.status,
            response.getheader("Content-Type", ""),
            response.read().decode(),
        )
    finally:
        connection.close()


def _post(port: int, payload: dict[str, Any]) -> tuple[str, str]:
    status, content_type, body = _request(
        port, "POST", "/v1/chat/completions", json.dumps(payload).encode()
    )
    assert status == 200
    return content_type, body


def _message(port: int, payload: dict[str, Any]) -> dict[str, Any]:
    _, body = _post(port, payload)
    return json.loads(body)["choices"][0]["message"]


def test_health_and_model_discovery(model_server: int) -> None:
    """Readiness and the configured model are discoverable without an LLM call."""
    status, _, body = _request(model_server, "GET", "/health")
    assert status == 200
    assert json.loads(body) == {"status": "ok"}
    status, _, body = _request(model_server, "GET", "/v1/models")
    assert status == 200
    models = json.loads(body)
    assert models["object"] == "list"
    assert [model["id"] for model in models["data"]] == ["gpt-test"]


def test_nonstreaming_completion_uses_the_engine_interaction_schema(
    model_server: int,
) -> None:
    """The first request asks the authored question using stored option values."""
    content_type, body = _post(model_server, _payload())
    completion = json.loads(body)
    assert content_type == "application/json"
    assert completion["object"] == "chat.completion"
    assert completion["choices"][0]["finish_reason"] == "tool_calls"
    (call,) = completion["choices"][0]["message"]["tool_calls"]
    assert call["type"] == "function"
    assert call["function"]["name"] == "interact"
    assert json.loads(call["function"]["arguments"]) == {
        "type": "single",
        "prompt": "Choose a learning path",
        "variable": "e2e_answer",
        "options": [
            {"display": "Visible A", "value": "a"},
            {"display": "Visible B", "value": "b"},
        ],
    }
    assert completion["usage"]["total_tokens"] == 2


@pytest.mark.parametrize("with_usage", [False, True])
def test_stream_contains_indexed_tool_deltas_and_a_terminal_marker(
    model_server: int, with_usage: bool
) -> None:
    """The finite SSE stream carries tool deltas, finish reason and requested usage."""
    payload = {
        **_payload(),
        "stream": True,
        "stream_options": {"include_usage": with_usage},
    }
    content_type, body = _post(model_server, payload)
    frames = [frame.removeprefix("data: ") for frame in body.strip().split("\n\n")]
    assert content_type == "text/event-stream"
    assert frames.pop() == "[DONE]"
    chunks = [json.loads(frame) for frame in frames]
    assert all(chunk["object"] == "chat.completion.chunk" for chunk in chunks)
    delta = chunks[0]["choices"][0]["delta"]
    assert delta["role"] == "assistant"
    assert delta["tool_calls"][0]["index"] == 0
    assert delta["tool_calls"][0]["function"]["name"] == "interact"
    assert chunks[1]["choices"][0]["finish_reason"] == "tool_calls"
    if with_usage:
        assert chunks[-1]["choices"] == []
        assert chunks[-1]["usage"]["total_tokens"] == 2
    else:
        assert len(chunks) == 2


def test_answered_interaction_finishes_once_and_does_not_ask_again(
    model_server: int,
) -> None:
    """Only a matched interaction tool result allows finishing the lesson."""
    question = _message(model_server, _payload())
    call = question["tool_calls"][0]
    history = [
        question,
        {"role": "tool", "tool_call_id": call["id"], "content": "Learner chose: b"},
    ]
    finished = _message(model_server, _payload(history))
    finish_call = finished["tool_calls"][0]
    assert finish_call["function"]["name"] == "finish"
    assert json.loads(finish_call["function"]["arguments"]) == {
        "summary": "Learning path recorded"
    }
    history.extend(
        [
            finished,
            {
                "role": "tool",
                "tool_call_id": finish_call["id"],
                "content": "finished. The lesson is over",
            },
        ]
    )
    assert "tool_calls" not in _message(model_server, _payload(history))


def test_unrelated_tool_results_do_not_count_as_a_learner_answer(
    model_server: int,
) -> None:
    """A tool result without a matching interaction call cannot advance the fixture."""
    history = _payload()["messages"] + [
        {"role": "tool", "tool_call_id": "other-call", "content": "Learner chose: b"}
    ]
    message = _message(model_server, _payload(history))
    assert message["tool_calls"][0]["function"]["name"] == "interact"


def test_unrelated_engine_requests_do_not_receive_a_fixture_question(
    model_server: int,
) -> None:
    """Seed and other engine requests cannot get an interaction from tool names alone."""
    payload = _payload([{"role": "user", "content": "Summarize this course"}])
    assert "tool_calls" not in _message(model_server, payload)


def test_summary_requests_return_text_without_interactions(model_server: int) -> None:
    """Calls without the engine tools remain ordinary finite text completions."""
    payload = {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "Summarize"}],
    }
    content_type, body = _post(model_server, payload)
    completion = json.loads(body)
    assert content_type == "application/json"
    assert completion["choices"][0]["message"]["content"]
    assert "tool_calls" not in completion["choices"][0]["message"]
    assert completion["choices"][0]["finish_reason"] == "stop"


@pytest.mark.parametrize("body", ["not-json", "[]"])
def test_invalid_request_is_rejected_without_logging_content(
    model_server: int, body: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Malformed payloads receive a bounded error without content in server logs."""
    status, _, _ = _request(model_server, "POST", "/v1/chat/completions", body.encode())
    assert status == 400
    assert capsys.readouterr().err == ""

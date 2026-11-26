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


def _payload(input_items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "model": "gpt-test",
        "input": input_items
        or [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Choose a learning path.\n\n?[{{e2e_answer}} Visible A//a | Visible B//b]",
                    }
                ],
            }
        ],
        "tools": [
            {"type": "function", "name": name, "parameters": {}}
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
        port, "POST", "/v1/responses", json.dumps(payload).encode()
    )
    assert status == 200
    return content_type, body


def _output(port: int, payload: dict[str, Any]) -> list[dict[str, Any]]:
    _, body = _post(port, payload)
    return json.loads(body)["output"]


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
    assert completion["object"] == "response"
    assert completion["status"] == "completed"
    message, call = completion["output"]
    assert message["content"][0]["text"] == "e2e_answer"
    assert call["type"] == "function_call"
    assert call["name"] == "interact"
    assert json.loads(call["arguments"]) == {
        "type": "single",
        "question": "e2e_answer",
        "options": [
            {"display": "Visible A", "value": "a"},
            {"display": "Visible B", "value": "b"},
        ],
    }
    assert completion["usage"]["total_tokens"] == 2


def test_responses_stream_contains_text_tool_deltas_and_terminal_usage(
    model_server: int,
) -> None:
    """The finite SSE stream carries native item events and terminal usage."""
    payload = {**_payload(), "stream": True}
    content_type, body = _post(model_server, payload)
    events = []
    for index, frame in enumerate(body.strip().split("\n\n")):
        event_name, data = frame.split("\n", 1)
        event = json.loads(data.removeprefix("data: "))
        assert event_name == f"event: {event['type']}"
        assert event["sequence_number"] == index
        events.append(event)
    by_type = {event["type"]: event for event in events}
    assert content_type == "text/event-stream"
    assert events[0]["response"]["status"] == "in_progress"
    assert by_type["response.output_text.delta"]["delta"] == "e2e_answer"
    added = by_type["response.output_item.added"]
    arguments = by_type["response.function_call_arguments.delta"]
    assert added["item"]["name"] == "interact"
    assert added["item"]["arguments"] == ""
    assert arguments["item_id"] == added["item"]["id"]
    assert arguments["output_index"] == added["output_index"] == 1
    assert events[-1]["type"] == "response.completed"
    response = events[-1]["response"]
    assert response["usage"]["total_tokens"] == 2
    assert response["output"][1]["arguments"] == arguments["delta"]


def test_answered_interaction_finishes_once_and_does_not_ask_again(
    model_server: int,
) -> None:
    """Only a matched interaction tool result allows finishing the lesson."""
    authored = _payload()
    _, call = _output(model_server, authored)
    history = [
        *authored["input"],
        call,
        {
            "type": "function_call_output",
            "call_id": call["call_id"],
            "output": [{"type": "input_text", "text": "Learner chose: b"}],
        },
    ]
    _, finish_call = _output(model_server, _payload(history))
    assert finish_call["name"] == "finish"
    assert json.loads(finish_call["arguments"]) == {"summary": "Learning path recorded"}
    history.extend(
        [
            finish_call,
            {
                "type": "function_call_output",
                "call_id": finish_call["call_id"],
                "output": "finished. The lesson is over",
            },
        ]
    )
    (message,) = _output(model_server, _payload(history))
    assert message["content"][0]["text"] == "Learning path recorded."


def test_unrelated_tool_results_do_not_count_as_a_learner_answer(
    model_server: int,
) -> None:
    """A tool result without a matching interaction call cannot advance the fixture."""
    history = _payload()["input"] + [
        {
            "type": "function_call_output",
            "call_id": "other-call",
            "output": "Learner chose: b",
        }
    ]
    _, call = _output(model_server, _payload(history))
    assert call["name"] == "interact"


def test_unrelated_engine_requests_do_not_receive_a_fixture_question(
    model_server: int,
) -> None:
    """Seed and other engine requests cannot get an interaction from tool names alone."""
    payload = _payload([{"role": "user", "content": "Summarize this course"}])
    (message,) = _output(model_server, payload)
    assert message["type"] == "message"


def test_summary_requests_return_text_without_interactions(model_server: int) -> None:
    """Calls without the engine tools remain ordinary finite text completions."""
    payload = {"model": "gpt-test", "input": "Summarize"}
    content_type, body = _post(model_server, payload)
    completion = json.loads(body)
    assert content_type == "application/json"
    (message,) = completion["output"]
    assert message["content"][0]["text"]
    assert completion["status"] == "completed"


def test_chat_completions_is_unavailable(model_server: int) -> None:
    """An accidental fallback to Chat Completions cannot pass the harness."""
    status, _, _ = _request(model_server, "POST", "/v1/chat/completions", b"{}")
    assert status == 404


@pytest.mark.parametrize("body", ["not-json", "[]"])
def test_invalid_request_is_rejected_without_logging_content(
    model_server: int, body: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Malformed payloads receive a bounded error without content in server logs."""
    status, _, _ = _request(model_server, "POST", "/v1/responses", body.encode())
    assert status == 400
    assert capsys.readouterr().err == ""

#!/usr/bin/env python3
"""Serve deterministic OpenAI responses for the interaction browser harness."""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

RESPONSES_USAGE = {
    "input_tokens": 1,
    "input_tokens_details": {"cached_tokens": 0},
    "output_tokens": 1,
    "output_tokens_details": {"reasoning_tokens": 0},
    "total_tokens": 2,
}
MODEL = {"id": "gpt-test", "object": "model", "created": 0, "owned_by": "harness"}
QUESTION = {
    "type": "single",
    "question": "e2e_answer",
    "options": [
        {"display": "Visible A", "value": "a"},
        {"display": "Visible B", "value": "b"},
    ],
}


def responses_text(content: str | list[dict[str, Any]]) -> str:
    """Read plain text from Responses strings or text part arrays."""
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content)


def responses_output(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Ask once, then finish only after the engine returns the learner's answer."""
    tools = {
        tool["name"]
        for tool in payload.get("tools", [])
        if tool.get("type") == "function"
    }
    items = payload.get("input", [])
    if isinstance(items, str):
        items = [{"role": "user", "content": items}]
    authored = any(
        re.search(
            r"\?\[\s*%?\{\{\s*e2e_answer\s*\}\}",
            responses_text(item.get("content", "")),
        )
        for item in items
        if item.get("role") == "user"
    )
    calls = {
        item["call_id"]: item["name"]
        for item in items
        if item.get("type") == "function_call"
    }
    returned = {
        calls.get(item.get("call_id"))
        for item in items
        if item.get("type") == "function_call_output"
        and responses_text(item["output"]).startswith(
            ("Learner chose:", "Learner wrote:", "finished.")
        )
    }
    name = None
    content = "Learning path recorded." if returned else "Choose a learning path."
    if authored and "interact" in tools and "interact" not in returned:
        name, arguments = "interact", QUESTION
        content = QUESTION["question"]
    elif "finish" in tools and "interact" in returned and "finish" not in returned:
        name, arguments = "finish", {"summary": "Learning path recorded"}
    output: list[dict[str, Any]] = [
        {
            "type": "message",
            "id": "msg_harness",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": content, "annotations": []}],
        }
    ]
    if name:
        output.append(
            {
                "type": "function_call",
                "id": f"fc_harness_{name}",
                "call_id": f"call_harness_{name}",
                "name": name,
                "arguments": json.dumps(arguments),
                "status": "completed",
            }
        )
    return output


def responses_events(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the native Responses SSE lifecycle for text and function calls."""
    pending = {**response, "status": "in_progress", "output": [], "usage": None}
    events = [{"type": "response.created", "response": pending}]
    for index, item in enumerate(response["output"]):
        output_ref = {"output_index": index}
        item_ref = {**output_ref, "item_id": item["id"]}
        partial_item = {**item, "status": "in_progress"}
        if item["type"] == "message":
            partial_item["content"] = []
            (part,) = item["content"]
            text_ref = {**item_ref, "content_index": 0}
            item_events = [
                {
                    "type": "response.content_part.added",
                    **text_ref,
                    "part": {**part, "text": ""},
                },
                {
                    "type": "response.output_text.delta",
                    **text_ref,
                    "delta": part["text"],
                    "logprobs": [],
                },
                {
                    "type": "response.output_text.done",
                    **text_ref,
                    "text": part["text"],
                    "logprobs": [],
                },
                {"type": "response.content_part.done", **text_ref, "part": part},
            ]
        else:
            partial_item["arguments"] = ""
            item_events = [
                {
                    "type": "response.function_call_arguments.delta",
                    **item_ref,
                    "delta": item["arguments"],
                },
                {
                    "type": "response.function_call_arguments.done",
                    **item_ref,
                    "name": item["name"],
                    "arguments": item["arguments"],
                },
            ]
        events.extend(
            [
                {
                    "type": "response.output_item.added",
                    **output_ref,
                    "item": partial_item,
                },
                *item_events,
                {"type": "response.output_item.done", **output_ref, "item": item},
            ]
        )
    events.append({"type": "response.completed", "response": response})
    return events


class InteractionModelHandler(BaseHTTPRequestHandler):
    """Expose readiness, model discovery, and deterministic generation."""

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        """Report readiness and expose the single deterministic test model."""
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        elif self.path == "/v1/models":
            self._send_json(200, {"object": "list", "data": [MODEL]})
        else:
            self._send_json(404, {"error": {"message": "Not found"}})

    def do_POST(self) -> None:
        """Return a regular response or a finite SSE stream with tool deltas."""
        if self.path != "/v1/responses":
            self._send_json(404, {"error": {"message": "Not found"}})
            return
        try:
            payload = json.loads(
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
            )
        except ValueError:
            self._send_json(400, {"error": {"message": "Invalid JSON request"}})
            return
        if not isinstance(payload, dict):
            self._send_json(400, {"error": {"message": "Invalid JSON request"}})
            return
        self._send_responses(payload)

    def _send_responses(self, payload: dict[str, Any]) -> None:
        response = {
            "id": "resp_harness",
            "created_at": 0,
            "model": payload.get("model", "gpt-test"),
            "object": "response",
            "status": "completed",
            "output": responses_output(payload),
            "usage": RESPONSES_USAGE,
        }
        if not payload.get("stream"):
            self._send_json(200, response)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for index, event in enumerate(responses_events(response)):
            frame = json.dumps({**event, "sequence_number": index})
            self.wfile.write(f"event: {event['type']}\ndata: {frame}\n\n".encode())
        self.wfile.flush()

    def log_message(self, _format: str, *_args: object) -> None:
        """Avoid logging request paths, prompts, answers or headers."""


if __name__ == "__main__":
    # The stub is reachable only on the isolated Runtime Harness compose network.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 - isolated compose service
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), InteractionModelHandler).serve_forever()

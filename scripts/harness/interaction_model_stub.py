#!/usr/bin/env python3
"""Serve deterministic OpenAI chat responses for the interaction browser harness."""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

USAGE = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
MODEL = {"id": "gpt-test", "object": "model", "created": 0, "owned_by": "harness"}
QUESTION = {
    "type": "single",
    "prompt": "Choose a learning path",
    "variable": "e2e_answer",
    "options": [
        {"display": "Visible A", "value": "a"},
        {"display": "Visible B", "value": "b"},
    ],
}


def response_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Ask once, then finish only after the engine returns the learner's answer."""
    tools = {tool["function"]["name"] for tool in payload.get("tools", [])}
    messages = payload.get("messages", [])
    authored = any(
        re.search(r"\?\[\s*%?\{\{\s*e2e_answer\s*\}\}", str(message.get("content", "")))
        for message in messages
        if message.get("role") == "user"
    )
    calls = {
        call["id"]: call["function"]["name"]
        for message in messages
        for call in message.get("tool_calls", [])
    }
    returned = {
        calls.get(message.get("tool_call_id"))
        for message in messages
        if message.get("role") == "tool"
        and str(message.get("content", "")).startswith(
            ("Learner chose:", "Learner wrote:", "finished.")
        )
    }
    name = None
    if authored and "interact" in tools and "interact" not in returned:
        name, arguments = "interact", QUESTION
    elif "finish" in tools and "interact" in returned and "finish" not in returned:
        name, arguments = "finish", {"summary": "Learning path recorded"}
    message: dict[str, Any] = {
        "role": "assistant",
        "content": "Learning path recorded." if returned else "Choose a learning path.",
    }
    if name:
        message["tool_calls"] = [
            {
                "id": f"call_harness_{name}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ]
    return message


class InteractionModelHandler(BaseHTTPRequestHandler):
    """Expose only readiness, model discovery and OpenAI chat-completion endpoints."""

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
        """Return a regular completion or finite SSE stream with OpenAI tool deltas."""
        if self.path != "/v1/chat/completions":
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
        message = response_message(payload)
        base = {
            "id": "chatcmpl-harness",
            "created": 0,
            "model": payload.get("model", "gpt-test"),
            "object": "chat.completion",
        }
        reason = "tool_calls" if message.get("tool_calls") else "stop"
        if not payload.get("stream"):
            self._send_json(
                200,
                {
                    **base,
                    "choices": [
                        {"index": 0, "message": message, "finish_reason": reason}
                    ],
                    "usage": USAGE,
                },
            )
            return
        if message.get("tool_calls"):
            message["tool_calls"][0]["index"] = 0
        base["object"] = "chat.completion.chunk"
        chunks = [
            {
                **base,
                "choices": [{"index": 0, "delta": message, "finish_reason": None}],
            },
            {
                **base,
                "choices": [{"index": 0, "delta": {}, "finish_reason": reason}],
            },
        ]
        if payload.get("stream_options", {}).get("include_usage"):
            chunks.append({**base, "choices": [], "usage": USAGE})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
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

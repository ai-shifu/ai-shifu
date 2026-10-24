"""Exercise ordinary Pro requests through LiteLLM's real Responses bridge."""

import importlib.metadata
import json
import os
import subprocess
import sys
import textwrap

import pytest


def _litellm_is_installed() -> bool:
    try:
        importlib.metadata.version("litellm")
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


@pytest.mark.skipif(
    not _litellm_is_installed(),
    reason="install requirements.txt to run the native LiteLLM Responses contract",
)
def test_pro_completion_uses_real_responses_bridge_without_mcp_tools() -> None:
    # Other LLM unit tests deliberately install SDK stubs. A fresh process must
    # import the real Responses dependencies before it can reach this transport.
    script = textwrap.dedent(
        r"""
        import json

        import httpx
        import litellm
        from flaskr.api import llm
        from litellm.llms.custom_httpx.http_handler import HTTPHandler

        contracts = []
        for model in ("gpt-5-pro", "gpt-5.2-pro", "gpt-5.4-pro", "gpt-5.5-pro"):
            for stream in (False, True):
                captured = []
                payload = {
                    "id": "resp-contract",
                    "object": "response",
                    "created_at": 1,
                    "status": "completed",
                    "model": model,
                    "output": [{
                        "id": "msg-contract",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{
                            "type": "output_text",
                            "text": "Hello world",
                            "annotations": [],
                        }],
                    }],
                    "usage": {
                        "input_tokens": 3,
                        "input_tokens_details": {"cached_tokens": 0},
                        "output_tokens": 2,
                        "output_tokens_details": {"reasoning_tokens": 0},
                        "total_tokens": 5,
                    },
                    "parallel_tool_calls": False,
                    "tools": [],
                    "tool_choice": "auto",
                }

                def respond(request):
                    body = json.loads(request.content)
                    captured.append({
                        "url": str(request.url),
                        "body": body,
                    })
                    if not body.get("stream", False):
                        return httpx.Response(200, json=payload, request=request)
                    events = [
                        {
                            "type": "response.output_text.delta",
                            "sequence_number": 0,
                            "item_id": "msg-contract",
                            "output_index": 0,
                            "content_index": 0,
                            "delta": "Hello world",
                            "logprobs": [],
                        },
                        {
                            "type": "response.completed",
                            "sequence_number": 1,
                            "response": payload,
                        },
                    ]
                    sse = "".join(
                        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
                        for event in events
                    )
                    return httpx.Response(
                        200,
                        headers={"content-type": "text/event-stream"},
                        content=sse,
                        request=request,
                    )

                with httpx.Client(
                    transport=httpx.MockTransport(respond), trust_env=False
                ) as http:
                    params = llm._prepare_litellm_request_kwargs(
                        "openai", model, {"custom_llm_provider": "openai"}, {}
                    )
                    result = litellm.completion(
                        model=model,
                        custom_llm_provider="openai",
                        api_base="https://llm.invalid/v1",
                        api_key="test-key",
                        client=HTTPHandler(client=http),
                        messages=[{"role": "user", "content": "hello"}],
                        stream=stream,
                        stream_options={"include_usage": True} if stream else None,
                        max_tokens=2048,
                        tools=[{
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "parameters": {"type": "object", "properties": {}},
                            },
                        }],
                        tool_choice="auto",
                        parallel_tool_calls=False,
                        num_retries=0,
                        **params,
                    )
                    if stream:
                        chunks = list(result)
                        content = "".join(
                            chunk.choices[0].delta.content or ""
                            for chunk in chunks if chunk.choices
                        )
                        usages = [
                            chunk.usage for chunk in chunks
                            if getattr(chunk, "usage", None) is not None
                        ]
                        assert len(usages) == 1
                        usage = usages[0]
                        assert any(
                            chunk.choices and chunk.choices[0].finish_reason == "stop"
                            for chunk in chunks
                        )
                    else:
                        content = result.choices[0].message.content
                        usage = result.usage
                        assert result.choices[0].finish_reason == "stop"
                    assert len(captured) == 1
                    contracts.append({
                        **captured[0],
                        "model": model,
                        "stream": stream,
                        "content": content,
                        "usage": [usage.prompt_tokens, usage.completion_tokens, usage.total_tokens],
                    })
        print(json.dumps(contracts))
        """
    )
    env = os.environ.copy()
    env.update(
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        PYTHON_DOTENV_DISABLED="1",
        SKIP_LOAD_DOTENV="1",
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        env=env,
        text=True,
        timeout=45,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    contracts = json.loads(completed.stdout.strip().splitlines()[-1])
    assert len(contracts) == 8
    for contract in contracts:
        body = contract["body"]
        assert contract["url"] == "https://llm.invalid/v1/responses"
        assert body["model"] == contract["model"]
        assert body["input"] == [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ]
        assert body["reasoning"] == {
            "effort": "high" if contract["model"] == "gpt-5-pro" else "medium"
        }
        assert "temperature" not in body
        assert body["max_output_tokens"] == 2048
        assert body.get("stream", False) is (
            contract["stream"] and contract["model"] != "gpt-5-pro"
        )
        assert len(body["tools"]) == 1
        tool = body["tools"][0]
        assert tool["type"] == "function"
        assert tool["name"] == "lookup"
        assert tool["parameters"] == {"type": "object", "properties": {}}
        assert body["tool_choice"] == "auto"
        assert body["parallel_tool_calls"] is False
        assert contract["content"] == "Hello world"
        assert contract["usage"] == [3, 2, 5]

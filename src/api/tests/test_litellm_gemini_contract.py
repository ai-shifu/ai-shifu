"""Exercise Gemini sampling options through the real LiteLLM adapter."""

import importlib.metadata
import os
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.skipif(
    next(importlib.metadata.distributions(name="litellm"), None) is None,
    reason="install requirements.txt to run the native LiteLLM Gemini contract",
)
def test_gemini_sampling_options_follow_provider_capabilities() -> None:
    # A subprocess avoids the lightweight LiteLLM stubs used by other tests.
    script = textwrap.dedent(
        """
        import json

        import httpx
        import litellm
        from litellm.llms.custom_httpx.http_handler import HTTPHandler

        from flaskr.api.llm import _prepare_litellm_request_kwargs

        captured = []

        def respond(request):
            captured.append(json.loads(request.content)["generationConfig"])
            return httpx.Response(200, json={
                "candidates": [{
                    "content": {"parts": [{"text": "Hello"}], "role": "model"},
                    "finishReason": "STOP",
                }],
                "usageMetadata": {
                    "promptTokenCount": 2,
                    "candidatesTokenCount": 1,
                    "totalTokenCount": 3,
                },
            })

        sampling_options = {"temperature": 0.4, "top_p": 0.7, "top_k": 3}
        with httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as http:
            for model, supports_sampling in (
                ("gemini-3.5-flash-lite", False),
                ("gemini-3.6-flash", False),
                ("gemini-3.7-flash", False),
                ("gemini-3.8-flash", False),
                ("gemini-3.1-pro-preview", True),
                ("gemini-2.5-flash", True),
                ("gemini-3-unknown-preview", True),
            ):
                params = _prepare_litellm_request_kwargs(
                    "gemini", model, {"custom_llm_provider": "gemini"},
                    {**sampling_options, "temperature": "0.4", "max_tokens": 256},
                )
                response = litellm.completion(
                    model=model, custom_llm_provider="gemini", api_key="test-key",
                    client=HTTPHandler(client=http),
                    messages=[{"role": "user", "content": "Hello"}],
                    num_retries=0, **params,
                )
                assert response.choices[0].message.content == "Hello", model
                generation_config = captured.pop()
                assert generation_config["max_output_tokens"] == 256, model
                assert {
                    key: generation_config[key]
                    for key in sampling_options if key in generation_config
                } == (sampling_options if supports_sampling else {}), model
        """
    )
    env = {
        **os.environ,
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "PYTHON_DOTENV_DISABLED": "1",
        "SKIP_LOAD_DOTENV": "1",
    }
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        env=env,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

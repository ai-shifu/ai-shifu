from types import SimpleNamespace

from flaskr.service.common.models import ERROR_CODE
from flaskr.service.learn.ask_provider_adapters import AskProviderError


class _FakeGeneration:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.end_kwargs = {}

    def end(self, **kwargs):
        self.end_kwargs = kwargs


class _FakeSpan:
    def __init__(self):
        self.generations = []
        self.end_kwargs = {}

    def generation(self, **kwargs):
        generation = _FakeGeneration(**kwargs)
        self.generations.append(generation)
        return generation

    def end(self, **kwargs):
        self.end_kwargs = kwargs


class _FakeTrace:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.updated = {}
        self.span_calls = []
        self.last_span = None

    def span(self, **kwargs):
        self.span_calls.append(kwargs)
        self.last_span = _FakeSpan()
        return self.last_span

    def update(self, **kwargs):
        self.updated = kwargs


class _FakeLangfuseClient:
    def __init__(self):
        self.traces = []

    def trace(self, **kwargs):
        trace = _FakeTrace(**kwargs)
        self.traces.append(trace)
        return trace


def test_ask_preview_route_success_with_provider(monkeypatch, test_client):
    fake_langfuse = _FakeLangfuseClient()

    def fake_stream_ask_provider_response(*args, **kwargs):
        _ = args
        provider = kwargs.get("provider", "")
        assert provider == "dify"
        yield SimpleNamespace(content="provider result")

    monkeypatch.setattr(
        "flaskr.service.learn.ask_provider_adapters.stream_ask_provider_response",
        fake_stream_ask_provider_response,
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.route.langfuse_client",
        fake_langfuse,
        raising=False,
    )

    resp = test_client.post(
        "/api/shifu/ask/preview",
        json={
            "query": "hello",
            "ask_model": "gpt-test",
            "ask_provider_config": {
                "provider": "dify",
                "mode": "provider_only",
                "config": {
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-api-key",
                },
            },
        },
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["answer"] == "provider result"
    assert payload["data"]["provider"] == "dify"
    assert payload["data"]["requested_provider"] == "dify"
    assert payload["data"]["fallback_used"] is False
    assert len(fake_langfuse.traces) == 1
    trace = fake_langfuse.traces[0]
    assert trace.last_span is not None
    assert len(trace.last_span.generations) == 1
    generation = trace.last_span.generations[0]
    assert generation.kwargs["model"] == "dify"
    assert generation.end_kwargs["metadata"]["provider_config"]["config"][
        "api_key"
    ] == ("[REDACTED]")
    assert generation.end_kwargs["output"] == "provider result"
    assert trace.last_span.end_kwargs["output"] == "provider result"
    assert trace.updated["output"] == "provider result"


def test_ask_preview_route_fallbacks_to_llm(monkeypatch, test_client):
    def fake_stream_ask_provider_response(*args, **kwargs):
        _ = args
        provider = kwargs.get("provider", "")
        if provider == "dify":
            raise AskProviderError("provider failed")
        assert provider == "llm"
        yield SimpleNamespace(content="llm fallback")

    monkeypatch.setattr(
        "flaskr.service.learn.ask_provider_adapters.stream_ask_provider_response",
        fake_stream_ask_provider_response,
        raising=False,
    )

    resp = test_client.post(
        "/api/shifu/ask/preview",
        json={
            "query": "hello",
            "ask_model": "gpt-test",
            "ask_provider_config": {
                "provider": "dify",
                "mode": "provider_then_llm",
                "config": {
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-api-key",
                },
            },
        },
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["answer"] == "llm fallback"
    assert payload["data"]["provider"] == "llm"
    assert payload["data"]["requested_provider"] == "dify"
    assert payload["data"]["fallback_used"] is True
    assert "provider failed" in payload["data"]["provider_error"]


def test_ask_preview_route_rejects_empty_query(test_client):
    resp = test_client.post(
        "/api/shifu/ask/preview",
        json={
            "query": "",
            "ask_model": "gpt-test",
            "ask_provider_config": {
                "provider": "llm",
                "mode": "provider_then_llm",
                "config": {},
            },
        },
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == ERROR_CODE["server.common.paramsError"]


def test_ask_preview_route_provider_only_does_not_require_ask_model(
    monkeypatch, test_client
):
    def fake_stream_ask_provider_response(*args, **kwargs):
        _ = args
        provider = kwargs.get("provider", "")
        assert provider == "coze"
        yield SimpleNamespace(content="coze result")

    monkeypatch.setattr(
        "flaskr.service.learn.ask_provider_adapters.stream_ask_provider_response",
        fake_stream_ask_provider_response,
        raising=False,
    )

    resp = test_client.post(
        "/api/shifu/ask/preview",
        json={
            "query": "hello",
            "ask_provider_config": {
                "provider": "coze",
                "mode": "provider_only",
                "config": {
                    "base_url": "https://api.coze.com",
                    "api_key": "test-api-key",
                    "bot_id": "bot-1",
                },
            },
        },
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["answer"] == "coze result"
    assert payload["data"]["provider"] == "coze"
    assert payload["data"]["requested_provider"] == "coze"
    assert payload["data"]["fallback_used"] is False


def test_ask_preview_route_provider_only_accepts_coze_workflow(
    monkeypatch, test_client
):
    def fake_stream_ask_provider_response(*args, **kwargs):
        _ = args
        provider = kwargs.get("provider", "")
        assert provider == "coze_workflow"
        yield SimpleNamespace(content="workflow result")

    monkeypatch.setattr(
        "flaskr.service.learn.ask_provider_adapters.stream_ask_provider_response",
        fake_stream_ask_provider_response,
        raising=False,
    )

    resp = test_client.post(
        "/api/shifu/ask/preview",
        json={
            "query": "hello",
            "ask_provider_config": {
                "provider": "coze_workflow",
                "mode": "provider_only",
                "config": {
                    "base_url": "https://api.coze.cn",
                    "api_key": "test-api-key",
                    "workflow_id": "workflow-1",
                },
            },
        },
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["answer"] == "workflow result"
    assert payload["data"]["provider"] == "coze_workflow"
    assert payload["data"]["requested_provider"] == "coze_workflow"
    assert payload["data"]["fallback_used"] is False

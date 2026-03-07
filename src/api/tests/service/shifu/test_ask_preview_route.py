from types import SimpleNamespace

from flaskr.service.common.models import ERROR_CODE
from flaskr.service.learn.ask_provider_adapters import AskProviderError


def test_ask_preview_route_success_with_provider(monkeypatch, test_client):
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

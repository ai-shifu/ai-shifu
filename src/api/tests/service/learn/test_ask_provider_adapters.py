import types

import pytest
import requests

from flaskr.service.learn import ask_provider_adapters as module
from flaskr.service.learn.ask_provider_adapters import (
    common,
    coze_adapter,
    coze_workflow_adapter,
    dify_adapter,
    volc_knowledge_adapter,
)


class _FakeResponse:
    def __init__(
        self,
        lines=None,
        status_code=200,
        text="",
        http_error=None,
        json_data=None,
        json_error=None,
    ):
        self._lines = lines or []
        self.status_code = status_code
        self.text = text
        self._http_error = http_error
        self._json_data = json_data
        self._json_error = json_error

    def iter_lines(self, decode_unicode=True):
        _ = decode_unicode
        for line in self._lines:
            yield line

    def raise_for_status(self):
        if self._http_error is not None:
            raise self._http_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_data


def test_dify_adapter_streams_success_content(app, monkeypatch):
    adapter = module.DifyAskProviderAdapter()
    request_state = {}

    monkeypatch.setattr(
        common,
        "get_config",
        lambda key: {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get(key),
    )

    def _fake_post(*_args, **kwargs):
        request_state["json"] = kwargs.get("json")
        return _FakeResponse(
            lines=[
                'data: {"event":"message","answer":"hello"}',
                'data: {"event":"message","answer":" world"}',
                "data: [DONE]",
            ]
        )

    monkeypatch.setattr(
        dify_adapter.requests,
        "post",
        _fake_post,
    )

    chunks = list(
        adapter.stream_answer(
            app=app,
            user_id="user-1",
            user_query="hello",
            messages=[
                {"role": "system", "content": "course prompt"},
                {"role": "user", "content": "previous question"},
                {"role": "assistant", "content": "previous answer"},
                {"role": "user", "content": "hello"},
            ],
            provider_config={
                "config": {
                    "base_url": "https://dify.example.com",
                    "api_key": "test-key",
                }
            },
        )
    )

    assert [chunk.content for chunk in chunks] == ["hello", " world"]
    assert request_state["json"]["query"] == (
        "[system]\ncourse prompt\n\n"
        "[user]\nprevious question\n\n"
        "[assistant]\nprevious answer\n\n"
        "[user]\nhello"
    )


def test_coze_adapter_timeout_raises_timeout_error(app, monkeypatch):
    adapter = module.CozeAskProviderAdapter()

    monkeypatch.setattr(
        common,
        "get_config",
        lambda key: {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get(key),
    )

    def _raise_timeout(*_args, **_kwargs):
        raise requests.Timeout("timeout")

    monkeypatch.setattr(coze_adapter.requests, "post", _raise_timeout)

    with pytest.raises(module.AskProviderTimeoutError):
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "base_url": "https://coze.example.com",
                        "api_key": "test-key",
                        "bot_id": "bot-1",
                    }
                },
            )
        )


def test_stream_ask_provider_response_raises_error_for_unsupported_provider(app):
    with pytest.raises(module.AskProviderConfigError):
        list(
            module.stream_ask_provider_response(
                app=app,
                provider="unsupported",
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={"config": {}},
            )
        )


def test_coze_adapter_http_error_raises_provider_error(app, monkeypatch):
    adapter = module.CozeAskProviderAdapter()

    monkeypatch.setattr(
        common,
        "get_config",
        lambda key: {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get(key),
    )

    http_error = requests.HTTPError("boom")
    monkeypatch.setattr(
        coze_adapter.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            text="coze bad request",
            status_code=400,
            http_error=http_error,
        ),
    )

    with pytest.raises(module.AskProviderError, match="coze request failed"):
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "base_url": "https://coze.example.com",
                        "api_key": "test-key",
                        "bot_id": "bot-1",
                    }
                },
            )
        )


def test_coze_workflow_adapter_streams_success_content(app, monkeypatch):
    adapter = module.CozeWorkflowAskProviderAdapter()
    request_state = {}

    monkeypatch.setattr(
        common,
        "get_config",
        lambda key: {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get(key),
    )

    def _fake_post(url, **kwargs):
        request_state["url"] = url
        request_state["json"] = kwargs.get("json")
        request_state["headers"] = kwargs.get("headers") or {}
        return _FakeResponse(
            json_data={
                "code": 0,
                "data": (
                    '{"concepts":[{"output":"title:Workflow concept\\nsummary:Explain the concept."}],'
                    '"values":[{"title":"Workflow value","summary":"Highlights the value."}]}'
                ),
            }
        )

    monkeypatch.setattr(
        coze_workflow_adapter.requests,
        "post",
        _fake_post,
    )

    chunks = list(
        adapter.stream_answer(
            app=app,
            user_id="user-1",
            user_query="hello workflow",
            messages=[],
            provider_config={
                "config": {
                    "api_key": "test-key",
                    "workflow_id": "workflow-1",
                }
            },
        )
    )

    assert request_state["url"] == "https://api.coze.cn/v1/workflow/run"
    assert request_state["json"] == {
        "workflow_id": "workflow-1",
        "parameters": {"query": "hello workflow"},
    }
    assert request_state["headers"]["Authorization"] == "Bearer test-key"
    assert len(chunks) == 1
    assert chunks[0].content == (
        "## Concepts\n"
        "1. Workflow concept\n"
        "Explain the concept.\n\n"
        "## Values\n"
        "1. Workflow value\n"
        "Highlights the value."
    )


def test_coze_workflow_adapter_nonzero_code_raises_provider_error(app, monkeypatch):
    adapter = module.CozeWorkflowAskProviderAdapter()

    monkeypatch.setattr(
        common,
        "get_config",
        lambda key: {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get(key),
    )

    monkeypatch.setattr(
        coze_workflow_adapter.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            json_data={
                "code": 5000,
                "msg": "service internal error, please retry after",
                "detail": {"logid": "coze-log-id"},
            }
        ),
    )

    with pytest.raises(
        module.AskProviderError,
        match="coze_workflow error \\[5000\\]: service internal error, please retry after",
    ):
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "api_key": "test-key",
                        "workflow_id": "workflow-1",
                    }
                },
            )
        )


def test_dify_adapter_missing_shifu_config_raises_config_error(app):
    adapter = module.DifyAskProviderAdapter()

    with pytest.raises(module.AskProviderConfigError, match="base_url/api_key"):
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={"config": {}},
            )
        )


def test_coze_adapter_missing_shifu_config_raises_config_error(app):
    adapter = module.CozeAskProviderAdapter()

    with pytest.raises(module.AskProviderConfigError, match="api_key is required"):
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={"config": {"bot_id": "bot-1"}},
            )
        )


def test_coze_workflow_adapter_missing_shifu_config_raises_config_error(app):
    adapter = module.CozeWorkflowAskProviderAdapter()

    with pytest.raises(
        module.AskProviderConfigError, match="api_key/workflow_id are required"
    ):
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={"config": {"workflow_id": "workflow-1"}},
            )
        )


def test_coze_adapter_uses_default_base_url_when_missing(app, monkeypatch):
    adapter = module.CozeAskProviderAdapter()
    request_state = {}

    monkeypatch.setattr(
        common,
        "get_config",
        lambda key: {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get(key),
    )

    def _fake_post(url, **kwargs):
        request_state["url"] = url
        return _FakeResponse(
            lines=[
                'data: {"event":"message","content":"ok"}',
                'data: {"event":"done"}',
            ]
        )

    monkeypatch.setattr(coze_adapter.requests, "post", _fake_post)

    chunks = list(
        adapter.stream_answer(
            app=app,
            user_id="user-1",
            user_query="hello",
            messages=[],
            provider_config={
                "config": {
                    "api_key": "test-key",
                    "bot_id": "bot-1",
                }
            },
        )
    )

    assert request_state["url"] == "https://api.coze.cn/v3/chat"
    assert [chunk.content for chunk in chunks] == ["ok"]


def test_volc_knowledge_adapter_streams_success_content(app, monkeypatch):
    adapter = module.VolcKnowledgeAskProviderAdapter()

    monkeypatch.setattr(
        common,
        "get_config",
        lambda key: {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get(key),
    )

    request_state = {}

    def _fake_request(*_args, **kwargs):
        request_state["method"] = kwargs.get("method")
        request_state["headers"] = kwargs.get("headers") or {}
        request_state["url"] = kwargs.get("url")
        return _FakeResponse(
            json_data={
                "code": 0,
                "data": {
                    "records": [
                        {"content": "volc-answer-1"},
                        {"text": "volc-answer-2"},
                    ]
                },
            }
        )

    monkeypatch.setattr(
        volc_knowledge_adapter.requests,
        "request",
        _fake_request,
    )

    chunks = list(
        adapter.stream_answer(
            app=app,
            user_id="user-1",
            user_query="hello",
            messages=[],
            provider_config={
                "config": {
                    "account_id": "acc-1",
                    "ak": "ak-1",
                    "sk": "sk-1",
                    "collection_name": "collection-1",
                }
            },
        )
    )

    assert [chunk.content for chunk in chunks] == ["volc-answer-1", "volc-answer-2"]
    assert request_state["method"] == "POST"
    assert request_state["url"].endswith("/api/knowledge/collection/search_knowledge")
    assert request_state["headers"]["Authorization"].startswith(
        "HMAC-SHA256 Credential=ak-1/"
    )
    assert request_state["headers"]["X-Date"]
    assert request_state["headers"]["X-Content-Sha256"]


def test_volc_knowledge_adapter_missing_config_raises_error(app):
    adapter = module.VolcKnowledgeAskProviderAdapter()

    with pytest.raises(module.AskProviderConfigError, match="account_id/ak/sk"):
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "account_id": "acc-1",
                        "collection_name": "collection-1",
                    }
                },
            )
        )


def test_llm_adapter_streams_from_runtime_factory(app):
    adapter = module.LlmAskProviderAdapter()

    runtime = module.AskProviderRuntime(
        llm_stream_factory=lambda: iter(
            [
                types.SimpleNamespace(result="hello"),
                types.SimpleNamespace(result=" world"),
                types.SimpleNamespace(result=""),
                types.SimpleNamespace(result=None),
            ]
        )
    )

    chunks = list(
        adapter.stream_answer(
            app=app,
            user_id="user-1",
            user_query="hello",
            messages=[],
            provider_config={"config": {}},
            runtime=runtime,
        )
    )

    assert [chunk.content for chunk in chunks] == ["hello", " world"]


def test_llm_adapter_missing_runtime_raises_config_error(app):
    adapter = module.LlmAskProviderAdapter()

    with pytest.raises(module.AskProviderConfigError, match="llm runtime"):
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={"config": {}},
            )
        )


def test_stream_ask_provider_response_uses_llm_adapter_runtime(app):
    runtime = module.AskProviderRuntime(
        llm_stream_factory=lambda: iter([types.SimpleNamespace(result="from-llm")])
    )

    chunks = list(
        module.stream_ask_provider_response(
            app=app,
            provider="llm",
            user_id="user-1",
            user_query="hello",
            messages=[],
            provider_config={"config": {}},
            runtime=runtime,
        )
    )

    assert [chunk.content for chunk in chunks] == ["from-llm"]

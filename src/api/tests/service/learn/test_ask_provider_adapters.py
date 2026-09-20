"""Verify ask provider adapter behavior."""

import json
import types
from typing import Self

import pytest
import requests
from flaskr.service.learn import ask_provider_adapters as module
from flaskr.service.learn.ask_provider_adapters import (
    common,
    coze_adapter,
    dify_adapter,
    get_biji_knowledge_adapter,
)


class _FakeResponse:
    def __init__(
        self,
        lines: object = None,
        status_code: object = 200,
        text: object = "",
        http_error: object = None,
        json_data: object = None,
        json_error: object = None,
    ) -> None:
        self._lines = lines or []
        self.status_code = status_code
        self.text = text
        self._http_error = http_error
        self._json_data = json_data
        self._json_error = json_error

    @property
    def status(self) -> object:
        return self.status_code

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None

    def iter_lines(self, decode_unicode: object = True) -> object:
        _ = decode_unicode
        yield from self._lines

    def raise_for_status(self) -> None:
        if self._http_error is not None:
            raise self._http_error

    def json(self) -> object:
        if self._json_error is not None:
            raise self._json_error
        return self._json_data

    @property
    def content(self) -> bytes:
        return json.dumps(self._json_data).encode("utf-8")


@pytest.fixture
def dify_app(app: object, monkeypatch: object) -> object:
    """Isolate Dify policy configuration from the shared Flask test app."""
    monkeypatch.setitem(app.config, "DIFY_TRUSTED_ORIGINS", "")
    return app


def test_dify_adapter_streams_success_content(
    dify_app: object,
    monkeypatch: object,
) -> None:
    adapter = module.DifyAskProviderAdapter()
    request_state = {}

    monkeypatch.setattr(
        common,
        "get_config",
        {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get,
    )

    def _fake_request(
        _self: object,
        method: object,
        url: object,
        **kwargs: object,
    ) -> object:
        request_state["method"] = method
        request_state["url"] = url
        request_state["headers"] = kwargs.get("headers")
        request_state["json"] = json.loads(kwargs.get("body", b"{}"))
        request_state["policy"] = _self.policy
        return _FakeResponse(
            lines=[
                'data: {"event":"message","answer":"hello"}',
                'data: {"event":"message","answer":" world"}',
                "data: [DONE]",
            ]
        )

    monkeypatch.setattr(
        dify_adapter.SafeOutboundClient,
        "request",
        _fake_request,
    )

    chunks = list(
        adapter.stream_answer(
            app=dify_app,
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
    assert request_state["method"] == "POST"
    assert request_state["url"] == "https://dify.example.com/chat-messages"
    assert request_state["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
    assert request_state["policy"].trusted_origins == frozenset()
    assert request_state["json"]["query"] == (
        "[system]\ncourse prompt\n\n"
        "[user]\nprevious question\n\n"
        "[assistant]\nprevious answer\n\n"
        "[user]\nhello"
    )


def test_dify_adapter_maps_request_deadline_to_provider_timeout(
    dify_app: object,
    monkeypatch: object,
) -> None:
    adapter = module.DifyAskProviderAdapter()

    def _raise_deadline(*_args: object, **_kwargs: object) -> object:
        message = "outbound request exceeded its total timeout"
        raise dify_adapter.OutboundDeadlineExceededError(message)

    monkeypatch.setattr(dify_adapter.SafeOutboundClient, "request", _raise_deadline)

    with pytest.raises(module.AskProviderTimeoutError, match="dify request timeout"):
        list(
            adapter.stream_answer(
                app=dify_app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "base_url": "https://dify.example.com",
                        "api_key": "test-key",
                    }
                },
            )
        )


def test_dify_adapter_maps_stream_deadline_to_provider_timeout(
    dify_app: object,
    monkeypatch: object,
) -> None:
    adapter = module.DifyAskProviderAdapter()

    class _DeadlineResponse(_FakeResponse):
        def iter_lines(self, decode_unicode: object = True) -> object:
            _ = decode_unicode
            message = "outbound request exceeded its total timeout"
            raise dify_adapter.OutboundDeadlineExceededError(message)
            yield

    monkeypatch.setattr(
        dify_adapter.SafeOutboundClient,
        "request",
        lambda *_args, **_kwargs: _DeadlineResponse(),
    )

    with pytest.raises(module.AskProviderTimeoutError, match="dify request timeout"):
        list(
            adapter.stream_answer(
                app=dify_app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "base_url": "https://dify.example.com",
                        "api_key": "test-key",
                    }
                },
            )
        )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1:80/v1",
        "http://[::1]:80/v1",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_dify_adapter_rejects_internal_destinations(
    dify_app: object,
    base_url: str,
) -> None:
    adapter = module.DifyAskProviderAdapter()

    with pytest.raises(
        module.AskProviderError,
        match="dify request was rejected or failed",
    ):
        list(
            adapter.stream_answer(
                app=dify_app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "base_url": base_url,
                        "api_key": "test-key",
                    }
                },
            )
        )


def test_dify_adapter_applies_deployment_trusted_origins(
    dify_app: object,
    monkeypatch: object,
) -> None:
    adapter = module.DifyAskProviderAdapter()
    captured = {}
    monkeypatch.setitem(
        dify_app.config,
        "DIFY_TRUSTED_ORIGINS",
        "http://dify.internal:5001",
    )

    def _fake_request(
        client: object,
        *_args: object,
        **_kwargs: object,
    ) -> object:
        captured["policy"] = client.policy
        return _FakeResponse(lines=["data: [DONE]"])

    monkeypatch.setattr(dify_adapter.SafeOutboundClient, "request", _fake_request)

    assert (
        list(
            adapter.stream_answer(
                app=dify_app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "base_url": "http://dify.internal:5001/v1",
                        "api_key": "test-key",
                    }
                },
            )
        )
        == []
    )
    assert captured["policy"].trusted_origins == frozenset(
        {"http://dify.internal:5001"}
    )


def test_dify_adapter_rejects_invalid_deployment_trusted_origin(
    dify_app: object,
    monkeypatch: object,
) -> None:
    adapter = module.DifyAskProviderAdapter()
    monkeypatch.setitem(
        dify_app.config,
        "DIFY_TRUSTED_ORIGINS",
        "http://user:secret@dify.internal:5001",
    )

    with pytest.raises(
        module.AskProviderConfigError,
        match="DIFY_TRUSTED_ORIGINS contains an invalid origin",
    ):
        list(
            adapter.stream_answer(
                app=dify_app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "base_url": "https://dify.example.com/v1",
                        "api_key": "test-key",
                    }
                },
            )
        )


def test_coze_adapter_timeout_raises_timeout_error(
    app: object, monkeypatch: object
) -> None:
    adapter = module.CozeAskProviderAdapter()

    monkeypatch.setattr(
        common,
        "get_config",
        {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get,
    )

    def _raise_timeout(*_args: object, **_kwargs: object) -> None:
        message = "timeout"
        raise coze_adapter.OutboundDeadlineExceededError(message)

    monkeypatch.setattr(common.SafeOutboundClient, "request", _raise_timeout)

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


def test_stream_ask_provider_response_raises_error_for_unsupported_provider(
    app: object,
) -> None:
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


def test_coze_adapter_http_error_raises_provider_error(
    app: object, monkeypatch: object
) -> None:
    adapter = module.CozeAskProviderAdapter()

    monkeypatch.setattr(
        common,
        "get_config",
        {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get,
    )

    monkeypatch.setattr(
        common.SafeOutboundClient,
        "request",
        lambda *_args, **_kwargs: _FakeResponse(status_code=400),
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


def test_coze_workflow_adapter_streams_success_content(
    app: object, monkeypatch: object
) -> None:
    adapter = module.CozeWorkflowAskProviderAdapter()
    request_state = {}

    monkeypatch.setattr(
        common,
        "get_config",
        {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get,
    )

    def _fake_request(
        _self: object, method: object, url: object, **kwargs: object
    ) -> object:
        request_state["method"] = method
        request_state["url"] = url
        request_state["json"] = json.loads(kwargs.get("body", b"{}"))
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
        common.SafeOutboundClient,
        "request",
        _fake_request,
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


def test_coze_workflow_adapter_nonzero_code_raises_provider_error(
    app: object, monkeypatch: object
) -> None:
    adapter = module.CozeWorkflowAskProviderAdapter()

    monkeypatch.setattr(
        common,
        "get_config",
        {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get,
    )

    monkeypatch.setattr(
        common.SafeOutboundClient,
        "request",
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


def test_dify_adapter_missing_shifu_config_raises_config_error(app: object) -> None:
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


def test_coze_adapter_missing_shifu_config_raises_config_error(app: object) -> None:
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


def test_coze_workflow_adapter_missing_shifu_config_raises_config_error(
    app: object,
) -> None:
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


def test_coze_adapter_uses_default_base_url_when_missing(
    app: object, monkeypatch: object
) -> None:
    adapter = module.CozeAskProviderAdapter()
    request_state = {}

    monkeypatch.setattr(
        common,
        "get_config",
        {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get,
    )

    def _fake_request(
        _self: object, method: object, url: object, **kwargs: object
    ) -> object:
        request_state["method"] = method
        request_state["url"] = url
        request_state["json"] = json.loads(kwargs["body"])
        return _FakeResponse(
            lines=[
                'data: {"event":"message","content":"ok"}',
                'data: {"event":"done"}',
            ]
        )

    monkeypatch.setattr(common.SafeOutboundClient, "request", _fake_request)

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
    assert request_state["json"]["bot_id"] == "bot-1"
    assert [chunk.content for chunk in chunks] == ["ok"]


def test_volc_knowledge_adapter_streams_success_content(
    app: object, monkeypatch: object
) -> None:
    adapter = module.VolcKnowledgeAskProviderAdapter()

    monkeypatch.setattr(
        common,
        "get_config",
        {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get,
    )

    request_state = {}

    monkeypatch.setattr(common.SafeOutboundClient, "new_deadline", lambda _self: 123.0)

    def _fake_validate_url(_self: object, _url: object, **kwargs: object) -> object:
        request_state["validation_deadline"] = kwargs.get("deadline")
        return types.SimpleNamespace(
            url="https://api-knowledgebase.mlp.cn-beijing.volces.com/api/knowledge/collection/search_knowledge"
        )

    monkeypatch.setattr(common.SafeOutboundClient, "validate_url", _fake_validate_url)

    def _fake_request(
        _self: object, method: object, url: object, **kwargs: object
    ) -> object:
        request_state["method"] = method
        request_state["headers"] = kwargs.get("headers") or {}
        request_state["url"] = url
        request_state["request_deadline"] = kwargs.get("deadline")
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
        common.SafeOutboundClient,
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
    assert request_state["validation_deadline"] == 123.0
    assert request_state["request_deadline"] == 123.0


@pytest.mark.parametrize(
    ("domain", "normalized_url", "expected_host"),
    [
        (
            "api-knowledgebase.mlp.cn-beijing.volces.com:443",
            "https://api-knowledgebase.mlp.cn-beijing.volces.com/api/knowledge/collection/search_knowledge",
            "api-knowledgebase.mlp.cn-beijing.volces.com",
        ),
        (
            "api-knowledgebase.mlp.cn-beijing.volces.com.",
            "https://api-knowledgebase.mlp.cn-beijing.volces.com/api/knowledge/collection/search_knowledge",
            "api-knowledgebase.mlp.cn-beijing.volces.com",
        ),
    ],
)
def test_volc_signature_uses_the_normalized_transport_host(
    app: object,
    monkeypatch: object,
    domain: str,
    normalized_url: str,
    expected_host: str,
) -> None:
    adapter = module.VolcKnowledgeAskProviderAdapter()
    request_state = {}

    monkeypatch.setattr(
        common.SafeOutboundClient,
        "validate_url",
        lambda *_args, **_kwargs: types.SimpleNamespace(url=normalized_url),
    )

    def _fake_request(
        _self: object, method: object, url: object, **kwargs: object
    ) -> object:
        request_state["method"] = method
        request_state["url"] = url
        request_state["headers"] = kwargs.get("headers") or {}
        return _FakeResponse(json_data={"code": 0, "data": {"text": "ok"}})

    monkeypatch.setattr(common.SafeOutboundClient, "request", _fake_request)

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
                    "domain": domain,
                }
            },
        )
    )

    assert [chunk.content for chunk in chunks] == ["ok"]
    assert request_state["url"] == normalized_url
    assert request_state["headers"]["Host"] == expected_host


def test_safe_provider_client_uses_separate_read_and_total_timeouts(
    app: object,
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(
        common,
        "get_config",
        {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
            "ASK_PROVIDER_TOTAL_TIMEOUT_SECONDS": 90,
        }.get,
    )

    client = common.safe_provider_client(
        app,
        trusted_origins_config="COZE_TRUSTED_ORIGINS",
    )

    assert client.policy.read_timeout_seconds == 20
    assert client.policy.total_timeout_seconds == 90


def test_safe_provider_client_requires_https_by_default(app: object) -> None:
    client = common.safe_provider_client(
        app,
        trusted_origins_config="COZE_TRUSTED_ORIGINS",
    )

    assert client.policy.allowed_schemes == frozenset({"https"})


def test_safe_provider_client_allows_explicit_private_http_opt_in(
    app: object, monkeypatch: object
) -> None:
    allow_insecure_http = True
    monkeypatch.setitem(
        app.config, "ASK_PROVIDER_ALLOW_INSECURE_HTTP", allow_insecure_http
    )

    client = common.safe_provider_client(
        app,
        trusted_origins_config="COZE_TRUSTED_ORIGINS",
    )

    assert client.policy.allowed_schemes == frozenset({"http", "https"})


def test_volc_knowledge_adapter_missing_config_raises_error(app: object) -> None:
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


@pytest.mark.parametrize(
    ("adapter", "provider_config", "error_message"),
    [
        (
            module.CozeAskProviderAdapter(),
            {
                "config": {
                    "api_key": "coze-secret",
                    "bot_id": "bot-1",
                    "base_url": "http://127.0.0.1",
                }
            },
            "coze request was rejected or failed",
        ),
        (
            module.CozeWorkflowAskProviderAdapter(),
            {
                "config": {
                    "api_key": "coze-secret",
                    "workflow_id": "workflow-1",
                    "base_url": "http://169.254.169.254",
                }
            },
            "coze_workflow request was rejected or failed",
        ),
        (
            module.VolcKnowledgeAskProviderAdapter(),
            {
                "config": {
                    "account_id": "acc-1",
                    "ak": "ak-1",
                    "sk": "sk-1",
                    "collection_name": "collection-1",
                    "domain": "[::1]",
                    "scheme": "http",
                }
            },
            "volc_knowledge request was rejected or failed",
        ),
    ],
)
def test_configurable_ask_providers_reject_internal_destinations(
    app: object,
    adapter: object,
    provider_config: dict[str, object],
    error_message: str,
) -> None:
    with pytest.raises(module.AskProviderError, match=error_message):
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config=provider_config,
            )
        )


def test_coze_absolute_api_path_is_still_checked_by_safe_outbound(
    app: object,
) -> None:
    adapter = module.CozeAskProviderAdapter()

    with pytest.raises(
        module.AskProviderError,
        match="coze request was rejected or failed",
    ):
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "api_key": "coze-secret",
                        "api_path": "http://127.0.0.1/private",
                    }
                },
            )
        )


def test_get_biji_knowledge_adapter_synthesizes_with_llm_context(
    app: object, monkeypatch: object
) -> None:
    adapter = module.GetBijiKnowledgeAskProviderAdapter()

    monkeypatch.setattr(
        common,
        "get_config",
        {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get,
    )

    request_state = {}

    def _fake_post(url: object, **kwargs: object) -> object:
        request_state["url"] = url
        request_state["headers"] = kwargs.get("headers") or {}
        request_state["json"] = kwargs.get("json")
        request_state["timeout"] = kwargs.get("timeout")
        return _FakeResponse(
            json_data={
                "success": True,
                "data": {
                    "results": [
                        {
                            "note_id": "note-1",
                            "note_type": "NOTE",
                            "title": "First note",
                            "content": "First content",
                            "created_at": "2026-02-25 10:00:00",
                        },
                        {
                            "note_id": "note-2",
                            "note_type": "NOTE",
                            "title": "Second note",
                            "content": "Second content",
                        },
                    ]
                },
            }
        )

    monkeypatch.setattr(
        get_biji_knowledge_adapter.requests,
        "post",
        _fake_post,
    )

    captured_context = {}

    def _context_stream_factory(knowledge_context: object) -> object:
        captured_context["value"] = knowledge_context
        return iter(
            [
                types.SimpleNamespace(result="synthesized"),
                types.SimpleNamespace(result=" answer"),
                types.SimpleNamespace(result=None),
            ]
        )

    runtime = module.AskProviderRuntime(
        llm_context_stream_factory=_context_stream_factory,
    )

    chunks = list(
        adapter.stream_answer(
            app=app,
            user_id="user-1",
            user_query="hello",
            messages=[],
            provider_config={
                "config": {
                    "api_key": "gk-live-1",
                    "client_id": "cli-1",
                    "topic_id": "topic-1",
                    "top_k": 50,
                }
            },
            runtime=runtime,
        )
    )

    assert request_state["url"] == (
        "https://openapi.biji.com/open/api/v1/resource/recall/knowledge"
    )
    assert request_state["headers"] == {
        "Authorization": "gk-live-1",
        "X-Client-ID": "cli-1",
        "Content-Type": "application/json",
    }
    assert request_state["json"] == {
        "topic_id": "topic-1",
        "query": "hello",
        "top_k": 10,
    }
    assert request_state["timeout"] == (5, 20)
    assert captured_context["value"] == (
        "1. **First note**\nFirst content\n(2026-02-25 10:00:00)"
        "\n\n2. **Second note**\nSecond content"
    )
    assert [chunk.content for chunk in chunks] == ["synthesized", " answer"]


def test_get_biji_knowledge_adapter_skips_results_without_title_or_content(
    app: object, monkeypatch: object
) -> None:
    adapter = module.GetBijiKnowledgeAskProviderAdapter()

    monkeypatch.setattr(
        get_biji_knowledge_adapter.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            json_data={
                "success": True,
                "data": {
                    "results": [
                        {},
                        {"created_at": "2026-02-25 10:00:00"},
                        {
                            "note_id": "note-1",
                            "title": "Useful note",
                            "content": "Useful content",
                        },
                    ]
                },
            }
        ),
    )

    captured_context = {}

    def _context_stream_factory(knowledge_context: object) -> object:
        captured_context["value"] = knowledge_context
        return iter([types.SimpleNamespace(result="answer")])

    runtime = module.AskProviderRuntime(
        llm_context_stream_factory=_context_stream_factory,
    )

    chunks = list(
        adapter.stream_answer(
            app=app,
            user_id="user-1",
            user_query="hello",
            messages=[],
            provider_config={
                "config": {
                    "api_key": "gk-live-1",
                    "client_id": "cli-1",
                    "topic_id": "topic-1",
                }
            },
            runtime=runtime,
        )
    )

    assert captured_context["value"] == "3. **Useful note**\nUseful content"
    assert [chunk.content for chunk in chunks] == ["answer"]


def test_get_biji_knowledge_adapter_empty_results_synthesizes_with_empty_context(
    app: object, monkeypatch: object
) -> None:
    adapter = module.GetBijiKnowledgeAskProviderAdapter()

    monkeypatch.setattr(
        get_biji_knowledge_adapter.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            json_data={"success": True, "data": {"results": []}}
        ),
    )

    captured_context = {}

    def _context_stream_factory(knowledge_context: object) -> object:
        captured_context["value"] = knowledge_context
        return iter([types.SimpleNamespace(result="fallback answer")])

    runtime = module.AskProviderRuntime(
        llm_context_stream_factory=_context_stream_factory,
    )

    chunks = list(
        adapter.stream_answer(
            app=app,
            user_id="user-1",
            user_query="hello",
            messages=[],
            provider_config={
                "config": {
                    "api_key": "gk-live-1",
                    "client_id": "cli-1",
                    "topic_id": "topic-1",
                }
            },
            runtime=runtime,
        )
    )

    assert captured_context["value"] == ""
    assert [chunk.content for chunk in chunks] == ["fallback answer"]


def test_get_biji_knowledge_adapter_without_runtime_emits_snippets(
    app: object, monkeypatch: object
) -> None:
    adapter = module.GetBijiKnowledgeAskProviderAdapter()

    monkeypatch.setattr(
        common,
        "get_config",
        {
            "ASK_PROVIDER_TIMEOUT_SECONDS": 20,
        }.get,
    )
    monkeypatch.setattr(
        get_biji_knowledge_adapter.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            json_data={
                "success": True,
                "data": {
                    "results": [
                        {
                            "note_id": "note-1",
                            "title": "First note",
                            "content": "First content",
                        }
                    ]
                },
            }
        ),
    )

    chunks = list(
        adapter.stream_answer(
            app=app,
            user_id="user-1",
            user_query="hello",
            messages=[],
            provider_config={
                "config": {
                    "api_key": "gk-live-1",
                    "client_id": "cli-1",
                    "topic_id": "topic-1",
                }
            },
        )
    )

    assert [chunk.content for chunk in chunks] == [
        "1. **First note**\nFirst content\n\n",
    ]


def test_get_biji_knowledge_adapter_missing_config_raises_error(app: object) -> None:
    adapter = module.GetBijiKnowledgeAskProviderAdapter()

    with pytest.raises(
        module.AskProviderConfigError, match="api_key/client_id/topic_id"
    ):
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "api_key": "gk-live-1",
                        "topic_id": "topic-1",
                    }
                },
            )
        )


def test_get_biji_knowledge_adapter_timeout_raises_timeout_error(
    app: object, monkeypatch: object
) -> None:
    adapter = module.GetBijiKnowledgeAskProviderAdapter()

    def _raise_timeout(*_args: object, **_kwargs: object) -> None:
        message = "timeout"
        raise requests.Timeout(message)

    monkeypatch.setattr(get_biji_knowledge_adapter.requests, "post", _raise_timeout)

    with pytest.raises(module.AskProviderTimeoutError):
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "api_key": "gk-live-1",
                        "client_id": "cli-1",
                        "topic_id": "topic-1",
                    }
                },
            )
        )


def test_get_biji_knowledge_adapter_http_error_raises_provider_error(
    app: object, monkeypatch: object
) -> None:
    adapter = module.GetBijiKnowledgeAskProviderAdapter()
    http_error = requests.HTTPError("bad request")

    monkeypatch.setattr(
        get_biji_knowledge_adapter.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            text="get biji bad request",
            status_code=400,
            http_error=http_error,
        ),
    )

    with pytest.raises(
        module.AskProviderError, match="get_biji_knowledge request failed"
    ):
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "api_key": "gk-live-1",
                        "client_id": "cli-1",
                        "topic_id": "topic-1",
                    }
                },
            )
        )


def test_get_biji_knowledge_adapter_api_error_includes_message_and_reason(
    app: object, monkeypatch: object
) -> None:
    adapter = module.GetBijiKnowledgeAskProviderAdapter()

    monkeypatch.setattr(
        get_biji_knowledge_adapter.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            json_data={
                "success": False,
                "data": None,
                "error": {
                    "code": 10201,
                    "message": "OpenAPI members only",
                    "reason": "not_member",
                },
            }
        ),
    )

    with pytest.raises(
        module.AskProviderError,
        match=r"OpenAPI members only \(reason: not_member\)",
    ) as exc_info:
        list(
            adapter.stream_answer(
                app=app,
                user_id="user-1",
                user_query="hello",
                messages=[],
                provider_config={
                    "config": {
                        "api_key": "gk-live-1",
                        "client_id": "cli-1",
                        "topic_id": "topic-1",
                    }
                },
            )
        )

    assert "membership" in (exc_info.value.user_message or "")


def test_get_biji_knowledge_adapter_maps_business_errors_to_user_messages(
    app: object, monkeypatch: object
) -> None:
    adapter = module.GetBijiKnowledgeAskProviderAdapter()
    cases = [
        # Auth failures arrive as HTTP 401 with a business error body.
        ({"code": 10004, "message": "unauthorized"}, 401, "API Key"),
        ({"code": 10001, "message": "auth failed"}, 401, "API Key"),
        (
            {"code": 10203, "message": "quota", "reason": "quota_daily_exceeded"},
            429,
            "quota",
        ),
        ({"code": 30000, "message": "internal"}, 500, None),
    ]

    for error_body, status_code, expected_fragment in cases:
        monkeypatch.setattr(
            get_biji_knowledge_adapter.requests,
            "post",
            lambda *_args, status_code=status_code, error_body=error_body, **_kwargs: (
                _FakeResponse(
                    status_code=status_code,
                    json_data={"success": False, "data": None, "error": error_body},
                )
            ),
        )

        with pytest.raises(module.AskProviderError) as exc_info:
            list(
                adapter.stream_answer(
                    app=app,
                    user_id="user-1",
                    user_query="hello",
                    messages=[],
                    provider_config={
                        "config": {
                            "api_key": "gk-live-1",
                            "client_id": "cli-1",
                            "topic_id": "topic-1",
                        }
                    },
                )
            )

        user_message = exc_info.value.user_message
        if expected_fragment is None:
            assert user_message is None, f"error {error_body} should have no mapping"
        else:
            assert expected_fragment in (user_message or ""), (
                f"error {error_body} should map to a message containing {expected_fragment}"
            )


def test_render_knowledge_rule_and_section() -> None:
    rule = common.render_knowledge_rule()
    section = common.render_knowledge_section("retrieved material", include_rule=False)
    section_with_rule = common.render_knowledge_section(
        "retrieved material", include_rule=True
    )

    assert rule.startswith("-")
    assert "<knowledge>\n\nretrieved material\n\n</knowledge>" in section
    assert rule not in section
    assert rule in section_with_rule
    assert "{knowledge}" not in section
    assert "{knowledge_rule}" not in section


def test_apply_knowledge_context_fills_rule_and_section_placeholders() -> None:
    prompt = (
        "# rules\n- learned rule\n{knowledge_rule}\n- unlearned rule\n\n"
        "{knowledge_section}\n\n# settings"
    )

    filled = common.apply_knowledge_context(prompt, "retrieved material")

    assert "{knowledge_rule}" not in filled
    assert "{knowledge_section}" not in filled
    # The rule lands in the rules list, between learned and unlearned rules.
    rule = common.render_knowledge_rule()
    assert f"- learned rule\n{rule}\n- unlearned rule" in filled
    assert "<knowledge>\n\nretrieved material\n\n</knowledge>" in filled
    # The rule appears exactly once (not duplicated inside the section).
    assert filled.count(rule) == 1


def test_apply_knowledge_context_removes_rule_and_section_without_knowledge() -> None:
    prompt = (
        "# rules\n- learned rule\n{knowledge_rule}\n- unlearned rule\n\n"
        "{knowledge_section}\n\n# settings"
    )

    filled = common.apply_knowledge_context(prompt, "")

    # Both the rule line and the section disappear without leftover gaps.
    assert filled == "# rules\n- learned rule\n- unlearned rule\n\n# settings"


def test_apply_knowledge_context_appends_section_for_legacy_prompts() -> None:
    prompt = "legacy prompt without placeholder"

    filled = common.apply_knowledge_context(prompt, "retrieved material")

    assert filled.startswith(prompt)
    # Legacy prompts cannot host the rule in a rules list, so it travels
    # with the appended section.
    assert filled == (
        prompt
        + "\n\n"
        + common.render_knowledge_section("retrieved material", include_rule=True)
    )
    assert common.render_knowledge_rule() in filled


def test_apply_knowledge_context_keeps_legacy_prompt_without_knowledge() -> None:
    prompt = "legacy prompt without placeholder"

    assert common.apply_knowledge_context(prompt, "") == prompt


def test_apply_knowledge_to_messages_updates_first_system_message() -> None:
    messages = [
        {"role": "system", "content": "rules {knowledge_section} end"},
        {"role": "user", "content": "question"},
    ]

    updated = common.apply_knowledge_to_messages(messages, "retrieved material")

    assert "{knowledge_section}" not in updated[0]["content"]
    assert "retrieved material" in updated[0]["content"]
    assert updated[1] == {"role": "user", "content": "question"}
    # The original messages are untouched.
    assert messages[0]["content"] == "rules {knowledge_section} end"


def test_apply_knowledge_to_messages_prepends_system_when_missing() -> None:
    messages = [{"role": "user", "content": "question"}]

    updated = common.apply_knowledge_to_messages(messages, "retrieved material")

    assert updated[0]["role"] == "system"
    assert "retrieved material" in updated[0]["content"]
    assert updated[-1] == {"role": "user", "content": "question"}

    unchanged = common.apply_knowledge_to_messages(messages, "")
    assert unchanged == messages


def test_llm_adapter_streams_from_runtime_factory(app: object) -> None:
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


def test_llm_adapter_missing_runtime_raises_config_error(app: object) -> None:
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


def test_stream_ask_provider_response_uses_llm_adapter_runtime(app: object) -> None:
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

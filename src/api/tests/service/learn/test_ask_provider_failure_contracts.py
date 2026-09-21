"""Keep provider errors and heterogeneous retrieval output behind one contract."""

import copy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, PropertyMock

import pytest
import requests
from flask import Flask
from flaskr.common.safe_outbound import OutboundDeadlineExceededError
from flaskr.service.learn.ask_provider_adapters import (
    common,
    dify_adapter,
    registry,
)
from flaskr.service.learn.ask_provider_adapters import (
    coze_workflow_adapter as workflow,
)
from flaskr.service.learn.ask_provider_adapters import (
    get_biji_knowledge_adapter as biji,
)
from flaskr.service.learn.ask_provider_adapters import (
    volc_knowledge_adapter as volc,
)
from flaskr.service.learn.ask_provider_adapters.base import (
    AskProviderConfigError,
    AskProviderError,
    AskProviderRuntime,
    AskProviderTimeoutError,
)
from urllib3.exceptions import NewConnectionError

PROVIDERS = ["dify", "coze", "coze_workflow", "get_biji_knowledge", "volc_knowledge"]
CONFIG = {
    "base_url": "https://example.test/api/",
    "api_key": "test-key",
    "bot_id": "bot",
    "workflow_id": "workflow",
    "client_id": "client",
    "topic_id": "topic",
    "account_id": "account",
    "ak": "test-ak",
    "sk": "test-sk",
    "collection_name": "collection",
}


@pytest.fixture(autouse=True)
def timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(common, "get_config", lambda _key: 7)
    monkeypatch.setattr(
        common.SafeOutboundClient,
        "validate_url",
        lambda _self, url, **_kw: SimpleNamespace(url=url),
    )


def _stub_request(
    monkeypatch: pytest.MonkeyPatch,
    response: object = None,
    *,
    error: Exception | None = None,
) -> Mock:
    request = Mock(return_value=response, side_effect=error)
    if response is not None:
        response.__enter__.return_value = response
        if response.json.side_effect is not None:
            response.content = b"invalid-json"
        else:
            payload = response.json.return_value
            response.content = json.dumps(
                payload
                if isinstance(payload, (dict, list, str, int, float, bool))
                else None
            ).encode()
    monkeypatch.setattr(requests, "post", request)

    def send(client: object, *args: object, **kwargs: object) -> object:
        request.policy = client.policy
        return request(*args, **kwargs)

    monkeypatch.setattr(common.SafeOutboundClient, "request", send)
    return request


def _run(provider: str, config: object = CONFIG, **kwargs: object) -> list:
    return list(
        registry.stream_ask_provider_response(
            Flask("provider-contract"),
            provider,
            "user",
            "question",
            kwargs.pop("messages", []),
            {"config": config},
            **kwargs,
        )
    )


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("failure", ["timeout", "connection"])
def test_network_failures_become_provider_errors_with_original_cause(
    provider: str, failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if provider == "get_biji_knowledge":
        error = (
            requests.Timeout("slow")
            if failure == "timeout"
            else requests.ConnectionError("offline")
        )
    else:
        error = (
            OutboundDeadlineExceededError("slow")
            if failure == "timeout"
            else NewConnectionError(None, "offline")
        )
    expected = AskProviderTimeoutError if failure == "timeout" else AskProviderError
    request = _stub_request(monkeypatch, error=error)
    with pytest.raises(expected) as raised:
        _run(provider)
    assert raised.value.__cause__ is error
    if provider == "get_biji_knowledge":
        assert request.call_args.kwargs["timeout"] == (5, 7)
    else:
        assert request.policy.connect_timeout_seconds == 5
        assert request.policy.read_timeout_seconds == 7


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("config", [None, [], "invalid", {}])
def test_invalid_configuration_is_rejected_before_network(
    provider: str, config: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _stub_request(monkeypatch, error=AssertionError("network must not run"))
    with pytest.raises(AskProviderConfigError):
        _run(provider, config)
    request.assert_not_called()


@pytest.mark.parametrize(
    "provider", ["coze_workflow", "get_biji_knowledge", "volc_knowledge"]
)
def test_non_json_retrieval_response_raises_domain_error(
    provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = MagicMock(status=200)
    response.json.side_effect = ValueError("not JSON")
    _stub_request(monkeypatch, response)
    with pytest.raises(AskProviderError, match="not valid json"):
        _run(provider)


@pytest.mark.parametrize("provider", ["dify", "coze"])
def test_sse_ignores_malformed_frames_and_propagates_provider_error(
    provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = MagicMock(status=200)
    response.iter_lines.return_value = iter(
        [
            "",
            " data: ",
            "data: [ DONE ]",
            "data: invalid-json",
            'data: {"event":"message","answer":"partial"}',
            'data: {"event":"error","message":"rate limited"}',
        ]
    )
    _stub_request(monkeypatch, response)
    stream = registry.stream_ask_provider_response(
        Flask("sse-provider"), provider, "user", "question", [], {"config": CONFIG}
    )
    assert next(stream).content == "partial"
    with pytest.raises(AskProviderError, match="rate limited"):
        next(stream)


def test_coze_custom_endpoint_and_extra_body_preserve_request_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock(status=200)
    response.iter_lines.return_value = iter(
        [
            'data: {"event":"chat.completed","text":"do not emit"}',
            'data: {"content":"answer"}',
        ]
    )
    request = _stub_request(monkeypatch, response)
    result = _run(
        "coze",
        {
            "api_key": "token",
            "api_path": "https://example.test/custom",
            "conversation_id": " conversation ",
            "extra_body": {"temperature": 0},
        },
    )
    assert [item.content for item in result] == ["answer"]
    assert request.call_args.args == ("POST", "https://example.test/custom")
    assert json.loads(request.call_args.kwargs["body"]) == {
        "stream": True,
        "user_id": "user",
        "additional_messages": [
            {"role": "user", "content": "question", "content_type": "text"}
        ],
        "conversation_id": "conversation",
        "temperature": 0,
    }
    with pytest.raises(AskProviderConfigError, match="bot_id"):
        _run("coze", {"api_key": "token"})


def test_dify_query_uses_only_supported_nonblank_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock(status=200)
    response.iter_lines.return_value = iter([])
    request = _stub_request(monkeypatch, response)
    _run(
        "dify",
        {**CONFIG, "conversation_id": "chat", "inputs": {"course": "course"}},
        messages=[
            None,
            {"role": "tool", "content": "secret"},
            {"role": "user", "content": " "},
            {"role": " ASSISTANT ", "content": " Previous answer "},
        ],
    )
    payload = json.loads(request.call_args.kwargs["body"])
    assert payload["query"] == "[assistant]\nPrevious answer"
    assert payload["conversation_id"] == "chat"
    assert payload["inputs"] == {"course": "course"}
    assert (
        dify_adapter._build_dify_query(
            "question", [{"role": "unknown", "content": "text"}]
        )
        == "question"
    )


@pytest.mark.parametrize(
    ("raw", "expected"), [(None, 20), ("bad", 20), (0, 1), (-2, 1), ("12", 12)]
)
def test_provider_timeout_never_becomes_nonpositive(
    raw: object, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(common, "get_config", lambda _key: raw)
    assert common.provider_timeout_seconds() == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ([None, {"answer": "found"}, "later"], "found"),
        ([], ""),
        ({"data": '{"message":{"text":"nested"}}'}, "nested"),
        ({"message": "message"}, "message"),
        ({"data": "not json"}, "not json"),
        ({"unsupported": "not text"}, ""),
    ],
)
def test_provider_text_extraction_handles_nested_shapes(
    raw: object, expected: str
) -> None:
    assert common.extract_text(raw) == expected


def test_http_error_survives_unreadable_body_and_limits_diagnostic_size() -> None:
    error = requests.HTTPError("503 unavailable")
    response = MagicMock(status=200)
    response.raise_for_status.side_effect = error
    type(response).text = PropertyMock(side_effect=RuntimeError("body unavailable"))
    with pytest.raises(AskProviderError, match="503 unavailable") as raised:
        common.raise_for_provider_response(response, "provider")
    assert raised.value.__cause__ is error
    response = Mock(text="x" * 301)
    response.raise_for_status.side_effect = error
    with pytest.raises(AskProviderError) as raised:
        common.raise_for_provider_response(response, "provider")
    assert str(raised.value).endswith("x" * 300)
    assert "x" * 301 not in str(raised.value)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (" raw answer ", "raw answer"),
        (
            [" first ", "", {"title": "Title", "summary": "Summary"}],
            "1. first\n3. Title\nSummary",
        ),
        (
            {
                "facts": ["fact"],
                "concepts": [
                    {
                        "output": "title: Concept\nsummary: Definition\nsummary: duplicate"
                    }
                ],
                "extra": ["extra"],
                "quotes": [],
            },
            "## Concepts\n1. Concept\nDefinition\n\n## Facts\n1. fact\n\n## extra\n1. extra",
        ),
        ({"text": "direct"}, "direct"),
        ({"unknown": 1}, '{"unknown": 1}'),
        (None, ""),
    ],
)
def test_workflow_formats_retrieval_categories_in_stable_order(
    payload: object, expected: str
) -> None:
    assert workflow._format_workflow_payload(payload) == expected


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (None, ""),
        ({"title": "Title", "output": "unstructured"}, "Title"),
        ({"title": "Same", "summary": "Same"}, "Same"),
        ({"output": "title: Name\nslice_content: Details\nno-colon"}, "Name\nDetails"),
        ({}, "{}"),
    ],
)
def test_workflow_item_uses_structured_fields_before_fallback(
    item: object, expected: str
) -> None:
    assert workflow._format_workflow_item(item) == expected


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (None, "invalid payload"),
        ({"code": 0, "data": " "}, "no retrievable text"),
        (
            {"code": 3, "message": "failed", "detail": {"logid": "trace"}},
            r"failed \(logid: trace\)",
        ),
        ({"code": 3}, "unknown error"),
    ],
)
def test_workflow_business_errors_have_actionable_diagnostics(
    payload: object, message: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = MagicMock(status=200)
    response.json.return_value = payload
    _stub_request(monkeypatch, response)
    with pytest.raises(AskProviderError, match=message):
        _run("coze_workflow")


def test_workflow_passes_extra_parameters_without_mutating_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock(status=200)
    response.json.return_value = {"code": "0", "data": "plain answer"}
    request = _stub_request(monkeypatch, response)
    config = {
        **CONFIG,
        "query_key": "prompt",
        "parameters": {"other": 1},
        "extra_body": {"is_async": False},
    }
    before = copy.deepcopy(config)
    assert [item.content for item in _run("coze_workflow", config)] == ["plain answer"]
    assert config == before
    assert json.loads(request.call_args.kwargs["body"]) == {
        "workflow_id": "workflow",
        "parameters": {"other": 1, "prompt": "question"},
        "is_async": False,
    }


def test_volc_request_normalizes_preprocessing_without_changing_caller_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock(status=200)
    response.json.return_value = {
        "data": {
            "chunks": [{"text": "one"}, {"text": "one"}],
            "records": [{"content": "two"}],
        }
    }
    request = _stub_request(monkeypatch, response)
    config = {
        **CONFIG,
        "domain": "example.test",
        "scheme": "ftp",
        "path": "search",
        "limit": -2,
        "dense_weight": 0.4,
        "image_query": " image ",
        "pre_processing": {
            "messages": [
                None,
                {"role": "user", "content": " "},
                {"role": "assistant", "content": None},
                {"role": "", "content": 7},
            ]
        },
        "post_processing": {"rerank": True},
        "query_param": {"filter": "course"},
    }
    before = copy.deepcopy(config)
    assert [item.content for item in _run("volc_knowledge", config)] == ["one", "two"]
    assert config == before
    assert request.call_args.args[1] == "https://example.test/search"
    body = json.loads(request.call_args.kwargs["body"])
    assert body["limit"] == 20
    assert body["dense_weight"] == 0.4
    assert body["image_query"] == "image"
    assert body["pre_processing"]["messages"] == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": ""},
        {"role": "user", "content": "7"},
    ]
    assert body["post_processing"] == {"rerank": True}
    assert body["query_param"] == {"filter": "course"}
    assert request.call_args.kwargs["headers"]["Authorization"].startswith(
        "HMAC-SHA256 Credential=test-ak/"
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (["one", "one", "two"], ["one", "two"]),
        ({"text": "direct"}, ["direct"]),
        ({"data": ["nested"]}, ["nested"]),
        (None, []),
    ],
)
def test_volc_retrieval_deduplicates_snippets_in_order(
    payload: object, expected: list[str]
) -> None:
    assert volc._collect_text_chunks(payload) == expected


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"code": 403, "message": "denied"}, "denied"),
        ({"code": 0, "data": {}}, "no retrievable text"),
    ],
)
def test_volc_business_failure_or_empty_retrieval_raises_domain_error(
    payload: dict, message: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = MagicMock(status=200)
    response.json.return_value = payload
    _stub_request(monkeypatch, response)
    with pytest.raises(AskProviderError, match=message):
        _run("volc_knowledge")


def test_volc_query_signing_canonicalizes_repeated_and_empty_parameters() -> None:
    assert (
        volc._normalize_query({"z": ["a b", None], "a/b": "+"})
        == "a%2Fb=%2B&z=a%20b&z="
    )
    assert volc._normalize_pre_processing({"enabled": True}, "query") == {
        "enabled": True
    }
    assert volc._normalize_pre_processing({"messages": [None]}, "query") == {
        "messages": [None]
    }


def test_biji_no_results_without_synthesis_returns_localized_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock(status=200)
    response.json.return_value = {"success": True, "data": []}
    _stub_request(monkeypatch, response)
    monkeypatch.setattr(biji, "_", lambda key: key)
    assert [item.content for item in _run("get_biji_knowledge")] == [
        "server.learn.askProviderNoResults"
    ]
    assert biji._extract_results(None) == []
    assert biji._format_result(2, "standalone") == "2. standalone"
    with pytest.raises(AskProviderError, match="failed"):
        biji._raise_for_api_error({"success": False, "error": "failed"})


def test_biji_synthesis_filters_empty_and_nontext_model_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock(status=200)
    response.json.return_value = {"data": {"results": []}}
    _stub_request(monkeypatch, response)
    factory = Mock(
        return_value=iter(
            [
                SimpleNamespace(result=None),
                SimpleNamespace(result=""),
                SimpleNamespace(result="answer"),
            ]
        )
    )
    result = _run(
        "get_biji_knowledge",
        runtime=AskProviderRuntime(llm_context_stream_factory=factory),
    )
    assert [item.content for item in result] == ["answer"]
    factory.assert_called_once_with("")

"""Exercise native Volc retrieval context at the signed outbound boundary."""

from __future__ import annotations

import copy
import hashlib
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn.ask_provider_adapters import (
    common,
)
from flaskr.service.learn.ask_provider_adapters import (
    volc_knowledge_adapter as volc,
)
from flaskr.service.learn.ask_provider_adapters.base import AskProviderError

if TYPE_CHECKING:
    from flask import Flask


class Response(SimpleNamespace):
    """Implement the safe client's response protocol without external requests."""

    def __enter__(self) -> object:
        """Return the configured offline response."""
        return self

    def __exit__(self, *_args: object) -> None:
        """No external resources are allocated."""


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Capture signed UTF-8 requests and supply configurable provider responses."""
    state = {"response": {"code": 0, "data": {"records": [{"content": "retrieved"}]}}}
    monkeypatch.setattr(common.SafeOutboundClient, "new_deadline", lambda _self: 123.0)
    monkeypatch.setattr(
        common.SafeOutboundClient,
        "validate_url",
        lambda _self, url, **_kwargs: SimpleNamespace(url=url),
    )

    def request(_self: object, method: str, url: str, **kwargs: object) -> Response:
        """Record the actual adapter serialization and signature headers."""
        state.update(method=method, url=url, **kwargs)
        return Response(status=200, content=json.dumps(state["response"]).encode())

    monkeypatch.setattr(common.SafeOutboundClient, "request", request)
    return state


def send(app: Flask, messages: list, **config: object) -> list[str]:
    """Run the real adapter with inert credentials and the captured HTTP boundary."""
    return [
        chunk.content
        for chunk in volc.VolcKnowledgeAskProviderAdapter().stream_answer(
            app,
            "learner",
            "Current question?",
            messages,
            {
                "config": {
                    "account_id": "account",
                    "ak": "test-ak",
                    "sk": "test-sk",
                    "collection_name": "collection",
                    **config,
                }
            },
        )
    ]


@pytest.mark.parametrize(
    "path",
    [
        None,
        "api/knowledge/collection/search_knowledge",
        "/api/knowledge/collection/search_knowledge/",
    ],
)
def test_native_request_keeps_context_and_signs_final_body(
    app: Flask, transport: dict, path: str | None
) -> None:
    """Scoped course data and history reach rewriting before the body is signed."""
    messages = [
        {
            "role": "system",
            "content": 'Rules. Untrusted course memory: {"style":"brief é"}',
        },
        {"role": "assistant", "content": "Selected anchor"},
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier reply"},
        {"role": "user", "content": "Current question?"},
    ]
    original = copy.deepcopy(messages)
    assert send(app, messages, path=path) == ["retrieved"]
    body = transport["body"]
    payload = json.loads(body)
    assert payload["query"] == "Current question?"
    assert payload["pre_processing"] == {"rewrite": True, "messages": messages}
    assert hashlib.sha256(body).hexdigest() == transport["headers"]["X-Content-Sha256"]
    assert transport["headers"]["Authorization"].startswith(
        "HMAC-SHA256 Credential=test-ak/"
    )
    assert transport["deadline"] == 123.0
    assert messages == original


def test_native_context_filters_invalid_entries_and_only_removes_tail_duplicate(
    app: Flask, transport: dict
) -> None:
    """Keep historical repeated questions and literal text while rejecting nontext roles."""
    history = [
        {"role": "system", "content": "  Exact instructions  "},
        {"role": "user", "content": "Current question?"},
        {"role": "assistant", "content": "Old reply"},
        {"role": "tool", "content": "PRIVATE TOOL"},
        {"role": ["user"], "content": "INVALID ROLE"},
        {"role": "assistant", "content": {"secret": "NON-TEXT"}},
        {"role": "user", "content": "   "},
        None,
        {"role": "user", "content": "Current question?"},
    ]
    before = copy.deepcopy(history)
    send(app, history)
    assert json.loads(transport["body"])["pre_processing"]["messages"] == [
        *history[:3],
        {"role": "user", "content": "Current question?"},
    ]
    assert history == before


@pytest.mark.parametrize("rewrite", [False, None, 0, "false"])
def test_explicit_rewrite_opt_out_retains_original_request(
    app: Flask, transport: dict, rewrite: object
) -> None:
    """Never enable rewriting or transmit unused private context over explicit settings."""
    pre = {"rewrite": rewrite, "need_instruction": True}
    send(app, [{"role": "system", "content": "PRIVATE NOTE"}], pre_processing=pre)
    assert json.loads(transport["body"])["pre_processing"] == pre
    assert b"PRIVATE NOTE" not in transport["body"]


@pytest.mark.parametrize("messages", [[], None, [{"role": "user", "content": ""}]])
def test_explicit_message_override_retains_normalization(
    app: Flask, transport: dict, messages: object
) -> None:
    """Custom templates keep full ownership including empty and malformed overrides."""
    pre = {"messages": messages, "rewrite": True, "need_instruction": True}
    before = copy.deepcopy(pre)
    send(app, [{"role": "system", "content": "PRIVATE NOTE"}], pre_processing=pre)
    expected = copy.deepcopy(pre)
    if messages:
        expected["messages"][0]["content"] = "Current question?"
    assert json.loads(transport["body"])["pre_processing"] == expected
    assert pre == before


def test_preprocessing_options_survive_automatic_context(
    app: Flask, transport: dict
) -> None:
    """Keep teacher options while filling the native missing context and rewrite default."""
    pre = {"need_instruction": True, "return_token_usage": True}
    before = copy.deepcopy(pre)
    history = [{"role": "assistant", "content": "Selected anchor"}]
    send(app, history, pre_processing=pre, post_processing={"rerank_switch": False})
    body = json.loads(transport["body"])
    assert body["pre_processing"] == {
        **pre,
        "rewrite": True,
        "messages": [*history, {"role": "user", "content": "Current question?"}],
    }
    assert body["post_processing"] == {"rerank_switch": False}
    assert pre == before


@pytest.mark.parametrize(
    "messages", [[], [{"role": "user", "content": "Current question?"}]]
)
def test_query_only_does_not_gain_rewrite(
    app: Flask, transport: dict, messages: list
) -> None:
    """Do not add provider preprocessing or extra model work to a plain query."""
    send(app, messages)
    assert "pre_processing" not in json.loads(transport["body"])


def test_non_native_path_keeps_query_only_contract(app: Flask, transport: dict) -> None:
    """Bespoke endpoints never receive newly invented native preprocessing fields."""
    send(app, [{"role": "system", "content": "PRIVATE NOTE"}], path="/custom/search")
    assert "pre_processing" not in json.loads(transport["body"])


@pytest.mark.parametrize(
    "response",
    [
        {"code": 1, "message": "PRIVATE NOTE"},
        {"code": 1, "message": "PRIVATE NOTE", "data": {"content": "PRIVATE NOTE"}},
        {"code": 0, "data": {"echo": "PRIVATE NOTE"}},
    ],
)
def test_provider_echo_never_exposes_course_context(
    app: Flask, transport: dict, monkeypatch: pytest.MonkeyPatch, response: dict
) -> None:
    """Provider failures cannot echo newly forwarded notes into host warnings."""
    transport["response"] = response
    warnings = []
    monkeypatch.setattr(
        app.logger, "warning", lambda *args, **kwargs: warnings.append((args, kwargs))
    )
    with pytest.raises(AskProviderError) as raised:
        send(app, [{"role": "system", "content": "PRIVATE NOTE"}])
    assert "PRIVATE NOTE" not in str(raised.value)
    assert "PRIVATE NOTE" not in repr(warnings)


@pytest.mark.parametrize("pre", [[], "invalid", 0])
def test_invalid_preprocessing_does_not_gain_context(
    app: Flask, transport: dict, pre: object
) -> None:
    """Preserve ignored legacy configuration instead of manufacturing new options."""
    send(app, [{"role": "system", "content": "PRIVATE NOTE"}], pre_processing=pre)
    assert "pre_processing" not in json.loads(transport["body"])


def test_explicit_rewrite_true_receives_missing_messages(
    app: Flask, transport: dict
) -> None:
    """An existing rewrite opt-in gains host history without changing other options."""
    history = [
        {"role": "system", "content": "Course context"},
        {"role": "assistant", "content": "Selected anchor"},
    ]
    send(app, history, pre_processing={"rewrite": True, "return_token_usage": False})
    assert json.loads(transport["body"])["pre_processing"] == {
        "rewrite": True,
        "return_token_usage": False,
        "messages": [*history, {"role": "user", "content": "Current question?"}],
    }

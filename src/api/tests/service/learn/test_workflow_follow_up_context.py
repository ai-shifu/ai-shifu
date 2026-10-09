"""Verify explicit Workflow context binding without changing existing query inputs."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn.ask_provider_adapters import common
from flaskr.service.learn.ask_provider_adapters import coze_workflow_adapter as workflow
from flaskr.service.learn.ask_provider_adapters.base import (
    AskProviderConfigError,
    AskProviderError,
)
from flaskr.service.shifu.shifu_draft_funcs import (
    normalize_ask_provider_config,
    serialize_ask_provider_config,
)

if TYPE_CHECKING:
    from flask import Flask


class Response(SimpleNamespace):
    """Implement the safe client's context-managed JSON response offline."""

    def __enter__(self) -> object:
        """Return the configured inert response."""
        return self

    def __exit__(self, *_args: object) -> None:
        """No resources are acquired."""


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Capture the actual serialized payload and provide configurable responses."""
    state = {"response": {"code": 0, "data": "retrieved"}}

    def request(_self: object, method: str, url: str, **kwargs: object) -> Response:
        """Stop at the HTTP boundary without connecting to any provider."""
        state.update(method=method, url=url, **kwargs)
        return Response(status=200, content=json.dumps(state["response"]).encode())

    monkeypatch.setattr(common.SafeOutboundClient, "request", request)
    return state


def send(app: Flask, messages: list, **config: object) -> list[str]:
    """Run a real adapter with inert credentials and the intercepted request."""
    return [
        chunk.content
        for chunk in workflow.CozeWorkflowAskProviderAdapter().stream_answer(
            app,
            "learner",
            "Current question?",
            messages,
            {"config": {"api_key": "test-key", "workflow_id": "workflow", **config}},
        )
    ]


def test_bound_context_reaches_declared_string_input(
    app: Flask, transport: dict
) -> None:
    """Keep the raw question while sending exact scoped context as separate JSON text."""
    history = [
        {
            "role": "system",
            "content": 'Rules. Untrusted course memory: {"style":"brief é"}',
        },
        {"role": "assistant", "content": "Selected anchor"},
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier reply"},
        {"role": "user", "content": "Current question?"},
    ]
    before = copy.deepcopy(history)
    config = {
        "context_key": "classroom_context",
        "query_key": "input",
        "parameters": {"tenant": "static", "input": "old", "classroom_context": "old"},
    }
    original = copy.deepcopy(config)
    assert send(app, history, **config) == ["retrieved"]
    payload = json.loads(transport["body"])
    assert payload["parameters"]["input"] == "Current question?"
    assert payload["parameters"]["tenant"] == "static"
    bound = payload["parameters"]["classroom_context"]
    assert isinstance(bound, str)
    assert json.loads(bound) == {"messages": history}
    assert config == original
    assert history == before
    assert transport["url"] == "https://api.coze.cn/v1/workflow/run"
    assert transport["headers"]["Authorization"] == "Bearer test-key"


@pytest.mark.parametrize("key", [None, "", "  "])
def test_unbound_workflow_keeps_existing_query(
    app: Flask, transport: dict, key: object
) -> None:
    """Existing workflows never gain undeclared inputs or a changed question."""
    send(app, [{"role": "system", "content": "PRIVATE NOTE"}], context_key=key)
    assert json.loads(transport["body"])["parameters"] == {"query": "Current question?"}


def test_bound_context_filters_invalid_messages_and_preserves_repeated_history(
    app: Flask, transport: dict
) -> None:
    """Filter only unsupported data and remove only the trailing current-query copy."""
    history = [
        {"role": "system", "content": "  exact rules  "},
        {"role": "user", "content": "Current question?"},
        {"role": "assistant", "content": "Prior reply"},
        {"role": "tool", "content": "PRIVATE TOOL"},
        {"role": ["user"], "content": "INVALID ROLE"},
        {"role": "assistant", "content": {"secret": "NOT TEXT"}},
        {"role": "user", "content": "  "},
        None,
        {"role": "user", "content": "Current question?"},
    ]
    send(app, history, context_key="context")
    value = json.loads(json.loads(transport["body"])["parameters"]["context"])
    assert value == {
        "messages": [*history[:3], {"role": "user", "content": "Current question?"}]
    }


def test_bound_empty_context_still_supplies_declared_input(
    app: Flask, transport: dict
) -> None:
    """A required start-node String input stays populated on the first question."""
    send(app, [], context_key="context")
    assert json.loads(json.loads(transport["body"])["parameters"]["context"]) == {
        "messages": [{"role": "user", "content": "Current question?"}]
    }


@pytest.mark.parametrize("key", [True, 12, [], {}, "query", " query "])
def test_malformed_or_colliding_binding_fails_before_request(
    app: Flask, transport: dict, key: object
) -> None:
    """Never overwrite the current question or silently accept invalid binding names."""
    with pytest.raises(AskProviderConfigError):
        send(app, [], context_key=key)
    assert "body" not in transport


def test_extra_body_parameters_keeps_complete_override(
    app: Flask, transport: dict
) -> None:
    """A complete explicit payload continues to opt out of generated parameters."""
    custom = {
        "parameters": {"input": "custom", "context": "static"},
        "bot_id": "bound-bot",
    }
    before = copy.deepcopy(custom)
    send(
        app,
        [{"role": "system", "content": "PRIVATE NOTE"}],
        context_key="context",
        extra_body=custom,
    )
    assert json.loads(transport["body"])["parameters"] == custom["parameters"]
    assert custom == before
    assert b"PRIVATE NOTE" not in transport["body"]


def test_other_extra_fields_keep_context(app: Flask, transport: dict) -> None:
    """Unrelated workflow options do not disable the declared context binding."""
    send(app, [], context_key=" context ", extra_body={"bot_id": "bound-bot"})
    payload = json.loads(transport["body"])
    assert payload["bot_id"] == "bound-bot"
    assert "context" in payload["parameters"]


def test_advanced_configuration_roundtrip_preserves_binding() -> None:
    """The existing course serializer persists advanced mapping and override fields."""
    config = {
        "provider": "coze_workflow",
        "mode": "provider_only",
        "config": {
            "api_key": "test-key",
            "workflow_id": "workflow",
            "context_key": "context",
            "query_key": "input",
            "parameters": {"tenant": "static"},
        },
    }
    assert (
        normalize_ask_provider_config(serialize_ask_provider_config(config)) == config
    )


@pytest.mark.parametrize(
    "response",
    [
        {"code": 3, "msg": "PRIVATE NOTE", "detail": {"logid": "PRIVATE NOTE"}},
        {
            "code": "PRIVATE NOTE",
            "message": "PRIVATE NOTE",
            "data": {"echo": "PRIVATE NOTE"},
        },
    ],
)
def test_workflow_error_echo_does_not_escape_to_host(
    app: Flask, transport: dict, response: dict
) -> None:
    """New private context cannot return through the host's provider exception warning."""
    transport["response"] = response
    with pytest.raises(AskProviderError) as raised:
        send(
            app, [{"role": "system", "content": "PRIVATE NOTE"}], context_key="context"
        )
    assert str(raised.value) == "coze_workflow returned an error response"


def test_custom_query_key_collision_fails_before_request(
    app: Flask, transport: dict
) -> None:
    """A custom query input has the same collision protection as the default key."""
    with pytest.raises(AskProviderConfigError):
        send(app, [], context_key=" input ", query_key="input")
    assert "body" not in transport

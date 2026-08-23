"""Verify ask preview HTTP route behavior."""

from types import SimpleNamespace

from flaskr.service.common.models import ERROR_CODE
from flaskr.service.learn.ask_provider_adapters import AskProviderError
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG

_PREVIEW_TOKEN = "preview-token"  # stub session token, `validate_user` is mocked


class _FakeObservation:
    """Mimics a Langfuse SDK v4 observation object."""

    def __init__(self, kind: str = "span", **kwargs: object) -> None:
        self.kind = kind
        self.kwargs = kwargs
        self.updates = []
        self.ended = False
        self.public = False
        self.trace_id = "f" * 32
        self.id = f"fake-{kind}-id"
        self.generations = []
        self.span_calls = []
        self.last_span = None

    def start_observation(self, as_type: object = "span", **kwargs: object):
        child = _FakeObservation(as_type, **kwargs)
        if as_type == "generation":
            self.generations.append(child)
        else:
            self.span_calls.append(kwargs)
            self.last_span = child
        return child

    def update(self, **kwargs: object):
        self.updates.append(kwargs)

    def set_trace_as_public(self):
        self.public = True

    def end(self):
        self.ended = True

    @property
    def end_kwargs(self):
        merged = {}
        for item in self.updates:
            merged.update(item)
        return merged


class _FakeLangfuseClient:
    def __init__(self) -> None:
        self.traces = []

    def start_observation(
        self,
        as_type: object = "span",
        trace_context: object = None,
        **kwargs: object,
    ):
        root = _FakeObservation(as_type, **kwargs)
        root.trace_context = trace_context or {}
        self.traces.append(root)
        return root


def _mock_authenticated_user(
    monkeypatch: object,
    user_bid: str = "preview-user-1",
    *,
    is_creator: bool = False,
) -> SimpleNamespace:
    user = SimpleNamespace(
        user_id=user_bid,
        language="en-US",
        is_creator=is_creator,
        is_operator=False,
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: user,
        raising=False,
    )
    return user


def _auth_headers(token: str = _PREVIEW_TOKEN) -> dict[str, str]:
    return {"Token": token}


def test_ask_preview_route_success_with_provider(
    monkeypatch: object, test_client: object
):
    _mock_authenticated_user(monkeypatch)
    fake_langfuse = _FakeLangfuseClient()

    def fake_stream_ask_provider_response(*args: object, **kwargs: object):
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
        "flaskr.service.shifu.route.get_langfuse_client",
        lambda: fake_langfuse,
        raising=False,
    )

    resp = test_client.post(
        "/api/shifu/ask/preview",
        headers=_auth_headers(),
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
    assert trace.kwargs["input"] == "hello"
    # The generation hangs directly off the root observation.
    assert len(trace.generations) == 1
    generation = trace.generations[0]
    assert generation.kwargs["model"] == "dify"
    assert generation.end_kwargs["metadata"]["provider_config"]["config"][
        "api_key"
    ] == ("[REDACTED]")
    assert generation.end_kwargs["output"] == "provider result"
    assert generation.ended
    assert trace.end_kwargs["output"] == "provider result"


def test_ask_preview_route_fallbacks_to_llm(monkeypatch: object, test_client: object):
    _mock_authenticated_user(monkeypatch)

    def fake_stream_ask_provider_response(*args: object, **kwargs: object):
        _ = args
        provider = kwargs.get("provider", "")
        if provider == "dify":
            message = "provider failed"
            raise AskProviderError(message)
        assert provider == "llm"
        yield SimpleNamespace(content="llm fallback")

    monkeypatch.setattr(
        "flaskr.service.learn.ask_provider_adapters.stream_ask_provider_response",
        fake_stream_ask_provider_response,
        raising=False,
    )

    resp = test_client.post(
        "/api/shifu/ask/preview",
        headers=_auth_headers(),
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
    # The raw provider error stays in the logs; the payload carries the
    # localized, human-readable message.
    assert payload["data"]["provider_error"] == (
        "The external knowledge service is temporarily unavailable."
    )


def test_ask_preview_route_rejects_empty_query(
    monkeypatch: object, test_client: object
):
    _mock_authenticated_user(monkeypatch)

    resp = test_client.post(
        "/api/shifu/ask/preview",
        headers=_auth_headers(),
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
    monkeypatch: object, test_client: object
):
    _mock_authenticated_user(monkeypatch)

    def fake_stream_ask_provider_response(*args: object, **kwargs: object):
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
        headers=_auth_headers(),
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
    monkeypatch: object, test_client: object
):
    _mock_authenticated_user(monkeypatch)

    def fake_stream_ask_provider_response(*args: object, **kwargs: object):
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
        headers=_auth_headers(),
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


def test_ask_preview_route_provider_only_accepts_get_biji_knowledge(
    monkeypatch: object, test_client: object
):
    _mock_authenticated_user(monkeypatch)
    captured: dict[str, object] = {}

    def fake_stream_ask_provider_response(*args: object, **kwargs: object):
        _ = args
        provider = kwargs.get("provider", "")
        assert provider == "get_biji_knowledge"
        captured["runtime"] = kwargs.get("runtime")
        yield SimpleNamespace(content="get biji synthesized result")

    monkeypatch.setattr(
        "flaskr.service.learn.ask_provider_adapters.stream_ask_provider_response",
        fake_stream_ask_provider_response,
        raising=False,
    )

    resp = test_client.post(
        "/api/shifu/ask/preview",
        headers=_auth_headers(),
        json={
            "query": "hello",
            "ask_model": "gpt-test",
            "ask_provider_config": {
                "provider": "get_biji_knowledge",
                "mode": "provider_only",
                "config": {
                    "api_key": "gk-live-1",
                    "client_id": "cli-1",
                    "topic_id": "topic-1",
                    "top_k": 5,
                },
            },
        },
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["answer"] == "get biji synthesized result"
    assert payload["data"]["provider"] == "get_biji_knowledge"
    assert payload["data"]["requested_provider"] == "get_biji_knowledge"
    assert payload["data"]["fallback_used"] is False
    # Synthesis providers must receive an LLM-capable runtime in preview.
    runtime = captured["runtime"]
    assert runtime is not None
    assert runtime.llm_context_stream_factory is not None


def test_ask_preview_route_surfaces_friendly_provider_error(
    monkeypatch: object, test_client: object
):
    _mock_authenticated_user(monkeypatch)

    def fake_stream_ask_provider_response(*args: object, **kwargs: object):
        _ = (args, kwargs)
        message = (
            "get_biji_knowledge request failed: 401 Client Error for url: "
            "https://openapi.biji.com/... | {raw json body}"
        )
        raise AskProviderError(
            message,
            user_message="Knowledge base authentication failed.",
        )
        yield  # pragma: no cover

    monkeypatch.setattr(
        "flaskr.service.learn.ask_provider_adapters.stream_ask_provider_response",
        fake_stream_ask_provider_response,
        raising=False,
    )

    resp = test_client.post(
        "/api/shifu/ask/preview",
        headers=_auth_headers(),
        json={
            "query": "hello",
            "ask_model": "gpt-test",
            "ask_provider_config": {
                "provider": "get_biji_knowledge",
                "mode": "provider_only",
                "config": {
                    "api_key": "gk-live-1",
                    "client_id": "cli-1",
                    "topic_id": "topic-1",
                },
            },
        },
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == ERROR_CODE["server.common.paramsError"]
    assert "Knowledge base authentication failed." in payload["message"]
    assert "openapi.biji.com" not in payload["message"]


def test_ask_preview_route_falls_back_to_generic_provider_error(
    monkeypatch: object, test_client: object
):
    _mock_authenticated_user(monkeypatch)

    def fake_stream_ask_provider_response(*args: object, **kwargs: object):
        _ = (args, kwargs)
        message = "dify request failed: 500 | {raw body}"
        raise AskProviderError(message)
        yield  # pragma: no cover

    monkeypatch.setattr(
        "flaskr.service.learn.ask_provider_adapters.stream_ask_provider_response",
        fake_stream_ask_provider_response,
        raising=False,
    )

    resp = test_client.post(
        "/api/shifu/ask/preview",
        headers=_auth_headers(),
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
    assert payload["code"] == ERROR_CODE["server.common.paramsError"]
    assert "raw body" not in payload["message"]
    assert "request failed" not in payload["message"]


def test_ask_preview_route_uses_authenticated_creator_for_debug_billing(
    monkeypatch: object, test_client: object
):
    fake_langfuse = _FakeLangfuseClient()
    captured: dict[str, object] = {}

    _mock_authenticated_user(monkeypatch, "creator-token-1", is_creator=True)
    monkeypatch.setattr(
        "flaskr.service.shifu.route.admit_creator_usage",
        lambda _app, creator_bid, usage_scene: captured.setdefault(
            "admission",
            {
                "creator_bid": creator_bid,
                "usage_scene": usage_scene,
            },
        ),
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.route.get_langfuse_client",
        lambda: fake_langfuse,
        raising=False,
    )

    def fake_chat_llm(*args: object, **kwargs: object):
        _ = args
        captured["chat_llm"] = kwargs
        yield SimpleNamespace(content="debug answer")

    def fake_stream_ask_provider_response(*args: object, **kwargs: object):
        _ = args
        runtime = kwargs.get("runtime")
        assert runtime is not None
        yield from runtime.llm_stream_factory()

    monkeypatch.setattr(
        "flaskr.api.llm.chat_llm",
        fake_chat_llm,
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.learn.ask_provider_adapters.stream_ask_provider_response",
        fake_stream_ask_provider_response,
        raising=False,
    )

    resp = test_client.post(
        "/api/shifu/ask/preview",
        headers={"Token": "creator-token"},
        json={
            "query": "hello",
            "ask_model": "gpt-test",
            "ask_provider_config": {
                "provider": "llm",
                "mode": "provider_only",
                "config": {},
            },
        },
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert captured["admission"] == {
        "creator_bid": "creator-token-1",
        "usage_scene": BILL_USAGE_SCENE_DEBUG,
    }
    chat_llm_kwargs = captured["chat_llm"]
    assert chat_llm_kwargs["billable"] == 1
    usage_context = chat_llm_kwargs["usage_context"]
    assert usage_context.user_bid == "creator-token-1"
    assert usage_context.usage_scene == BILL_USAGE_SCENE_DEBUG
    assert usage_context.billable == 1


def test_ask_preview_route_passes_debug_usage_context_for_creator(
    monkeypatch: object, test_client: object
):
    fake_langfuse = _FakeLangfuseClient()
    captured: dict[str, object] = {}

    def fake_chat_llm(*args: object, **kwargs: object):
        _ = args
        captured.update(kwargs)
        yield SimpleNamespace(content="debug answer")

    def fake_stream_ask_provider_response(*args: object, **kwargs: object):
        _ = args
        runtime = kwargs.get("runtime")
        assert runtime is not None
        yield from runtime.llm_stream_factory()

    _mock_authenticated_user(monkeypatch, "creator-debug-1", is_creator=True)
    monkeypatch.setattr(
        "flaskr.service.shifu.route.get_langfuse_client",
        lambda: fake_langfuse,
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.route.admit_creator_usage",
        lambda _app, creator_bid, usage_scene: {
            "creator_bid": creator_bid,
            "usage_scene": usage_scene,
        },
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.api.llm.chat_llm",
        fake_chat_llm,
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.learn.ask_provider_adapters.stream_ask_provider_response",
        fake_stream_ask_provider_response,
        raising=False,
    )

    resp = test_client.post(
        "/api/shifu/ask/preview",
        headers=_auth_headers(),
        json={
            "query": "hello",
            "ask_model": "gpt-test",
            "ask_provider_config": {
                "provider": "llm",
                "mode": "provider_only",
                "config": {},
            },
        },
    )

    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["answer"] == "debug answer"
    assert captured["usage_scene"] == BILL_USAGE_SCENE_DEBUG
    assert captured["billable"] == 1
    usage_context = captured["usage_context"]
    assert usage_context.user_bid == "creator-debug-1"
    assert usage_context.usage_scene == BILL_USAGE_SCENE_DEBUG
    assert usage_context.billable == 1

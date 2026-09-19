"""Verify ask preview HTTP route behavior."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing.admission import admit_creator_usage
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    CreditLedgerEntry,
    CreditUsageRate,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.ownership import resolve_usage_creator_bid
from flaskr.service.billing.settlement import settle_bill_usage
from flaskr.service.common.models import ERROR_CODE
from flaskr.service.learn.ask_provider_adapters import AskProviderError
from flaskr.service.metering import record_llm_usage
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG, BILL_USAGE_TYPE_LLM
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu.models import DraftShifu
from flaskr.util.datetime import now_utc

_PREVIEW_SHIFU = "preview-course"
_PREVIEW_OWNER = "preview-owner"

_PREVIEW_TOKEN = "preview-token"  # stub session token, `validate_user` is mocked


@pytest.fixture(autouse=True)
def preview_course(monkeypatch: object, app: object) -> None:
    monkeypatch.setattr(
        "flaskr.api.llm.get_litellm_params_and_model",
        lambda model: ({"api_key": "test"}, model, "test"),
    )
    with app.app_context(), unit_of_work():
        DraftShifu.query.filter_by(shifu_bid=_PREVIEW_SHIFU).delete()
        db.session.add(
            DraftShifu(shifu_bid=_PREVIEW_SHIFU, created_user_bid=_PREVIEW_OWNER)
        )
    monkeypatch.setattr(
        "flaskr.service.shifu.route.shifu_permission_verification",
        lambda _app, _user, course, permission: (
            course == _PREVIEW_SHIFU and permission == "edit"
        ),
    )


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

    def start_observation(self, as_type: object = "span", **kwargs: object) -> object:
        child = _FakeObservation(as_type, **kwargs)
        if as_type == "generation":
            self.generations.append(child)
        else:
            self.span_calls.append(kwargs)
            self.last_span = child
        return child

    def update(self, **kwargs: object) -> None:
        self.updates.append(kwargs)

    def set_trace_as_public(self) -> None:
        self.public = True

    def end(self) -> None:
        self.ended = True

    @property
    def end_kwargs(self) -> object:
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
    ) -> object:
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
) -> None:
    _mock_authenticated_user(monkeypatch)
    fake_langfuse = _FakeLangfuseClient()

    def fake_stream_ask_provider_response(*args: object, **kwargs: object) -> object:
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
            "shifu_bid": _PREVIEW_SHIFU,
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


def test_ask_preview_route_fallbacks_to_llm(
    monkeypatch: object, test_client: object
) -> None:
    _mock_authenticated_user(monkeypatch)

    def fake_stream_ask_provider_response(*args: object, **kwargs: object) -> object:
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
            "shifu_bid": _PREVIEW_SHIFU,
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
) -> None:
    _mock_authenticated_user(monkeypatch)

    resp = test_client.post(
        "/api/shifu/ask/preview",
        headers=_auth_headers(),
        json={
            "shifu_bid": _PREVIEW_SHIFU,
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
) -> None:
    _mock_authenticated_user(monkeypatch)

    def fake_stream_ask_provider_response(*args: object, **kwargs: object) -> object:
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
            "shifu_bid": _PREVIEW_SHIFU,
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
) -> None:
    _mock_authenticated_user(monkeypatch)

    def fake_stream_ask_provider_response(*args: object, **kwargs: object) -> object:
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
            "shifu_bid": _PREVIEW_SHIFU,
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
) -> None:
    _mock_authenticated_user(monkeypatch)
    captured: dict[str, object] = {}

    def fake_stream_ask_provider_response(*args: object, **kwargs: object) -> object:
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
            "shifu_bid": _PREVIEW_SHIFU,
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
) -> None:
    _mock_authenticated_user(monkeypatch)

    def fake_stream_ask_provider_response(*args: object, **kwargs: object) -> object:
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
            "shifu_bid": _PREVIEW_SHIFU,
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
) -> None:
    _mock_authenticated_user(monkeypatch)

    def fake_stream_ask_provider_response(*args: object, **kwargs: object) -> object:
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
            "shifu_bid": _PREVIEW_SHIFU,
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


@pytest.mark.parametrize("is_creator", [True, False])
@pytest.mark.parametrize("provider", ["llm", "dify", "get_biji_knowledge"])
@pytest.mark.parametrize(
    "selection", ["gpt-test", "fast", "balanced", "ultimate", None]
)
def test_ask_preview_route_bills_course_owner(
    monkeypatch: object,
    test_client: object,
    is_creator: bool,
    provider: str,
    selection: str | None,
) -> None:
    fake_langfuse = _FakeLangfuseClient()
    captured: dict[str, object] = {}

    user_bid = f"preview-{provider[:4]}-{is_creator}-{selection}"
    original_selection = selection if selection is not None else " missing-model "
    monkeypatch.setattr(
        "flaskr.api.llm.tiers.resolve_tier_model", lambda _tier: user_bid
    )
    _mock_authenticated_user(monkeypatch, user_bid, is_creator=is_creator)
    monkeypatch.setattr(
        "flaskr.service.metering.recorder._enqueue_usage_settlement",
        lambda _app, *, usage_bid: captured.setdefault("enqueued", usage_bid),
    )
    with test_client.application.app_context(), unit_of_work():
        DraftShifu.query.filter_by(
            shifu_bid=_PREVIEW_SHIFU
        ).one().ask_llm = original_selection
        CreditWalletBucket.query.filter_by(creator_bid=_PREVIEW_OWNER).delete()
        CreditWallet.query.filter_by(creator_bid=_PREVIEW_OWNER).delete()
        db.session.add(
            CreditWallet(
                wallet_bid="preview-owner-wallet",
                creator_bid=_PREVIEW_OWNER,
                available_credits=Decimal(10),
            )
        )
        db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid="preview-owner-bucket",
                wallet_bid="preview-owner-wallet",
                creator_bid=_PREVIEW_OWNER,
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
                priority=20,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                available_credits=Decimal(10),
                original_credits=Decimal(10),
                effective_from=now_utc() - timedelta(days=1),
            )
        )
        db.session.add(
            CreditUsageRate(
                rate_bid=user_bid,
                usage_type=BILL_USAGE_TYPE_LLM,
                provider="openai",
                model=user_bid,
                usage_scene=BILL_USAGE_SCENE_DEBUG,
                billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                unit_size=1,
                credits_per_unit=Decimal(1),
                rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
                effective_from=now_utc() - timedelta(days=1),
                status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
            )
        )
    monkeypatch.setattr(
        "flaskr.service.billing.admission.is_billing_enabled", lambda: True
    )

    def capture_admission(app: object, **kwargs: object) -> object:
        captured["admission"] = kwargs
        return admit_creator_usage(app, **kwargs)

    monkeypatch.setattr(
        "flaskr.service.shifu.route.admit_creator_usage", capture_admission
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.route.get_langfuse_client",
        lambda: fake_langfuse,
        raising=False,
    )

    def fake_chat_llm(*args: object, **kwargs: object) -> object:
        assert args[1] == user_bid
        captured["chat_llm"] = kwargs
        captured["usage_bid"] = record_llm_usage(
            args[0],
            kwargs["usage_context"],
            provider="openai",
            model=user_bid,
            is_stream=True,
            input=5,
            output=7,
            total=12,
        )
        yield SimpleNamespace(content="debug answer")

    def fake_stream_ask_provider_response(*args: object, **kwargs: object) -> object:
        _ = args
        if kwargs["provider"] == "dify":
            message = "provider unavailable"
            raise AskProviderError(message)
        runtime = kwargs.get("runtime")
        assert runtime is not None
        if kwargs["provider"] == "get_biji_knowledge":
            yield from runtime.llm_context_stream_factory("preview knowledge")
        else:
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
            "shifu_bid": _PREVIEW_SHIFU,
            "query": "hello",
            **({"ask_model": selection} if selection is not None else {}),
            "billable": 0,
            "internal": True,
            "is_creator": False,
            "user_bid": "unrelated-user",
            "creator_bid": "unrelated-owner",
            "usage_context": {"billable": 0, "user_bid": "unrelated-user"},
            "ask_provider_config": {
                "provider": provider,
                "mode": "provider_then_llm",
                "config": {
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-api-key",
                    "topic_id": "topic-1",
                    "client_id": "client-1",
                },
            },
        },
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert captured["admission"] == {
        "creator_bid": _PREVIEW_OWNER,
        "shifu_bid": _PREVIEW_SHIFU,
        "usage_scene": BILL_USAGE_SCENE_DEBUG,
    }
    chat_llm_kwargs = captured["chat_llm"]
    assert chat_llm_kwargs["model"] == user_bid
    assert chat_llm_kwargs["usage_metadata"] == {
        "model_selection_field": "ask_llm",
        "model_selection_table": "shifu_draft_shifus",
        "model_selection_record_id": chat_llm_kwargs["usage_metadata"][
            "model_selection_record_id"
        ],
        "model_selection_scope": "course",
        "model_selection_original": original_selection,
        "model_index": "1",
        "model_selection_fallback": True,
        "model_selection_fallback_reason": "invalid_selection",
        "resolved_model": user_bid,
    }
    assert chat_llm_kwargs["billable"] == 1
    usage_context = chat_llm_kwargs["usage_context"]
    assert usage_context.user_bid == user_bid
    assert usage_context.shifu_bid == _PREVIEW_SHIFU
    assert usage_context.usage_scene == BILL_USAGE_SCENE_DEBUG
    assert usage_context.billable == 1
    with test_client.application.app_context():
        record = BillUsageRecord.query.filter_by(usage_bid=captured["usage_bid"]).one()
        assert record.billable == 1
        assert record.usage_scene == BILL_USAGE_SCENE_DEBUG
        assert record.user_bid == user_bid
        assert record.shifu_bid == _PREVIEW_SHIFU
        assert (
            resolve_usage_creator_bid(test_client.application, record) == _PREVIEW_OWNER
        )
        assert captured["enqueued"] == record.usage_bid

        settlement = settle_bill_usage(
            test_client.application, usage_bid=record.usage_bid
        )
        assert settlement["status"] == "settled"
        assert settlement["creator_bid"] == _PREVIEW_OWNER
        assert CreditWallet.query.filter_by(
            creator_bid=_PREVIEW_OWNER
        ).one().available_credits == Decimal(3)
        entries = CreditLedgerEntry.query.filter_by(source_bid=record.usage_bid).all()
        assert entries
        assert all(entry.creator_bid == _PREVIEW_OWNER for entry in entries)
        assert CreditWallet.query.filter_by(creator_bid=user_bid).count() == 0


def test_ask_preview_route_passes_debug_usage_context_for_creator(
    monkeypatch: object, test_client: object
) -> None:
    fake_langfuse = _FakeLangfuseClient()
    captured: dict[str, object] = {}

    def fake_chat_llm(*args: object, **kwargs: object) -> object:
        _ = args
        captured.update(kwargs)
        yield SimpleNamespace(content="debug answer")

    def fake_stream_ask_provider_response(*args: object, **kwargs: object) -> object:
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
        lambda _app, creator_bid, shifu_bid, usage_scene: {
            "creator_bid": creator_bid,
            "shifu_bid": shifu_bid,
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
            "shifu_bid": _PREVIEW_SHIFU,
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

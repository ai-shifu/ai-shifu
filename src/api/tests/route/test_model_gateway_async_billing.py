"""Verify gateway admission, recording, and the existing async settlement path."""

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flaskr import dao
from flaskr.api import llm
from flaskr.common.cache_provider import InMemoryCacheProvider, redis_cache
from flaskr.route import model_gateway_runtime as runtime
from flaskr.service.billing import settlement
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_CACHE_TOKENS,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    CreditLedgerEntry,
    CreditUsageRate,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.models import AppError
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_LLM
from flaskr.service.metering.models import BillUsageRecord


@pytest.fixture
def gateway_billing_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[Flask]:
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)
    cache = InMemoryCacheProvider()
    monkeypatch.setattr(runtime, "cache", cache)
    monkeypatch.setattr(settlement, "cache_provider", cache)
    monkeypatch.setattr(
        "flaskr.service.billing.admission.is_billing_enabled", lambda: True
    )
    monkeypatch.setattr(llm, "count_llm_chat_input_tokens", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(
        llm, "resolve_llm_max_output_tokens", lambda *_args, **_kwargs: 4096
    )
    with app.app_context():
        dao.db.create_all()
        wallet = CreditWallet(
            wallet_bid="wallet-gateway",
            creator_bid="gateway-user",
            available_credits=Decimal(1),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal(1),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-gateway",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
            source_type=0,
            source_bid="source-gateway",
            priority=10,
            original_credits=Decimal(1),
            available_credits=Decimal(1),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 1, 1),
            effective_to=None,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket])
        for metric, price in [
            (BILLING_METRIC_LLM_INPUT_TOKENS, "0.1"),
            (BILLING_METRIC_LLM_CACHE_TOKENS, "0.05"),
            (BILLING_METRIC_LLM_OUTPUT_TOKENS, "0.2"),
        ]:
            dao.db.session.add(
                CreditUsageRate(
                    rate_bid=f"rate-gateway-{metric}",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="*",
                    model="rated-model",
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    billing_metric=metric,
                    unit_size=1,
                    credits_per_unit=Decimal(price),
                    rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
                    effective_from=datetime(2026, 1, 1),
                    status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
                )
            )
        dao.db.session.commit()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _prepare(app: Flask, key: str = "request-1") -> runtime.GatewayChatRequest:
    return runtime.prepare_gateway_chat_request(
        app,
        creator_bid="gateway-user",
        idempotency_key=key,
        payload={
            "model": "rated-model",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 4096,
            "shifu_bid": "untrusted-course",
            "usage_metadata": {"billing_source": "untrusted"},
        },
    )


@pytest.mark.parametrize("stream", [False, True])
def test_gateway_records_then_existing_worker_charges_account_without_holds(
    gateway_billing_app: Flask, monkeypatch: pytest.MonkeyPatch, stream: bool
) -> None:
    queued = []
    monkeypatch.setattr(
        "flaskr.service.metering.recorder._enqueue_usage_settlement",
        lambda _app, *, usage_bid: queued.append(usage_bid),
    )
    monkeypatch.setattr(runtime, "_trace_for_request", lambda _request: MagicMock())
    monkeypatch.setattr(llm, "resolve_langfuse_trace_id", lambda _span: "trace-gateway")
    monkeypatch.setattr(llm, "build_langfuse_observation_link", lambda *_args: {})
    monkeypatch.setattr(
        llm,
        "get_litellm_params_and_model",
        lambda _model: ({"api_key": "test"}, "provider-model", "example"),
    )
    monkeypatch.setattr(
        llm,
        "_prepare_litellm_request_kwargs",
        lambda _provider, _model, _params, kwargs: kwargs,
    )
    usage = SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)
    response = SimpleNamespace(
        usage=usage,
        model_dump=lambda **_kwargs: {
            "id": "reply-1",
            "choices": [{"delta" if stream else "message": {"content": "hello"}}],
        },
    )

    def complete(**kwargs: object) -> object:
        assert CreditLedgerEntry.query.count() == 0
        assert CreditWallet.query.one().available_credits == Decimal(1)
        assert CreditWallet.query.one().reserved_credits == Decimal(0)
        assert "usage_metadata" not in kwargs
        assert "usage_bid" not in kwargs
        return response

    monkeypatch.setattr(llm.litellm, "completion", complete)
    monkeypatch.setattr(
        llm,
        "_iter_stream_with_precontent_retry",
        lambda *_args, **_kwargs: iter([complete()]),
    )
    request = _prepare(gateway_billing_app, "k" * 90)
    # A 4096-token allowance exceeds this wallet, but no worst-case hold is taken.
    assert request.provider_options["max_tokens"] == 4096
    if stream:
        assert (
            len(list(runtime.stream_gateway_chat_request(gateway_billing_app, request)))
            == 1
        )
    else:
        assert (
            runtime.complete_gateway_chat_request(gateway_billing_app, request)["id"]
            == "reply-1"
        )
    assert CreditLedgerEntry.query.count() == 0
    assert CreditWallet.query.one().available_credits == Decimal(1)
    record = BillUsageRecord.query.one()
    assert record.request_id == request.request_id
    assert len(record.request_id) <= BillUsageRecord.request_id.type.length
    assert record.user_bid == "gateway-user"
    assert not record.shifu_bid
    assert record.extra["billing_source"] == "model_gateway"
    assert queued == [record.usage_bid]

    result = settlement.settle_bill_usage(
        gateway_billing_app, usage_bid=record.usage_bid
    )
    assert result.creator_bid == "gateway-user"
    dao.db.session.expire_all()
    wallet = CreditWallet.query.one()
    assert wallet.available_credits == Decimal("0.2")
    assert wallet.reserved_credits == Decimal(0)
    assert wallet.lifetime_consumed_credits == Decimal("0.8")
    assert {row.entry_type for row in CreditLedgerEntry.query.all()} == {
        CREDIT_LEDGER_ENTRY_TYPE_CONSUME
    }
    assert (
        settlement.settle_bill_usage(
            gateway_billing_app, usage_bid=record.usage_bid
        ).status
        == "already_settled"
    )

    # Persisted usage still prevents replay after the short-lived request guard is gone.
    monkeypatch.setattr(runtime, "cache", InMemoryCacheProvider())
    with pytest.raises(runtime.GatewayRequestError) as raised:
        _prepare(gateway_billing_app, "k" * 90)
    assert raised.value.status_code == 409


def test_duplicate_before_usage_is_recorded_does_not_mutate_wallet(
    gateway_billing_app: Flask,
) -> None:
    _prepare(gateway_billing_app)
    with pytest.raises(runtime.GatewayRequestError) as raised:
        _prepare(gateway_billing_app)
    assert raised.value.status_code == 409
    assert CreditLedgerEntry.query.count() == 0
    assert CreditWallet.query.one().reserved_credits == Decimal(0)


def test_empty_wallet_reuses_course_admission_rejection(
    gateway_billing_app: Flask,
) -> None:
    bucket = CreditWalletBucket.query.one()
    bucket.available_credits = Decimal(0)
    dao.db.session.commit()
    with pytest.raises(AppError):
        _prepare(gateway_billing_app)
    assert CreditLedgerEntry.query.count() == 0
    assert BillUsageRecord.query.count() == 0


def test_request_guard_failure_is_closed_without_credit_mutation(
    gateway_billing_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = MagicMock()
    cache.set.side_effect = RuntimeError("cache unavailable")
    monkeypatch.setattr(runtime, "cache", cache)
    with pytest.raises(runtime.GatewayRequestError) as raised:
        _prepare(gateway_billing_app)
    assert raised.value.status_code == 503
    assert CreditLedgerEntry.query.count() == 0


def test_production_guard_does_not_fall_back_to_process_local_cache(
    gateway_billing_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = MagicMock()
    client.set.side_effect = RuntimeError("redis unavailable")
    monkeypatch.setattr("flaskr.dao.get_redis_client", lambda: client)
    monkeypatch.setattr(runtime, "cache", redis_cache)
    with pytest.raises(runtime.GatewayRequestError) as raised:
        _prepare(gateway_billing_app)
    assert raised.value.status_code == 503
    assert CreditLedgerEntry.query.count() == 0


def test_concurrent_admissions_use_existing_insufficient_settlement_policy(
    gateway_billing_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    queued = []
    monkeypatch.setattr(
        "flaskr.service.metering.recorder._enqueue_usage_settlement",
        lambda _app, *, usage_bid: queued.append(usage_bid),
    )
    requests = [
        _prepare(gateway_billing_app, "first"),
        _prepare(gateway_billing_app, "second"),
    ]
    for request in requests:
        llm._record_gateway_llm_usage(
            gateway_billing_app,
            user_id="gateway-user",
            request_id=request.request_id,
            trace_id="",
            provider="example",
            model="rated-model",
            is_stream=False,
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5),
            invoke_model="provider-model",
            fallback_input_tokens=2,
            output_capture="hello",
            latency_ms=1,
            status=0,
            error_message="",
            usage_metadata=None,
        )
    assert CreditLedgerEntry.query.count() == 0
    assert len(queued) == 2
    settlement.settle_bill_usage(gateway_billing_app, usage_bid=queued[0])
    result = settlement.settle_bill_usage(gateway_billing_app, usage_bid=queued[1])
    assert result.status == "insufficient"
    dao.db.session.expire_all()
    wallet = CreditWallet.query.one()
    assert wallet.available_credits == Decimal("0.2")
    assert wallet.reserved_credits == Decimal(0)
    assert wallet.lifetime_consumed_credits == Decimal("0.8")
    assert BillUsageRecord.query.count() == 2


@pytest.mark.parametrize("partial_output", ["", "partial response"])
def test_failed_gateway_usage_is_not_queued_or_charged(
    gateway_billing_app: Flask, monkeypatch: pytest.MonkeyPatch, partial_output: str
) -> None:
    enqueue = MagicMock()
    monkeypatch.setattr(
        "flaskr.service.metering.recorder._enqueue_usage_settlement", enqueue
    )
    llm._record_gateway_llm_usage(
        gateway_billing_app,
        user_id="gateway-user",
        request_id="failed-request",
        trace_id="",
        provider="example",
        model="rated-model",
        is_stream=True,
        usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5),
        invoke_model="provider-model",
        fallback_input_tokens=2,
        output_capture=partial_output,
        latency_ms=1,
        status=1,
        error_message="provider failed",
        usage_metadata=None,
    )
    record = BillUsageRecord.query.one()
    assert record.billable == 0
    enqueue.assert_not_called()
    settlement.settle_bill_usage(gateway_billing_app, usage_bid=record.usage_bid)
    assert CreditLedgerEntry.query.count() == 0
    assert CreditWallet.query.one().available_credits == Decimal(1)

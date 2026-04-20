from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import json
import sys
import threading
import time
import types

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_SOURCE_TYPE_USAGE,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    BillingRenewalEvent,
    CreditLedgerEntry,
    CreditUsageRate,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.tasks import (
    aggregate_daily_ledger_summary_task,
    aggregate_daily_usage_metrics_task,
    dispatch_due_renewal_events_task,
    expire_wallet_buckets_task,
    reconcile_provider_reference_task,
    replay_usage_settlement_task,
    rebuild_daily_aggregates_task,
    retry_failed_renewal_task,
    run_renewal_event_task,
    send_low_balance_alert_task,
    settle_usage_task,
    verify_domain_binding_task,
)
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_LLM
from flaskr.service.metering.models import BillUsageRecord


@pytest.fixture
def billing_task_integration_app(tmp_path):
    db_path = tmp_path / "billing-task.sqlite"
    db_uri = f"sqlite:///{db_path}"

    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI=db_uri,
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": db_uri,
            "ai_shifu_admin": db_uri,
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}},
        REDIS_KEY_PREFIX="billing-task-test",
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _install_fake_app_module(
    monkeypatch: pytest.MonkeyPatch,
    app,
) -> None:
    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: app),
    )


def test_settle_usage_task_calls_settlement_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = object()
    _install_fake_app_module(monkeypatch, fake_app)

    captured: dict[str, object] = {}

    def _fake_settle_bill_usage(app, *, usage_bid: str = ""):
        captured["app"] = app
        captured["usage_bid"] = usage_bid
        return {
            "status": "settled",
            "creator_bid": "creator-task-1",
            "usage_bid": usage_bid,
        }

    monkeypatch.setattr(
        "flaskr.service.billing.tasks.settle_bill_usage",
        _fake_settle_bill_usage,
    )

    payload = settle_usage_task(
        creator_bid="creator-task-1",
        usage_bid="usage-task-1",
    )

    assert captured == {
        "app": fake_app,
        "usage_bid": "usage-task-1",
    }
    assert payload["status"] == "settled"
    assert payload["task_name"] == "billing.settle_usage"
    assert payload["requested_creator_bid"] == "creator-task-1"


def test_settle_usage_task_normalizes_empty_creator_bid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = object()
    _install_fake_app_module(monkeypatch, fake_app)
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.settle_bill_usage",
        lambda app, *, usage_bid="": {"status": "noop", "usage_bid": usage_bid},
    )

    payload = settle_usage_task(creator_bid="  ", usage_bid="usage-task-2")

    assert payload["status"] == "noop"
    assert payload["requested_creator_bid"] is None
    assert payload["task_name"] == "billing.settle_usage"


def test_aggregate_daily_usage_metrics_task_calls_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = object()
    _install_fake_app_module(monkeypatch, fake_app)

    captured: dict[str, object] = {}

    def _fake_aggregate_daily_usage_metrics(
        app,
        *,
        stat_date: str = "",
        creator_bid: str = "",
        finalize: bool = False,
    ):
        captured["app"] = app
        captured["stat_date"] = stat_date
        captured["creator_bid"] = creator_bid
        captured["finalize"] = finalize
        return {
            "status": "aggregated",
            "stat_date": stat_date,
            "creator_bid": creator_bid or None,
            "finalize": finalize,
        }

    monkeypatch.setattr(
        "flaskr.service.billing.tasks.aggregate_daily_usage_metrics",
        _fake_aggregate_daily_usage_metrics,
    )

    payload = aggregate_daily_usage_metrics_task(
        stat_date=" 2026-04-08 ",
        creator_bid=" creator-task-1 ",
        finalize="true",
    )

    assert captured == {
        "app": fake_app,
        "stat_date": "2026-04-08",
        "creator_bid": "creator-task-1",
        "finalize": True,
    }
    assert payload["status"] == "aggregated"
    assert payload["task_name"] == "billing.aggregate_daily_usage_metrics"


def test_aggregate_daily_ledger_summary_task_calls_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = object()
    _install_fake_app_module(monkeypatch, fake_app)

    captured: dict[str, object] = {}

    def _fake_aggregate_daily_ledger_summary(
        app,
        *,
        stat_date: str = "",
        creator_bid: str = "",
        finalize: bool = False,
    ):
        captured["app"] = app
        captured["stat_date"] = stat_date
        captured["creator_bid"] = creator_bid
        captured["finalize"] = finalize
        return {
            "status": "finalized" if finalize else "aggregated",
            "stat_date": stat_date,
            "creator_bid": creator_bid or None,
            "finalize": finalize,
        }

    monkeypatch.setattr(
        "flaskr.service.billing.tasks.aggregate_daily_ledger_summary",
        _fake_aggregate_daily_ledger_summary,
    )

    payload = aggregate_daily_ledger_summary_task(
        stat_date=" 2026-04-08 ",
        creator_bid=" creator-task-2 ",
        finalize="1",
    )

    assert captured == {
        "app": fake_app,
        "stat_date": "2026-04-08",
        "creator_bid": "creator-task-2",
        "finalize": True,
    }
    assert payload["status"] == "finalized"
    assert payload["task_name"] == "billing.aggregate_daily_ledger_summary"


def test_rebuild_daily_aggregates_task_calls_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = object()
    _install_fake_app_module(monkeypatch, fake_app)

    captured: dict[str, object] = {}

    def _fake_rebuild_daily_aggregates(
        app,
        *,
        creator_bid: str = "",
        shifu_bid: str = "",
        date_from: str = "",
        date_to: str = "",
    ):
        captured["app"] = app
        captured["creator_bid"] = creator_bid
        captured["shifu_bid"] = shifu_bid
        captured["date_from"] = date_from
        captured["date_to"] = date_to
        return {
            "status": "rebuilt",
            "creator_bid": creator_bid or None,
            "shifu_bid": shifu_bid or None,
            "date_from": date_from,
            "date_to": date_to,
        }

    monkeypatch.setattr(
        "flaskr.service.billing.tasks.rebuild_daily_aggregates",
        _fake_rebuild_daily_aggregates,
    )

    payload = rebuild_daily_aggregates_task(
        creator_bid=" creator-task-3 ",
        shifu_bid=" shifu-task-1 ",
        date_from=" 2026-04-08 ",
        date_to=" 2026-04-10 ",
    )

    assert captured == {
        "app": fake_app,
        "creator_bid": "creator-task-3",
        "shifu_bid": "shifu-task-1",
        "date_from": "2026-04-08",
        "date_to": "2026-04-10",
    }
    assert payload["status"] == "rebuilt"
    assert payload["task_name"] == "billing.rebuild_daily_aggregates"


def test_verify_domain_binding_task_calls_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = object()
    _install_fake_app_module(monkeypatch, fake_app)

    captured: dict[str, object] = {}

    def _fake_verify_domain_binding(
        app,
        *,
        creator_bid: str = "",
        domain_binding_bid: str = "",
        host: str = "",
        verification_token: str = "",
    ):
        captured["app"] = app
        captured["creator_bid"] = creator_bid
        captured["domain_binding_bid"] = domain_binding_bid
        captured["host"] = host
        captured["verification_token"] = verification_token
        return {
            "action": "verify",
            "creator_bid": creator_bid or None,
            "binding": {
                "domain_binding_bid": domain_binding_bid or None,
                "host": host or None,
            },
        }

    monkeypatch.setattr(
        "flaskr.service.billing.tasks.verify_domain_binding",
        _fake_verify_domain_binding,
    )

    payload = verify_domain_binding_task(
        creator_bid=" creator-task-4 ",
        domain_binding_bid=" binding-task-1 ",
        host=" verify.example.com ",
        verification_token=" token-task-1 ",
    )

    assert captured == {
        "app": fake_app,
        "creator_bid": "creator-task-4",
        "domain_binding_bid": "binding-task-1",
        "host": "verify.example.com",
        "verification_token": "token-task-1",
    }
    assert payload["action"] == "verify"
    assert payload["task_name"] == "billing.verify_domain_binding"


def test_settle_usage_task_serializes_same_creator_concurrent_usage(
    billing_task_integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ThreadLock:
        def __init__(
            self,
            *,
            key: str,
            raw_lock: threading.Lock,
            events: list[dict[str, object]],
            second_attempted: threading.Event,
        ) -> None:
            self._key = key
            self._raw_lock = raw_lock
            self._events = events
            self._second_attempted = second_attempted

        def acquire(self, blocking: bool = True, blocking_timeout=None):
            self._events.append(
                {
                    "type": "attempt",
                    "key": self._key,
                    "thread": threading.current_thread().name,
                    "at": time.monotonic(),
                }
            )
            if (
                len([event for event in self._events if event["type"] == "attempt"])
                >= 2
            ):
                self._second_attempted.set()
            if blocking_timeout is None:
                acquired = self._raw_lock.acquire(blocking)
            else:
                acquired = self._raw_lock.acquire(
                    blocking,
                    timeout=blocking_timeout,
                )
            if acquired:
                self._events.append(
                    {
                        "type": "acquired",
                        "key": self._key,
                        "thread": threading.current_thread().name,
                        "at": time.monotonic(),
                    }
                )
            return acquired

        def release(self) -> None:
            self._events.append(
                {
                    "type": "released",
                    "key": self._key,
                    "thread": threading.current_thread().name,
                    "at": time.monotonic(),
                }
            )
            self._raw_lock.release()

    class _ThreadLockCacheProvider:
        def __init__(self) -> None:
            self._locks: dict[str, threading.Lock] = {}
            self._guard = threading.Lock()
            self.events: list[dict[str, object]] = []
            self.second_attempted = threading.Event()

        def lock(self, key: str, timeout=None, blocking_timeout=None):
            del timeout, blocking_timeout
            with self._guard:
                raw_lock = self._locks.setdefault(key, threading.Lock())
            return _ThreadLock(
                key=key,
                raw_lock=raw_lock,
                events=self.events,
                second_attempted=self.second_attempted,
            )

    _install_fake_app_module(monkeypatch, billing_task_integration_app)
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-concurrent-1",
    )
    dummy_cache = _ThreadLockCacheProvider()
    monkeypatch.setattr("flaskr.service.billing.settlement.cache_provider", dummy_cache)

    entered_first_charge = threading.Event()
    release_first_charge = threading.Event()

    from flaskr.service.billing import settlement as settlement_module

    original_build_usage_metric_charges = settlement_module.build_usage_metric_charges

    def _blocking_build_usage_metric_charges(*args, **kwargs):
        usage = args[0]
        if usage.usage_bid == "usage-concurrent-1":
            entered_first_charge.set()
            assert release_first_charge.wait(timeout=2)
        return original_build_usage_metric_charges(*args, **kwargs)

    monkeypatch.setattr(
        settlement_module,
        "build_usage_metric_charges",
        _blocking_build_usage_metric_charges,
    )

    with billing_task_integration_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-concurrent-1",
            creator_bid="creator-concurrent-1",
            available_credits=Decimal("2.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("2.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        dao.db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid="bucket-concurrent-1",
                wallet_bid=wallet.wallet_bid,
                creator_bid="creator-concurrent-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
                source_type=0,
                source_bid="grant-concurrent-1",
                priority=10,
                original_credits=Decimal("2.0000000000"),
                available_credits=Decimal("2.0000000000"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("0"),
                expired_credits=Decimal("0"),
                effective_from=datetime(2026, 4, 8, 12, 0, 0),
                effective_to=None,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={},
                created_at=datetime(2026, 4, 8, 12, 0, 0),
                updated_at=datetime(2026, 4, 8, 12, 0, 0),
            )
        )
        dao.db.session.add(
            CreditUsageRate(
                rate_bid="rate-concurrent-1",
                usage_type=BILL_USAGE_TYPE_LLM,
                provider="openai",
                model="gpt-concurrent",
                usage_scene=BILL_USAGE_SCENE_PROD,
                billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                unit_size=1000,
                credits_per_unit=Decimal("1.0000000000"),
                rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
                effective_from=datetime(2026, 4, 8, 0, 0, 0),
                effective_to=None,
                status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
            )
        )
        dao.db.session.add_all(
            [
                BillUsageRecord(
                    usage_bid="usage-concurrent-1",
                    parent_usage_bid="",
                    user_bid="learner-concurrent-1",
                    shifu_bid="shifu-concurrent-1",
                    outline_item_bid="",
                    progress_record_bid="",
                    generated_block_bid="",
                    audio_bid="",
                    request_id="req-concurrent-1",
                    trace_id="trace-concurrent-1",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    record_level=0,
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    provider="openai",
                    model="gpt-concurrent",
                    is_stream=0,
                    input=1000,
                    input_cache=0,
                    output=0,
                    total=1000,
                    word_count=0,
                    duration_ms=1000,
                    latency_ms=100,
                    segment_index=0,
                    segment_count=0,
                    billable=1,
                    status=0,
                    error_message="",
                    extra={},
                    created_at=datetime(2026, 4, 8, 12, 1, 0),
                    updated_at=datetime(2026, 4, 8, 12, 1, 0),
                ),
                BillUsageRecord(
                    usage_bid="usage-concurrent-2",
                    parent_usage_bid="",
                    user_bid="learner-concurrent-2",
                    shifu_bid="shifu-concurrent-1",
                    outline_item_bid="",
                    progress_record_bid="",
                    generated_block_bid="",
                    audio_bid="",
                    request_id="req-concurrent-2",
                    trace_id="trace-concurrent-2",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    record_level=0,
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    provider="openai",
                    model="gpt-concurrent",
                    is_stream=0,
                    input=1000,
                    input_cache=0,
                    output=0,
                    total=1000,
                    word_count=0,
                    duration_ms=1000,
                    latency_ms=100,
                    segment_index=0,
                    segment_count=0,
                    billable=1,
                    status=0,
                    error_message="",
                    extra={},
                    created_at=datetime(2026, 4, 8, 12, 1, 1),
                    updated_at=datetime(2026, 4, 8, 12, 1, 1),
                ),
            ]
        )
        dao.db.session.commit()

    results: dict[str, dict[str, object]] = {}

    def _run_task(usage_bid: str) -> None:
        results[usage_bid] = settle_usage_task(
            creator_bid="creator-concurrent-1",
            usage_bid=usage_bid,
        )

    first = threading.Thread(
        target=_run_task,
        args=("usage-concurrent-1",),
        name="student-worker-1",
    )
    second = threading.Thread(
        target=_run_task,
        args=("usage-concurrent-2",),
        name="student-worker-2",
    )

    first.start()
    assert entered_first_charge.wait(timeout=2)
    second.start()
    assert dummy_cache.second_attempted.wait(timeout=2)
    time.sleep(0.05)
    release_first_charge.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()

    with billing_task_integration_app.app_context():
        wallet = CreditWallet.query.filter_by(creator_bid="creator-concurrent-1").one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-concurrent-1"
        ).one()
        entries = (
            CreditLedgerEntry.query.filter(
                CreditLedgerEntry.creator_bid == "creator-concurrent-1",
                CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_USAGE,
            )
            .order_by(CreditLedgerEntry.id.asc())
            .all()
        )

        assert results["usage-concurrent-1"]["status"] == "settled"
        assert results["usage-concurrent-2"]["status"] == "settled"
        assert len(entries) == 2
        assert [entry.source_bid for entry in entries] == [
            "usage-concurrent-1",
            "usage-concurrent-2",
        ]
        assert [entry.balance_after for entry in entries] == [
            Decimal("1.0000000000"),
            Decimal("0E-10"),
        ]
        assert wallet.available_credits == Decimal("0E-10")
        assert wallet.lifetime_consumed_credits == Decimal("2.0000000000")
        assert bucket.available_credits == Decimal("0E-10")
        assert bucket.status == CREDIT_BUCKET_STATUS_EXHAUSTED

    acquired_events = [
        event for event in dummy_cache.events if event["type"] == "acquired"
    ]
    released_events = [
        event for event in dummy_cache.events if event["type"] == "released"
    ]
    assert len(acquired_events) == 2
    assert len(released_events) == 2
    assert acquired_events[0]["thread"] == "student-worker-1"
    assert released_events[0]["thread"] == "student-worker-1"
    assert acquired_events[1]["thread"] == "student-worker-2"
    assert acquired_events[1]["at"] >= released_events[0]["at"]


def test_replay_usage_settlement_task_calls_replay_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = object()
    _install_fake_app_module(monkeypatch, fake_app)

    captured: dict[str, object] = {}

    def _fake_replay_bill_usage_settlement(
        app,
        *,
        creator_bid: str = "",
        usage_bid: str = "",
        usage_id=None,
    ):
        captured["app"] = app
        captured["creator_bid"] = creator_bid
        captured["usage_bid"] = usage_bid
        captured["usage_id"] = usage_id
        return {
            "status": "already_settled",
            "creator_bid": creator_bid,
            "usage_bid": usage_bid,
            "replay": True,
        }

    monkeypatch.setattr(
        "flaskr.service.billing.tasks.replay_bill_usage_settlement",
        _fake_replay_bill_usage_settlement,
    )

    payload = replay_usage_settlement_task(
        creator_bid="creator-task-2",
        usage_bid="usage-task-2",
    )

    assert captured == {
        "app": fake_app,
        "creator_bid": "creator-task-2",
        "usage_bid": "usage-task-2",
        "usage_id": None,
    }
    assert payload["status"] == "already_settled"
    assert payload["task_name"] == "billing.replay_usage_settlement"
    assert payload["replay"] is True


def test_expire_wallet_buckets_task_calls_wallet_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = Flask(__name__)
    _install_fake_app_module(monkeypatch, fake_app)

    captured: dict[str, object] = {}

    def _fake_expire_credit_wallet_buckets(app, *, creator_bid="", expire_before=None):
        captured["app"] = app
        captured["creator_bid"] = creator_bid
        captured["expire_before"] = expire_before
        return {"status": "expired", "bucket_count": 2}

    monkeypatch.setattr(
        "flaskr.service.billing.tasks.expire_credit_wallet_buckets",
        _fake_expire_credit_wallet_buckets,
    )

    payload = expire_wallet_buckets_task(
        creator_bid="creator-task-expire",
        expire_before="2026-04-08T12:34:56",
    )

    assert captured["app"] is fake_app
    assert captured["creator_bid"] == "creator-task-expire"
    assert captured["expire_before"] == datetime(2026, 4, 8, 12, 34, 56)
    assert payload["status"] == "expired"
    assert payload["task_name"] == "billing.expire_wallet_buckets"


def test_reconcile_provider_reference_task_delegates_to_reconcile_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = Flask(__name__)
    _install_fake_app_module(monkeypatch, fake_app)

    captured: dict[str, object] = {}

    def _fake_run_reconcile_provider_reference(
        app,
        *,
        creator_bid="",
        payment_provider="",
        provider_reference_id="",
        bill_order_bid="",
        session_id="",
    ):
        captured["app"] = app
        captured["creator_bid"] = creator_bid
        captured["payment_provider"] = payment_provider
        captured["provider_reference_id"] = provider_reference_id
        captured["bill_order_bid"] = bill_order_bid
        captured["session_id"] = session_id
        return {"status": "paid", "bill_order_bid": bill_order_bid}

    monkeypatch.setattr(
        "flaskr.service.billing.tasks._run_reconcile_provider_reference",
        _fake_run_reconcile_provider_reference,
    )

    payload = reconcile_provider_reference_task(
        creator_bid="creator-task-reconcile",
        payment_provider="stripe",
        provider_reference_id="cs_task_reconcile",
        bill_order_bid="bill-order-task-reconcile",
        session_id="cs_task_reconcile",
    )

    assert captured == {
        "app": fake_app,
        "creator_bid": "creator-task-reconcile",
        "payment_provider": "stripe",
        "provider_reference_id": "cs_task_reconcile",
        "bill_order_bid": "bill-order-task-reconcile",
        "session_id": "cs_task_reconcile",
    }
    assert payload["status"] == "paid"
    assert payload["task_name"] == "billing.reconcile_provider_reference"


def test_send_low_balance_alert_task_filters_to_low_balance_alerts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = Flask(__name__)
    _install_fake_app_module(monkeypatch, fake_app)
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.build_billing_overview",
        lambda app, creator_bid, timezone_name=None: {
            "creator_bid": creator_bid,
            "wallet": {"available_credits": "0E-10"},
            "billing_alerts": [
                {"code": "low_balance", "severity": "warning"},
                {"code": "subscription_past_due", "severity": "error"},
            ],
        },
    )

    payload = send_low_balance_alert_task(creator_bid="creator-task-alert")

    assert payload["status"] == "alerts_found"
    assert payload["creator_count"] == 1
    assert payload["alert_count"] == 1
    assert payload["creators"][0]["creator_bid"] == "creator-task-alert"
    assert payload["creators"][0]["alerts"] == [
        {"code": "low_balance", "severity": "warning"}
    ]
    assert payload["task_name"] == "billing.send_low_balance_alert"


def test_dispatch_due_renewal_events_task_noops_when_disabled(
    billing_task_integration_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_app_module(monkeypatch, billing_task_integration_app)
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.get_config",
        lambda key, default="": json.dumps(
            {
                "enabled": 0,
                "batch_size": 5,
                "lookahead_minutes": 60,
                "queue": "billing-renewal",
            }
        ),
    )

    called = {"apply_async": 0}

    def _fake_apply_async(*, kwargs=None, **options):
        del kwargs, options
        called["apply_async"] += 1

    monkeypatch.setattr(run_renewal_event_task, "apply_async", _fake_apply_async)

    payload = dispatch_due_renewal_events_task()

    assert payload == {
        "status": "noop_disabled",
        "candidate_count": 0,
        "enqueued_count": 0,
        "renewal_event_bids": [],
        "task_name": "billing.dispatch_due_renewal_events",
    }
    assert called["apply_async"] == 0


def test_dispatch_due_renewal_events_task_enqueues_due_pending_events_only(
    billing_task_integration_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_app_module(monkeypatch, billing_task_integration_app)
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.get_config",
        lambda key, default="": json.dumps(
            {
                "enabled": 1,
                "batch_size": 2,
                "lookahead_minutes": 60,
                "queue": "billing-renewal",
            }
        ),
    )

    now = datetime.now()
    with billing_task_integration_app.app_context():
        dao.db.session.add_all(
            [
                BillingRenewalEvent(
                    renewal_event_bid="renewal-due-1",
                    subscription_bid="subscription-due-1",
                    creator_bid="creator-due-1",
                    event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
                    scheduled_at=now - timedelta(minutes=5),
                    status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
                    attempt_count=0,
                    last_error="",
                    payload_json=None,
                    processed_at=None,
                ),
                BillingRenewalEvent(
                    renewal_event_bid="renewal-due-2",
                    subscription_bid="subscription-due-2",
                    creator_bid="creator-due-2",
                    event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
                    scheduled_at=now + timedelta(minutes=10),
                    status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
                    attempt_count=0,
                    last_error="",
                    payload_json=None,
                    processed_at=None,
                ),
                BillingRenewalEvent(
                    renewal_event_bid="renewal-due-3-over-batch",
                    subscription_bid="subscription-due-3",
                    creator_bid="creator-due-3",
                    event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
                    scheduled_at=now + timedelta(minutes=20),
                    status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
                    attempt_count=0,
                    last_error="",
                    payload_json=None,
                    processed_at=None,
                ),
                BillingRenewalEvent(
                    renewal_event_bid="renewal-future",
                    subscription_bid="subscription-future",
                    creator_bid="creator-future",
                    event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
                    scheduled_at=now + timedelta(minutes=61),
                    status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
                    attempt_count=0,
                    last_error="",
                    payload_json=None,
                    processed_at=None,
                ),
                BillingRenewalEvent(
                    renewal_event_bid="renewal-processing",
                    subscription_bid="subscription-processing",
                    creator_bid="creator-processing",
                    event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
                    scheduled_at=now - timedelta(minutes=1),
                    status=BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
                    attempt_count=1,
                    last_error="",
                    payload_json=None,
                    processed_at=None,
                ),
                BillingRenewalEvent(
                    renewal_event_bid="renewal-succeeded",
                    subscription_bid="subscription-succeeded",
                    creator_bid="creator-succeeded",
                    event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
                    scheduled_at=now - timedelta(minutes=1),
                    status=BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
                    attempt_count=1,
                    last_error="",
                    payload_json=None,
                    processed_at=now,
                ),
                BillingRenewalEvent(
                    renewal_event_bid="renewal-failed",
                    subscription_bid="subscription-failed",
                    creator_bid="creator-failed",
                    event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
                    scheduled_at=now - timedelta(minutes=1),
                    status=BILLING_RENEWAL_EVENT_STATUS_FAILED,
                    attempt_count=1,
                    last_error="boom",
                    payload_json=None,
                    processed_at=now,
                ),
                BillingRenewalEvent(
                    renewal_event_bid="renewal-canceled",
                    subscription_bid="subscription-canceled",
                    creator_bid="creator-canceled",
                    event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
                    scheduled_at=now - timedelta(minutes=1),
                    status=BILLING_RENEWAL_EVENT_STATUS_CANCELED,
                    attempt_count=0,
                    last_error="",
                    payload_json=None,
                    processed_at=now,
                ),
            ]
        )
        dao.db.session.commit()

    captured_calls: list[dict[str, object]] = []

    def _fake_apply_async(*, kwargs=None, **options):
        captured_calls.append(
            {
                "kwargs": dict(kwargs or {}),
                "options": dict(options),
            }
        )

    monkeypatch.setattr(run_renewal_event_task, "apply_async", _fake_apply_async)

    payload = dispatch_due_renewal_events_task()

    assert payload["status"] == "enqueued"
    assert payload["candidate_count"] == 2
    assert payload["enqueued_count"] == 2
    assert payload["renewal_event_bids"] == ["renewal-due-1", "renewal-due-2"]
    assert payload["task_name"] == "billing.dispatch_due_renewal_events"
    assert captured_calls == [
        {
            "kwargs": {
                "renewal_event_bid": "renewal-due-1",
                "subscription_bid": "subscription-due-1",
                "creator_bid": "creator-due-1",
            },
            "options": {},
        },
        {
            "kwargs": {
                "renewal_event_bid": "renewal-due-2",
                "subscription_bid": "subscription-due-2",
                "creator_bid": "creator-due-2",
            },
            "options": {},
        },
    ]


def test_billing_task_entrypoints_return_json_serializable_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = Flask(__name__)
    _install_fake_app_module(monkeypatch, fake_app)
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.settle_bill_usage",
        lambda app, *, usage_bid="": {
            "status": "settled",
            "usage_bid": usage_bid,
            "creator_bid": "creator-json-1",
        },
    )
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.expire_credit_wallet_buckets",
        lambda app, *, creator_bid="", expire_before=None: {
            "status": "expired",
            "creator_bid": creator_bid,
            "expire_before": expire_before.isoformat() if expire_before else None,
        },
    )
    monkeypatch.setattr(
        "flaskr.service.billing.tasks._run_reconcile_provider_reference",
        lambda app, **kwargs: {
            "status": "paid",
            "bill_order_bid": kwargs.get("bill_order_bid"),
        },
    )

    payloads = [
        settle_usage_task(creator_bid="creator-json-1", usage_bid="usage-json-1"),
        expire_wallet_buckets_task(
            creator_bid="creator-json-1",
            expire_before="2026-04-08T12:34:56",
        ),
        reconcile_provider_reference_task(
            creator_bid="creator-json-1",
            payment_provider="stripe",
            provider_reference_id="cs_json_1",
            bill_order_bid="bill-order-json-1",
            session_id="cs_json_1",
        ),
    ]

    for payload in payloads:
        json.dumps(payload)


def test_run_renewal_event_task_delegates_to_renewal_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = Flask(__name__)
    _install_fake_app_module(monkeypatch, fake_app)
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.run_billing_renewal_event",
        lambda app, **kwargs: {
            "status": "applied",
            "renewal_event_bid": kwargs["renewal_event_bid"],
            "event_status": "succeeded",
        },
    )

    payload = run_renewal_event_task(
        renewal_event_bid="renewal-task-1",
        subscription_bid="subscription-task-1",
        creator_bid="creator-task-1",
    )

    assert payload["status"] == "applied"
    assert payload["renewal_event_bid"] == "renewal-task-1"
    assert payload["event_status"] == "succeeded"
    assert payload["task_name"] == "billing.run_renewal_event"


def test_retry_failed_renewal_task_reuses_reconcile_helper_when_reference_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = Flask(__name__)
    _install_fake_app_module(monkeypatch, fake_app)

    captured: dict[str, object] = {}

    def _fake_run_reconcile_provider_reference(
        app,
        *,
        creator_bid="",
        payment_provider="",
        provider_reference_id="",
        bill_order_bid="",
        session_id="",
    ):
        captured["app"] = app
        captured["creator_bid"] = creator_bid
        captured["payment_provider"] = payment_provider
        captured["provider_reference_id"] = provider_reference_id
        captured["bill_order_bid"] = bill_order_bid
        captured["session_id"] = session_id
        return {"status": "paid", "bill_order_bid": bill_order_bid}

    monkeypatch.setattr(
        "flaskr.service.billing.tasks._run_reconcile_provider_reference",
        _fake_run_reconcile_provider_reference,
    )

    payload = retry_failed_renewal_task(
        renewal_event_bid="renewal-task-retry",
        bill_order_bid="bill-order-retry",
        provider_reference_id="cs_retry_task",
        payment_provider="stripe",
        creator_bid="creator-task-retry",
    )

    assert captured == {
        "app": fake_app,
        "creator_bid": "creator-task-retry",
        "payment_provider": "stripe",
        "provider_reference_id": "cs_retry_task",
        "bill_order_bid": "bill-order-retry",
        "session_id": "cs_retry_task",
    }
    assert payload["status"] == "paid"
    assert payload["renewal_event_bid"] == "renewal-task-retry"
    assert payload["task_name"] == "billing.retry_failed_renewal"


def test_retry_failed_renewal_task_delegates_to_renewal_helper_without_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = Flask(__name__)
    _install_fake_app_module(monkeypatch, fake_app)
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.retry_billing_renewal_event",
        lambda app, **kwargs: {
            "status": "paid",
            "bill_order_bid": "bill-order-task-retry-auto",
            "renewal_event_bid": kwargs["renewal_event_bid"],
        },
    )

    payload = retry_failed_renewal_task(
        renewal_event_bid="renewal-task-retry-auto",
        creator_bid="creator-task-retry-auto",
    )

    assert payload["status"] == "paid"
    assert payload["bill_order_bid"] == "bill-order-task-retry-auto"
    assert payload["renewal_event_bid"] == "renewal-task-retry-auto"
    assert payload["task_name"] == "billing.retry_failed_renewal"

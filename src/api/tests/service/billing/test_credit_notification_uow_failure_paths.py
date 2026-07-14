"""Mid-flow-failure tests for the credit notification uow migration (B4c).

Before the migration, ``billing/credit_notifications.py`` committed 20 times
mid-flow. These tests pin the new semantics:

- Batch scans stage each candidate in its own per-item transaction: one bad
  notification rolls back only its own row, is reported as ``stage_failed``,
  and never affects rows already staged for neighboring creators.
- Delivery is one unit of work whose terminal status flip is the send marker.
  Once the SENT flip commits, the row leaves the processable set, so a crash
  in later bookkeeping (task wrapper, serialization) cannot cause a second
  send — a re-run is a noop. The FAILED_PROVIDER flip persists the same way,
  keeping the celery autoretry path able to reprocess the row.
- The stage-then-enqueue flow dispatches through ``uow.on_commit``: nested in
  a failing outer unit of work the dispatch is dropped with the rollback; at
  top level it fires exactly once, after the staged row is durable.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import os
import secrets
from types import SimpleNamespace

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.dao import uow
from flaskr.i18n import load_translations
from flaskr.service.billing import credit_notifications
from flaskr.service.billing.consts import (
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
    CREDIT_NOTIFICATION_STATUS_PENDING,
    CREDIT_NOTIFICATION_STATUS_SENT,
    CREDIT_NOTIFICATION_TYPE_EXPIRING,
    CREDIT_NOTIFICATION_TYPE_GRANTED,
    CREDIT_NOTIFICATION_TYPE_LOW_BALANCE,
    CREDIT_SOURCE_TYPE_MANUAL,
)
from flaskr.service.billing.credit_notifications import (
    deliver_credit_notification,
    save_credit_notification_policy,
    scan_low_balance_notifications,
    stage_credit_granted_notification,
)
from flaskr.service.billing.models import (
    CreditLedgerEntry,
    CreditWallet,
    NotificationRecord,
    NotificationTemplate,
)
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.repository import (
    create_user_entity,
    mark_user_roles,
    upsert_credential,
)


@pytest.fixture
def credit_notification_uow_app(tmp_path) -> Flask:
    db_path = tmp_path / "credit-notification-uow.sqlite"
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
        REDIS_KEY_PREFIX="credit-notification-uow-test:",
        SECRET_KEY=os.environ.get(
            "CREDIT_NOTIFICATION_TEST_SECRET_KEY", secrets.token_urlsafe(24)
        ),
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        load_translations(app)
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


@pytest.fixture(autouse=True)
def _neutralize_savepoints_on_sqlite(monkeypatch):
    """Make begin_nested a no-op under the SQLite test engine.

    ``_stage_notification_record`` wraps its INSERT in
    ``db.session.begin_nested()`` to capture duplicate-key IntegrityErrors on
    MySQL. pysqlite emits BEGIN lazily, so that SAVEPOINT can run outside a
    transaction and auto-commit the row — which would silently defeat the
    unit-of-work rollback these tests exist to assert. The rollback property
    under test belongs to ``unit_of_work()``, not to the savepoint, so the
    savepoint is neutralized here; the dedupe IntegrityError path keeps its
    own coverage in the main credit-notification suite.
    """
    from contextlib import nullcontext

    from sqlalchemy.orm import Session

    monkeypatch.setattr(Session, "begin_nested", lambda self: nullcontext())


def _seed_creator(
    app: Flask,
    *,
    creator_bid: str,
    mobile: str,
) -> None:
    # Runs inside the fixture's app context on purpose: a nested
    # app.app_context() would open a SECOND session/connection on the same
    # SQLite file and its writes could contend with the fixture session.
    create_user_entity(
        user_bid=creator_bid,
        identify=mobile,
        nickname=f"Creator {creator_bid}",
        state=USER_STATE_REGISTERED,
    )
    mark_user_roles(creator_bid, is_creator=True)
    upsert_credential(
        app,
        user_bid=creator_bid,
        provider_name="phone",
        subject_id=mobile,
        subject_format="phone",
        identifier=mobile,
        metadata={},
        verified=True,
    )
    dao.db.session.commit()


def _seed_notification_template(
    *,
    template_code: str,
    placeholders: list[str],
) -> None:
    template = NotificationTemplate(
        notification_template_bid=f"tpl-{template_code}"[:36],
        channel="sms",
        provider="aliyun",
        template_code=template_code,
        deleted=0,
        template_name=f"Template {template_code}",
        template_content=" ".join(f"${{{item}}}" for item in placeholders),
        template_status="AUDIT_STATE_PASS",
        template_type="0",
        variable_attribute_json={},
        provider_response_json={"code": "OK"},
        placeholders_json=placeholders,
        sync_status="synced",
        error_code="",
        error_message="",
        last_synced_at=datetime(2026, 5, 22, 0, 0, 0),
        metadata_json={},
    )
    dao.db.session.add(template)
    dao.db.session.commit()


def _enable_policy(app: Flask) -> None:
    _seed_notification_template(
        template_code="TPL-GRANT",
        placeholders=["credits", "source", "expires_at"],
    )
    _seed_notification_template(
        template_code="TPL-EXPIRING",
        placeholders=["credits", "expires_at", "window"],
    )
    _seed_notification_template(
        template_code="TPL-LOW",
        placeholders=["available_credits"],
    )
    save_credit_notification_policy(
        app,
        {
            "enabled": True,
            "types": {
                CREDIT_NOTIFICATION_TYPE_GRANTED: {
                    "enabled": True,
                    "template_code": "TPL-GRANT",
                },
                CREDIT_NOTIFICATION_TYPE_EXPIRING: {
                    "enabled": True,
                    "template_code": "TPL-EXPIRING",
                    "windows": ["7d", "3d", "1d", "0d"],
                },
                CREDIT_NOTIFICATION_TYPE_LOW_BALANCE: {
                    "enabled": True,
                    "template_code": "TPL-LOW",
                    "thresholds": [{"kind": "fixed", "value": "3"}],
                },
            },
            "frequency": {
                "per_mobile_per_day": 0,
                "per_creator_per_type_per_day": 0,
            },
            "softlimit": {
                "enabled": False,
                "threshold": {"kind": "fixed", "value": "0"},
                "disable_debug": True,
            },
            "blacklist": {"creator_bids": [], "mobiles": []},
            "opt_out": {"creator_bids": [], "mobiles": []},
        },
    )


def _seed_wallet(*, creator_bid: str, available_credits: str = "2") -> None:
    dao.db.session.add(
        CreditWallet(
            wallet_bid=f"wallet-{creator_bid}",
            creator_bid=creator_bid,
            available_credits=Decimal(available_credits),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal(available_credits),
            lifetime_consumed_credits=Decimal("0"),
        )
    )
    dao.db.session.commit()


def _seed_credit_ledger(*, ledger_bid: str, creator_bid: str) -> None:
    dao.db.session.add(
        CreditLedgerEntry(
            ledger_bid=ledger_bid,
            creator_bid=creator_bid,
            wallet_bid=f"wallet-{creator_bid}",
            wallet_bucket_bid=f"bucket-{creator_bid}",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid=f"manual-{ledger_bid}",
            idempotency_key=f"grant:{ledger_bid}",
            amount=Decimal("12.5"),
            balance_after=Decimal("12.5"),
            expires_at=datetime(2026, 6, 30, 0, 0, 0),
            metadata_json={"grant_source": "operator"},
        )
    )
    dao.db.session.commit()


def _stub_send_sms(monkeypatch: pytest.MonkeyPatch, sends: list[dict]):
    def fake_send(app, mobile, *, template_code, template_params, sign_name=None):
        sends.append(
            {
                "mobile": mobile,
                "template_code": template_code,
                "template_params": dict(template_params),
            }
        )
        return SimpleNamespace(
            body=SimpleNamespace(
                code="OK",
                message="accepted",
                request_id="req-uow",
                biz_id="biz-uow",
            )
        )

    monkeypatch.setattr(credit_notifications, "send_sms_ali", fake_send)


def test_scan_item_failure_is_isolated_from_neighbor_items(
    credit_notification_uow_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-item scan isolation: item 2 of 3 fails; items 1 and 3 persist.

    The failing item raises AFTER its row was staged, so the test also pins
    that the per-item transaction rolls the partial row back instead of
    leaking it, while neighboring items keep their own committed rows.
    """
    app = credit_notification_uow_app
    for index in (1, 2, 3):
        _seed_creator(
            app,
            creator_bid=f"creator-uow-{index}",
            mobile=f"1380000000{index}",
        )
        _seed_wallet(creator_bid=f"creator-uow-{index}", available_credits="2")
    _enable_policy(app)

    original_stage = credit_notifications._stage_notification_record

    def staging_then_boom(app_arg, **kwargs):
        result = original_stage(app_arg, **kwargs)
        if kwargs.get("creator_bid") == "creator-uow-2":
            raise RuntimeError("boom in creator-uow-2")
        return result

    monkeypatch.setattr(
        credit_notifications, "_stage_notification_record", staging_then_boom
    )
    enqueued: list[str] = []
    monkeypatch.setattr(
        credit_notifications,
        "enqueue_credit_notification",
        lambda _app, *, notification_bid: (
            enqueued.append(notification_bid) or {"enqueued": True}
        ),
    )

    payload = scan_low_balance_notifications(app)

    statuses = {
        item["creator_bid"]: item["status"] for item in payload["notifications"]
    }
    assert statuses["creator-uow-1"] == CREDIT_NOTIFICATION_STATUS_PENDING
    assert statuses["creator-uow-2"] == "stage_failed"
    assert statuses["creator-uow-3"] == CREDIT_NOTIFICATION_STATUS_PENDING
    assert payload["created_count"] == 2
    assert payload["enqueued_count"] == 2
    assert len(enqueued) == 2

    dao.db.session.expire_all()
    persisted = {
        record.creator_bid
        for record in NotificationRecord.query.filter(
            NotificationRecord.notification_type == CREDIT_NOTIFICATION_TYPE_LOW_BALANCE
        ).all()
    }
    # The failed item's partial row rolled back; its neighbors' rows are
    # durable because each item committed in its own transaction.
    assert persisted == {"creator-uow-1", "creator-uow-3"}


def test_sent_marker_survives_post_delivery_crash_no_double_send(
    credit_notification_uow_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No-double-send: the SENT flip commits with the delivery attempt.

    A crash in post-delivery bookkeeping (simulated by a session rollback
    right after the call returns, as a failing task wrapper would produce)
    cannot take the marker back, and a re-run is a noop with no second send.
    """
    app = credit_notification_uow_app
    _seed_creator(app, creator_bid="creator-uow-send", mobile="13800009001")
    _enable_policy(app)
    _seed_credit_ledger(ledger_bid="ledger-uow-send", creator_bid="creator-uow-send")

    staged = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-uow-send",
        enqueue=False,
    )
    assert staged["status"] == CREDIT_NOTIFICATION_STATUS_PENDING
    notification_bid = str(staged["notification_bid"])

    sends: list[dict] = []
    _stub_send_sms(monkeypatch, sends)

    delivered = deliver_credit_notification(app, notification_bid=notification_bid)
    assert delivered["status"] == CREDIT_NOTIFICATION_STATUS_SENT
    assert len(sends) == 1

    # Simulated wrapper crash after delivery: the rollback finds nothing to
    # undo because the SENT flip already committed inside the delivery uow.
    dao.db.session.rollback()
    dao.db.session.expire_all()
    record = NotificationRecord.query.filter_by(notification_bid=notification_bid).one()
    assert record.status == CREDIT_NOTIFICATION_STATUS_SENT

    retried = deliver_credit_notification(app, notification_bid=notification_bid)
    assert retried["status"] == "noop"
    assert retried["notification_status"] == CREDIT_NOTIFICATION_STATUS_SENT
    assert len(sends) == 1  # no second SMS


def test_failed_provider_marker_persists_and_stays_retryable(
    credit_notification_uow_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The FAILED_PROVIDER flip persists so the autoretry path can rerun.

    The failure-path status flip is committed by the delivery unit of work
    even though the provider call raised, and a later attempt (the celery
    autoretry) still finds the row processable and completes the send.
    """
    app = credit_notification_uow_app
    _seed_creator(app, creator_bid="creator-uow-retry", mobile="13800009002")
    _enable_policy(app)
    _seed_credit_ledger(ledger_bid="ledger-uow-retry", creator_bid="creator-uow-retry")

    staged = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-uow-retry",
        enqueue=False,
    )
    notification_bid = str(staged["notification_bid"])

    def crashing_send(*_args, **_kwargs):
        raise RuntimeError("provider connection dropped")

    monkeypatch.setattr(credit_notifications, "send_sms_ali", crashing_send)
    failed = deliver_credit_notification(app, notification_bid=notification_bid)
    assert failed["status"] == CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER

    dao.db.session.expire_all()
    record = NotificationRecord.query.filter_by(notification_bid=notification_bid).one()
    assert record.status == CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER
    assert record.error_code == "provider_exception"

    sends: list[dict] = []
    _stub_send_sms(monkeypatch, sends)
    retried = deliver_credit_notification(app, notification_bid=notification_bid)
    assert retried["status"] == CREDIT_NOTIFICATION_STATUS_SENT
    assert len(sends) == 1


def test_granted_dispatch_fires_after_commit_and_drops_on_rollback(
    credit_notification_uow_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stage-then-enqueue dispatch obeys uow.on_commit semantics.

    Nested in a failing outer unit of work, the celery dispatch is dropped
    with the rollback (and the staged row disappears); at top level it fires
    exactly once, after the staged row is durable.
    """
    app = credit_notification_uow_app
    _seed_creator(app, creator_bid="creator-uow-dispatch", mobile="13800009003")
    _enable_policy(app)
    _seed_credit_ledger(
        ledger_bid="ledger-uow-dispatch", creator_bid="creator-uow-dispatch"
    )

    enqueued: list[str] = []
    monkeypatch.setattr(
        credit_notifications,
        "enqueue_credit_notification",
        lambda _app, *, notification_bid: (
            enqueued.append(notification_bid) or {"enqueued": True}
        ),
    )

    # Nested: the outer failure drops the deferred dispatch — the legacy code
    # committed and enqueued mid-flow and could never be taken back.
    with pytest.raises(RuntimeError, match="outer boom"):
        with uow.unit_of_work():
            staged = stage_credit_granted_notification(
                app,
                ledger_bid="ledger-uow-dispatch",
                commit=True,
                enqueue=True,
            )
            assert staged["status"] == CREDIT_NOTIFICATION_STATUS_PENDING
            assert enqueued == []  # not yet durable, must not dispatch
            raise RuntimeError("outer boom")
    dao.db.session.expire_all()
    assert enqueued == []
    assert (
        NotificationRecord.query.filter_by(creator_bid="creator-uow-dispatch").count()
        == 0
    )

    # Top level: the dispatch fires exactly once, after the commit, and the
    # payload reports the real enqueue outcome.
    payload = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-uow-dispatch",
        commit=True,
        enqueue=True,
    )
    assert payload["status"] == CREDIT_NOTIFICATION_STATUS_PENDING
    assert payload["enqueued"] is True
    assert enqueued == [payload["notification_bid"]]
    dao.db.session.expire_all()
    record = NotificationRecord.query.filter_by(
        creator_bid="creator-uow-dispatch"
    ).one()
    assert record.status == CREDIT_NOTIFICATION_STATUS_PENDING

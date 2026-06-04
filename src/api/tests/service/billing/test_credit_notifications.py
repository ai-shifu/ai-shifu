from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import os
import secrets
import sys
import time as time_module
from types import SimpleNamespace

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.i18n import load_translations
from flaskr.service.billing.consts import (
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
    CREDIT_NOTIFICATION_STATUS_PENDING,
    CREDIT_NOTIFICATION_STATUS_SENT,
    CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE,
    CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT,
    CREDIT_NOTIFICATION_STATUS_SUPPRESSED_DUPLICATE,
    CREDIT_NOTIFICATION_TYPE_EXPIRING,
    CREDIT_NOTIFICATION_TYPE_GRANTED,
    CREDIT_NOTIFICATION_TYPE_LOW_BALANCE,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.credit_notifications import (
    _is_quiet_hours,
    assert_creator_debug_allowed,
    deliver_credit_notification,
    get_credit_notification_detail,
    list_credit_notification_templates,
    list_credit_notifications,
    load_credit_notification_policy_for_operator,
    requeue_credit_notification,
    resolve_creator_limit_state,
    save_credit_notification_policy,
    scan_credit_expiring_notifications,
    scan_low_balance_notifications,
    stage_credit_granted_notification,
    sync_credit_notification_template,
)
from flaskr.service.billing.models import (
    BillingDailyLedgerSummary,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
    NotificationRecord,
    NotificationTemplate,
)
from flaskr.service.billing.tasks import (
    CreditNotificationRetryableError,
    send_credit_notification_task,
)
from flaskr.service.common.models import AppException
from flaskr.service.config.models import Config
from flaskr.service.user.consts import USER_STATE_REGISTERED, USER_STATE_UNREGISTERED
from flaskr.service.user.repository import (
    create_user_entity,
    mark_user_roles,
    upsert_credential,
)


@pytest.fixture
def credit_notifications_app(tmp_path):
    db_path = tmp_path / "credit-notifications.sqlite"
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
        REDIS_KEY_PREFIX="credit-notification-test:",
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


def _seed_creator(
    app: Flask,
    *,
    creator_bid: str = "creator-1",
    mobile: str | None = "13800000000",
    nickname: str = "Creator",
    state: int = USER_STATE_REGISTERED,
    is_creator: bool = True,
) -> None:
    identify = mobile or creator_bid
    with app.app_context():
        create_user_entity(
            user_bid=creator_bid,
            identify=identify,
            nickname=nickname,
            state=state,
        )
        if is_creator:
            mark_user_roles(creator_bid, is_creator=True)
        if mobile:
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


def _enable_policy(
    app: Flask,
    *,
    softlimit: dict | None = None,
    low_balance_thresholds: list[dict[str, object]] | None = None,
    blacklist: dict | None = None,
    opt_out: dict | None = None,
) -> None:
    _seed_default_notification_templates(app)
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
                    "thresholds": low_balance_thresholds
                    or [{"kind": "fixed", "value": "3"}],
                },
            },
            "frequency": {
                "per_mobile_per_day": 0,
                "per_creator_per_type_per_day": 0,
            },
            "softlimit": softlimit
            or {
                "enabled": False,
                "threshold": {"kind": "fixed", "value": "0"},
                "disable_debug": True,
            },
            "blacklist": blacklist or {"creator_bids": [], "mobiles": []},
            "opt_out": opt_out or {"creator_bids": [], "mobiles": []},
        },
    )


def _seed_credit_ledger(
    *,
    ledger_bid: str = "ledger-1",
    creator_bid: str = "creator-1",
    amount: str = "12.5",
) -> None:
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
            amount=Decimal(amount),
            balance_after=Decimal(amount),
            expires_at=datetime(2026, 6, 30, 0, 0, 0),
            metadata_json={"grant_source": "operator"},
        )
    )
    dao.db.session.commit()


def _seed_wallet(
    *,
    creator_bid: str = "creator-1",
    available_credits: str = "2",
) -> None:
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


def _seed_bucket(
    *,
    creator_bid: str = "creator-1",
    effective_to: datetime,
    available_credits: str = "5",
    wallet_bucket_bid: str | None = None,
) -> None:
    resolved_wallet_bucket_bid = wallet_bucket_bid or f"bucket-{creator_bid}"
    dao.db.session.add(
        CreditWalletBucket(
            wallet_bucket_bid=resolved_wallet_bucket_bid,
            wallet_bid=f"wallet-{creator_bid}",
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid=f"source-{resolved_wallet_bucket_bid}",
            priority=10,
            original_credits=Decimal(available_credits),
            available_credits=Decimal(available_credits),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 5, 1, 0, 0, 0),
            effective_to=effective_to,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
    )


def _seed_daily_consumption(
    *,
    creator_bid: str = "creator-1",
    stat_date: str,
    amount: str,
) -> None:
    window_started_at = datetime.fromisoformat(f"{stat_date}T00:00:00")
    dao.db.session.add(
        BillingDailyLedgerSummary(
            daily_ledger_summary_bid=f"daily-ledger-{creator_bid}-{stat_date}",
            stat_date=stat_date,
            creator_bid=creator_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            amount=Decimal(amount),
            entry_count=1,
            window_started_at=window_started_at,
            window_ended_at=window_started_at + timedelta(days=1),
        )
    )


def _seed_notification_template(
    app: Flask,
    *,
    template_code: str,
    placeholders: list[str] | None = None,
    template_content: str | None = None,
    sync_status: str = "synced",
) -> None:
    resolved_placeholders = placeholders or []
    resolved_content = template_content
    if resolved_content is None:
        resolved_content = " ".join(f"${{{item}}}" for item in resolved_placeholders)
    with app.app_context():
        existing = NotificationTemplate.query.filter_by(
            channel="sms",
            provider="aliyun",
            template_code=template_code,
            deleted=0,
        ).first()
        if existing is None:
            existing = NotificationTemplate(
                notification_template_bid=f"tpl-{template_code}"[:36],
                channel="sms",
                provider="aliyun",
                template_code=template_code,
                deleted=0,
            )
        existing.template_name = f"Template {template_code}"
        existing.template_content = resolved_content
        existing.template_status = "AUDIT_STATE_PASS"
        existing.template_type = "0"
        existing.variable_attribute_json = {}
        existing.provider_response_json = {"code": "OK"}
        existing.placeholders_json = resolved_placeholders
        existing.sync_status = sync_status
        existing.error_code = ""
        existing.error_message = ""
        existing.last_synced_at = datetime(2026, 5, 22, 0, 0, 0)
        existing.metadata_json = {}
        dao.db.session.add(existing)
        dao.db.session.commit()


def _seed_default_notification_templates(app: Flask) -> None:
    _seed_notification_template(
        app,
        template_code="TPL-GRANT",
        placeholders=["credits", "source", "expires_at"],
    )
    _seed_notification_template(
        app,
        template_code="TPL-EXPIRING",
        placeholders=["credits", "expires_at", "window"],
    )
    _seed_notification_template(
        app,
        template_code="TPL-LOW",
        placeholders=["available_credits"],
    )


def test_credit_granted_notification_stages_once_and_delivers_sms(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    _seed_creator(app)
    _enable_policy(app)
    captured: list[dict[str, object]] = []

    with app.app_context():
        _seed_credit_ledger()

    first = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-1",
        enqueue=False,
    )
    second = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-1",
        enqueue=False,
    )

    assert first["status"] == CREDIT_NOTIFICATION_STATUS_PENDING
    assert second["status"] == "suppressed_duplicate"

    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.send_sms_ali",
        lambda app, mobile, *, template_code, template_params, sign_name=None: (
            captured.append(
                {
                    "mobile": mobile,
                    "template_code": template_code,
                    "template_params": dict(template_params),
                }
            )
            or SimpleNamespace(
                body=SimpleNamespace(
                    code="OK",
                    message="accepted",
                    request_id="req-1",
                    biz_id="biz-1",
                )
            )
        ),
    )

    delivered = deliver_credit_notification(
        app,
        notification_bid=str(first["notification_bid"]),
    )

    assert delivered["status"] == CREDIT_NOTIFICATION_STATUS_SENT
    assert captured == [
        {
            "mobile": "13800000000",
            "template_code": "TPL-GRANT",
            "template_params": {
                "credits": "12.50",
                "expires_at": "2026-06-30 00:00:00",
                "source": "operator",
            },
        }
    ]
    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_bid=first["notification_bid"]
        ).one()
        assert notification.status == CREDIT_NOTIFICATION_STATUS_SENT
        assert notification.mobile_snapshot == "13800000000"


def test_credit_notification_policy_blocks_creator_by_email_identifier(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    _seed_creator(app)
    with app.app_context():
        upsert_credential(
            app,
            user_bid="creator-1",
            provider_name="email",
            subject_id="creator@example.com",
            subject_format="email",
            identifier="creator@example.com",
            metadata={},
            verified=True,
        )
        dao.db.session.commit()
    _enable_policy(
        app,
        blacklist={"creator_bids": ["creator@example.com"], "mobiles": []},
    )
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.send_sms_ali",
        lambda *args, **kwargs: pytest.fail("blocked notification should not send"),
    )
    with app.app_context():
        _seed_credit_ledger()

    staged = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-1",
        enqueue=False,
    )
    delivered = deliver_credit_notification(
        app,
        notification_bid=str(staged["notification_bid"]),
    )

    assert delivered["status"] == CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT
    assert delivered["reason"] == "blacklisted"
    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_bid=staged["notification_bid"]
        ).one()
        assert notification.error_code == "blacklisted"


def test_credit_notification_delivery_normalizes_legacy_iso_expires_at(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    _seed_creator(app)
    _enable_policy(app)
    captured: list[dict[str, object]] = []

    with app.app_context():
        _seed_credit_ledger()

    staged = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-1",
        enqueue=False,
    )
    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_bid=staged["notification_bid"]
        ).one()
        notification.template_params_json = {
            "credits": "12.50",
            "expires_at": "2026-06-30T00:00:00+00:00",
            "source": "operator",
        }
        dao.db.session.commit()

    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.send_sms_ali",
        lambda app, mobile, *, template_code, template_params, sign_name=None: (
            captured.append(dict(template_params))
            or SimpleNamespace(
                body=SimpleNamespace(
                    code="OK",
                    message="accepted",
                    request_id="req-legacy",
                    biz_id="biz-legacy",
                )
            )
        ),
    )

    delivered = deliver_credit_notification(
        app,
        notification_bid=str(staged["notification_bid"]),
    )

    assert delivered["status"] == CREDIT_NOTIFICATION_STATUS_SENT
    assert captured == [
        {
            "credits": "12.50",
            "expires_at": "2026-06-30 00:00:00",
            "source": "operator",
        }
    ]
    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_bid=staged["notification_bid"]
        ).one()
        assert notification.template_params_json["expires_at"] == (
            "2026-06-30 00:00:00"
        )


def test_credit_notification_policy_rejects_invalid_windows(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app

    with pytest.raises(AppException):
        save_credit_notification_policy(
            app,
            {
                "enabled": True,
                "types": {
                    CREDIT_NOTIFICATION_TYPE_EXPIRING: {
                        "enabled": True,
                        "template_code": "TPL-EXPIRING",
                        "windows": ["soon"],
                    }
                },
            },
        )


def test_credit_notification_policy_accepts_estimated_days_threshold(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    _seed_notification_template(
        app,
        template_code="TPL-LOW",
        placeholders=["available_credits"],
    )

    policy = save_credit_notification_policy(
        app,
        {
            "enabled": True,
            "types": {
                CREDIT_NOTIFICATION_TYPE_LOW_BALANCE: {
                    "enabled": True,
                    "template_code": "TPL-LOW",
                    "thresholds": [
                        {
                            "kind": "estimated_days",
                            "days": 7,
                            "lookback_days": 7,
                            "min_consumed_days": 2,
                            "fallback_fixed_value": "0",
                        }
                    ],
                }
            },
        },
    )

    assert policy["types"][CREDIT_NOTIFICATION_TYPE_LOW_BALANCE]["thresholds"] == [
        {
            "kind": "estimated_days",
            "days": 7,
            "lookback_days": 7,
            "min_consumed_days": 2,
            "fallback_fixed_value": "0.00",
        }
    ]


def test_credit_notification_policy_can_preserve_opt_out_list(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app

    save_credit_notification_policy(
        app,
        {
            "enabled": False,
            "opt_out": {
                "creator_bids": ["creator-opted-out"],
                "mobiles": ["13800000000"],
            },
        },
    )

    policy = save_credit_notification_policy(
        app,
        {
            "enabled": False,
            "blacklist": {
                "creator_bids": ["creator-blocked"],
                "mobiles": ["13900000000"],
            },
            "opt_out": {
                "creator_bids": ["should-not-save"],
                "mobiles": ["13700000000"],
            },
        },
        preserve_opt_out=True,
    )

    assert policy["blacklist"] == {
        "creator_bids": ["creator-blocked"],
        "mobiles": ["13900000000"],
    }
    assert policy["opt_out"] == {
        "creator_bids": ["creator-opted-out"],
        "mobiles": ["13800000000"],
    }


def test_credit_notification_policy_persists_operator_updated_by(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app

    save_credit_notification_policy(
        app,
        {"enabled": False},
        updated_by="operator-audit-1",
    )

    with app.app_context():
        config = (
            Config.query.filter(
                Config.key == "BILL_CREDIT_NOTIFICATION_SMS_CONFIG",
                Config.deleted == 0,
            )
            .order_by(Config.id.desc())
            .first()
        )
        assert config is not None
        assert config.updated_by == "operator-audit-1"


def test_credit_notification_policy_truncates_operator_updated_by(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    updated_by = "operator-audit-" + ("x" * 40)

    save_credit_notification_policy(
        app,
        {"enabled": False},
        updated_by=updated_by,
    )

    with app.app_context():
        config = (
            Config.query.filter(
                Config.key == "BILL_CREDIT_NOTIFICATION_SMS_CONFIG",
                Config.deleted == 0,
            )
            .order_by(Config.id.desc())
            .first()
        )
        assert config is not None
        assert config.updated_by == updated_by[:36]


def test_credit_notification_policy_resolves_list_creator_details(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    _seed_creator(app, creator_bid="creator-detail", nickname="Detail Creator")

    save_credit_notification_policy(
        app,
        {
            "enabled": False,
            "blacklist": {
                "creator_bids": [],
                "mobiles": ["13800000000"],
            },
        },
    )

    policy = load_credit_notification_policy_for_operator()

    assert policy["resolved_lists"]["blacklist"]["items"] == [
        {
            "identifier": "13800000000",
            "creator_bid": "creator-detail",
            "mobile": "13800000000",
            "email": "",
            "nickname": "Detail Creator",
        }
    ]


def test_sync_credit_notification_template_persists_aliyun_template(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID=os.environ.get(
            "ALIBABA_CLOUD_SMS_ACCESS_KEY_ID", f"test-key-{secrets.token_hex(4)}"
        ),
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET=os.environ.get(
            "ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET", secrets.token_urlsafe(24)
        ),
    )

    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.get_sms_template_ali",
        lambda app, *, template_code: SimpleNamespace(
            body=SimpleNamespace(
                code="OK",
                message="OK",
                request_id="req-template-1",
                template_code=template_code,
                template_name="Low balance",
                template_content=(
                    "Available ${available_credits}, unknown ${bad_variable}"
                ),
                template_status="AUDIT_STATE_PASS",
                template_type="0",
                variable_attribute={"available_credits": "credits"},
            )
        ),
    )

    payload = sync_credit_notification_template(
        app,
        notification_type=CREDIT_NOTIFICATION_TYPE_LOW_BALANCE,
        template_code="TPL-LOW-SYNC",
    )

    assert payload["sync_status"] == "synced"
    assert payload["placeholders"] == ["available_credits", "bad_variable"]
    assert payload["unsupported_placeholders"] == ["bad_variable"]
    assert payload["compatible"] is False
    assert payload["last_synced_at"].endswith("Z")
    with app.app_context():
        template = NotificationTemplate.query.filter_by(
            template_code="TPL-LOW-SYNC"
        ).one()
        assert template.template_content == (
            "Available ${available_credits}, unknown ${bad_variable}"
        )
        assert template.placeholders_json == ["available_credits", "bad_variable"]


def test_sync_credit_notification_template_reports_missing_credentials(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app

    payload = sync_credit_notification_template(
        app,
        notification_type=CREDIT_NOTIFICATION_TYPE_GRANTED,
        template_code="TPL-NO-CREDS",
    )

    assert payload["sync_status"] == "missing_credentials"
    assert payload["error_code"] == "missing_credentials"
    assert payload["compatible"] is False


def test_list_credit_notification_templates_falls_back_to_local_cache(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    _seed_notification_template(
        app,
        template_code="TPL-CACHED",
        placeholders=["credits"],
    )

    payload = list_credit_notification_templates(app)

    assert payload["source"] == "local"
    assert payload["provider_available"] is False
    assert payload["error_code"] == "missing_credentials"
    assert [item["template_code"] for item in payload["items"]] == ["TPL-CACHED"]
    assert payload["items"][0]["source"] == "local"
    assert payload["items"][0]["last_synced_at"] == "2026-05-22T00:00:00Z"


def test_list_credit_notification_templates_syncs_provider_list(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID=f"test-key-{secrets.token_hex(4)}",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET=secrets.token_urlsafe(24),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.query_sms_template_list_ali",
        lambda app, *, page_index, page_size: SimpleNamespace(
            body=SimpleNamespace(
                code="OK",
                message="OK",
                request_id="req-list-1",
                sms_template_list=[
                    SimpleNamespace(
                        template_code="TPL-PROVIDER",
                        template_name="Provider Template",
                        template_content="Credits ${credits}",
                        audit_status="AUDIT_STATE_PASS",
                        template_type="0",
                        create_date="2026-05-22 00:00:00",
                        order_id="order-1",
                        reason={},
                    )
                ],
            )
        ),
    )

    payload = list_credit_notification_templates(app)

    assert payload["source"] == "provider"
    assert payload["provider_available"] is True
    assert payload["items"][0]["template_code"] == "TPL-PROVIDER"
    assert payload["items"][0]["source"] == "provider"
    assert payload["items"][0]["last_synced_at"].endswith("Z")
    with app.app_context():
        template = NotificationTemplate.query.filter_by(
            template_code="TPL-PROVIDER"
        ).one()
        assert template.template_name == "Provider Template"
        assert template.placeholders_json == ["credits"]


def test_sync_credit_notification_template_records_provider_exception(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID=os.environ.get(
            "ALIBABA_CLOUD_SMS_ACCESS_KEY_ID", f"test-key-{secrets.token_hex(4)}"
        ),
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET=os.environ.get(
            "ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET", secrets.token_urlsafe(24)
        ),
    )

    def raise_provider_error(app: Flask, *, template_code: str) -> None:
        raise RuntimeError("provider down")

    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.get_sms_template_ali",
        raise_provider_error,
    )

    payload = sync_credit_notification_template(
        app,
        notification_type=CREDIT_NOTIFICATION_TYPE_GRANTED,
        template_code="TPL-RAISE",
    )

    assert payload["sync_status"] == "failed_provider"
    assert payload["error_code"] == "provider_exception"
    assert payload["error_message"] == "provider_exception"
    assert payload["compatible"] is False


def test_credit_notification_policy_allows_synced_template_missing_variables(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    _seed_notification_template(
        app,
        template_code="TPL-GRANT-PARTIAL",
        placeholders=["credits"],
    )

    policy = save_credit_notification_policy(
        app,
        {
            "enabled": True,
            "types": {
                CREDIT_NOTIFICATION_TYPE_GRANTED: {
                    "enabled": True,
                    "template_code": "TPL-GRANT-PARTIAL",
                }
            },
        },
    )

    assert policy["types"][CREDIT_NOTIFICATION_TYPE_GRANTED]["template_code"] == (
        "TPL-GRANT-PARTIAL"
    )


def test_credit_notification_policy_revalidates_cached_template_with_provider(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID=f"test-key-{secrets.token_hex(4)}",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET=secrets.token_urlsafe(24),
    )
    _seed_notification_template(
        app,
        template_code="TPL-DELETED",
        placeholders=["credits"],
    )
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.get_sms_template_ali",
        lambda app, *, template_code: SimpleNamespace(
            body=SimpleNamespace(
                code="isv.SMS_TEMPLATE_ILLEGAL",
                message="template not found",
                request_id="req-deleted",
            )
        ),
    )

    with pytest.raises(AppException):
        save_credit_notification_policy(
            app,
            {
                "enabled": True,
                "types": {
                    CREDIT_NOTIFICATION_TYPE_GRANTED: {
                        "enabled": True,
                        "template_code": "TPL-DELETED",
                    }
                },
            },
        )

    with app.app_context():
        template = NotificationTemplate.query.filter_by(
            template_code="TPL-DELETED"
        ).one()
        assert template.sync_status == "failed_provider"
        assert template.error_code == "isv.SMS_TEMPLATE_ILLEGAL"


def test_credit_notification_policy_rejects_unknown_template_variables(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    _seed_notification_template(
        app,
        template_code="TPL-GRANT-BAD",
        placeholders=["credits", "bad_variable"],
    )

    with pytest.raises(AppException):
        save_credit_notification_policy(
            app,
            {
                "enabled": True,
                "types": {
                    CREDIT_NOTIFICATION_TYPE_GRANTED: {
                        "enabled": True,
                        "template_code": "TPL-GRANT-BAD",
                    }
                },
            },
        )


def test_disabled_notification_type_does_not_require_template_validation(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app

    policy = save_credit_notification_policy(
        app,
        {
            "enabled": True,
            "types": {
                CREDIT_NOTIFICATION_TYPE_GRANTED: {
                    "enabled": False,
                    "template_code": "TPL-NOT-SYNCED",
                }
            },
        },
    )

    assert policy["types"][CREDIT_NOTIFICATION_TYPE_GRANTED]["enabled"] is False


@pytest.mark.parametrize(
    "threshold",
    [
        {
            "kind": "estimated_days",
            "days": 0,
            "lookback_days": 7,
            "min_consumed_days": 2,
        },
        {
            "kind": "estimated_days",
            "days": 7,
            "lookback_days": 0,
            "min_consumed_days": 2,
        },
        {
            "kind": "estimated_days",
            "days": 7,
            "lookback_days": 7,
            "min_consumed_days": 0,
        },
        {
            "kind": "estimated_days",
            "days": 366,
            "lookback_days": 7,
            "min_consumed_days": 2,
        },
        {
            "kind": "estimated_days",
            "days": 7,
            "lookback_days": 366,
            "min_consumed_days": 2,
        },
        {
            "kind": "estimated_days",
            "days": 7,
            "lookback_days": 7,
            "min_consumed_days": 8,
        },
        {
            "kind": "estimated_days",
            "days": 7,
            "lookback_days": 7,
            "min_consumed_days": 2,
            "fallback_fixed_value": "bad-decimal",
        },
        {"kind": "unknown", "value": "1"},
    ],
)
def test_credit_notification_policy_rejects_invalid_low_balance_thresholds(
    credit_notifications_app: Flask,
    threshold: dict[str, object],
) -> None:
    app = credit_notifications_app

    with pytest.raises(AppException):
        save_credit_notification_policy(
            app,
            {
                "enabled": True,
                "types": {
                    CREDIT_NOTIFICATION_TYPE_LOW_BALANCE: {
                        "enabled": True,
                        "template_code": "TPL-LOW",
                        "thresholds": [threshold],
                    }
                },
            },
        )


def test_credit_notification_skips_creator_without_mobile(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    now = datetime(2026, 5, 21, 0, 0, 0)
    _seed_creator(app, creator_bid="creator-no-mobile", mobile=None)
    _enable_policy(app)
    enqueue_calls: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.enqueue_credit_notification",
        lambda app, *, notification_bid: enqueue_calls.append(notification_bid),
    )
    with app.app_context():
        _seed_credit_ledger(
            ledger_bid="ledger-no-mobile",
            creator_bid="creator-no-mobile",
        )
        _seed_wallet(creator_bid="creator-no-mobile", available_credits="0")
        _seed_bucket(
            creator_bid="creator-no-mobile",
            effective_to=now + timedelta(days=1, hours=2),
        )
        dao.db.session.commit()

    staged = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-no-mobile",
        enqueue=True,
    )
    expiring = scan_credit_expiring_notifications(app, now=now)
    low_balance = scan_low_balance_notifications(app, now=now)

    assert staged["status"] == CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE
    assert staged["enqueued"] is False
    assert expiring["created_count"] == 0
    assert expiring["enqueued_count"] == 0
    assert expiring["candidate_count"] == 0
    assert expiring["notifications"][0]["status"] == (
        CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE
    )
    assert low_balance["created_count"] == 0
    assert low_balance["enqueued_count"] == 0
    assert low_balance["candidate_count"] == 0
    assert low_balance["notifications"][0]["status"] == (
        CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE
    )
    assert enqueue_calls == []
    with app.app_context():
        notifications = NotificationRecord.query.order_by(
            NotificationRecord.id.asc()
        ).all()
        assert [item.error_code for item in notifications] == [
            "missing_mobile",
            "missing_mobile",
            "missing_mobile",
        ]
        assert {item.status for item in notifications} == {
            CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE
        }


def test_credit_notification_skips_invalid_mobile(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    _seed_creator(app, creator_bid="creator-invalid-mobile", mobile="not-a-phone")
    _enable_policy(app)
    enqueue_calls: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.enqueue_credit_notification",
        lambda app, *, notification_bid: enqueue_calls.append(notification_bid),
    )
    with app.app_context():
        _seed_credit_ledger(
            ledger_bid="ledger-invalid-mobile",
            creator_bid="creator-invalid-mobile",
        )

    staged = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-invalid-mobile",
        enqueue=True,
    )

    assert staged["status"] == CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE
    assert staged["enqueued"] is False
    assert enqueue_calls == []
    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_bid=staged["notification_bid"]
        ).one()
        assert notification.error_code == "invalid_mobile"
        assert notification.mobile_snapshot == "not-a-phone"


def test_credit_notification_quiet_hours_uses_policy_timezone() -> None:
    policy = {
        "quiet_hours": {
            "enabled": True,
            "start": "22:00",
            "end": "09:00",
            "timezone": "Asia/Shanghai",
        }
    }

    assert _is_quiet_hours(
        policy,
        now=datetime.fromisoformat("2026-05-21T15:30:00+00:00"),
    )
    assert not _is_quiet_hours(
        policy,
        now=datetime.fromisoformat("2026-05-21T03:00:00+00:00"),
    )


def test_credit_notification_quiet_hours_converts_naive_process_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not hasattr(time_module, "tzset"):
        pytest.skip("tzset is unavailable on this platform")

    previous_tz = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "UTC")
    time_module.tzset()
    try:
        policy = {
            "quiet_hours": {
                "enabled": True,
                "start": "22:00",
                "end": "09:00",
                "timezone": "Asia/Shanghai",
            }
        }

        assert not _is_quiet_hours(policy, now=datetime(2026, 5, 23, 8, 0, 0))
        assert _is_quiet_hours(policy, now=datetime(2026, 5, 23, 15, 30, 0))
    finally:
        if previous_tz is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", previous_tz)
        time_module.tzset()


def test_credit_notification_list_handles_invalid_pagination(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app

    payload = list_credit_notifications(app, page_index="bad", page_size="bad")

    assert payload["page"] == 1
    assert payload["page_size"] == 20


def test_credit_notification_list_filters_delivery_status_and_skip_reason(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    records = [
        (
            "notification-contact",
            CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE,
            "missing_mobile",
        ),
        (
            "notification-policy",
            CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT,
            "quiet_hours",
        ),
        (
            "notification-template-params",
            CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT,
            "missing_template_params",
        ),
        (
            "notification-policy-stale",
            CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT,
            "expiry_extended",
        ),
        (
            "notification-duplicate",
            CREDIT_NOTIFICATION_STATUS_SUPPRESSED_DUPLICATE,
            "suppressed_duplicate",
        ),
        ("notification-stale", "skipped", "expiry_extended"),
        (
            "notification-failed",
            CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
            "provider_failed",
        ),
    ]
    with app.app_context():
        for index, (notification_bid, status, error_code) in enumerate(records):
            dao.db.session.add(
                NotificationRecord(
                    notification_bid=notification_bid,
                    notification_type=CREDIT_NOTIFICATION_TYPE_GRANTED,
                    channel="sms",
                    creator_bid=f"creator-{index}",
                    target_user_bid=f"creator-{index}",
                    mobile_snapshot="13800000000",
                    source_type="ledger",
                    source_bid=f"ledger-{index}",
                    dedupe_key=f"credit_granted:ledger-{index}",
                    status=status,
                    template_code="TPL-GRANT",
                    template_params_json={},
                    policy_snapshot_json={},
                    provider_response_json={},
                    error_code=error_code,
                    error_message=error_code,
                    metadata_json={},
                    deleted=0,
                    created_at=datetime(2026, 5, 21, 8, index, 0),
                    updated_at=datetime(2026, 5, 21, 8, index, 0),
                )
            )
        dao.db.session.commit()

    not_sent_payload = list_credit_notifications(
        app,
        filters={"delivery_status": "not_sent"},
    )
    assert not_sent_payload["total"] == 6
    assert {item["delivery_status"] for item in not_sent_payload["items"]} == {
        "not_sent"
    }
    assert {item["skip_reason"] for item in not_sent_payload["items"]} == {
        "contact",
        "policy",
        "template_params",
        "duplicate",
        "stale",
    }

    assert (
        list_credit_notifications(app, filters={"skip_reason": "contact"})["total"] == 1
    )
    assert (
        list_credit_notifications(app, filters={"skip_reason": "policy"})["items"][0][
            "notification_bid"
        ]
        == "notification-policy"
    )
    assert (
        list_credit_notifications(app, filters={"skip_reason": "template_params"})[
            "items"
        ][0]["notification_bid"]
        == "notification-template-params"
    )
    assert (
        list_credit_notifications(app, filters={"skip_reason": "duplicate"})["items"][
            0
        ]["notification_bid"]
        == "notification-duplicate"
    )
    assert {
        item["notification_bid"]
        for item in list_credit_notifications(
            app,
            filters={"skip_reason": "stale"},
        )["items"]
    } == {"notification-policy-stale", "notification-stale"}
    assert list_credit_notifications(app, filters={"status": "skipped"})["total"] == 6


def test_credit_notification_list_matches_google_email_credential(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    _seed_creator(app, creator_bid="google-creator", mobile=None)
    with app.app_context():
        upsert_credential(
            app,
            user_bid="google-creator",
            provider_name="google",
            subject_id="google-creator@example.com",
            subject_format="email",
            identifier="google-creator@example.com",
            metadata={},
            verified=True,
        )
        dao.db.session.add(
            NotificationRecord(
                notification_bid="notification-google-creator",
                notification_type=CREDIT_NOTIFICATION_TYPE_GRANTED,
                channel="sms",
                creator_bid="google-creator",
                target_user_bid="google-creator",
                mobile_snapshot="",
                source_type="ledger",
                source_bid="ledger-google",
                dedupe_key="credit_granted:ledger-google",
                status=CREDIT_NOTIFICATION_STATUS_PENDING,
                template_code="TPL-GRANT",
                template_params_json={},
                policy_snapshot_json={},
                provider_response_json={},
                metadata_json={},
                deleted=0,
                created_at=datetime(2026, 5, 21, 8, 0, 0),
                updated_at=datetime(2026, 5, 21, 8, 0, 0),
            )
        )
        dao.db.session.commit()

    payload = list_credit_notifications(
        app,
        filters={"creator_keyword": "google-creator@example.com"},
    )

    assert payload["total"] == 1
    assert payload["items"][0]["notification_bid"] == "notification-google-creator"


def test_credit_notification_list_ignores_unverified_credentials(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    _seed_creator(app, creator_bid="unverified-creator", mobile=None)
    with app.app_context():
        upsert_credential(
            app,
            user_bid="unverified-creator",
            provider_name="email",
            subject_id="unverified-creator@example.com",
            subject_format="email",
            identifier="unverified-creator@example.com",
            metadata={},
            verified=False,
        )
        dao.db.session.add(
            NotificationRecord(
                notification_bid="notification-unverified-creator",
                notification_type=CREDIT_NOTIFICATION_TYPE_GRANTED,
                channel="sms",
                creator_bid="unverified-creator",
                target_user_bid="unverified-creator",
                mobile_snapshot="",
                source_type="ledger",
                source_bid="ledger-unverified",
                dedupe_key="credit_granted:ledger-unverified",
                status=CREDIT_NOTIFICATION_STATUS_PENDING,
                template_code="TPL-GRANT",
                template_params_json={},
                policy_snapshot_json={},
                provider_response_json={},
                metadata_json={},
                deleted=0,
                created_at=datetime(2026, 5, 21, 8, 0, 0),
                updated_at=datetime(2026, 5, 21, 8, 0, 0),
            )
        )
        dao.db.session.commit()

    payload = list_credit_notifications(
        app,
        filters={"creator_keyword": "unverified-creator@example.com"},
    )

    assert payload["total"] == 0


def test_credit_notification_list_omits_detail_payloads(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    _seed_creator(app)
    _seed_notification_template(app, template_code="TPL-LOW")
    with app.app_context():
        dao.db.session.add(
            NotificationRecord(
                notification_bid="notification-list-summary",
                notification_type=CREDIT_NOTIFICATION_TYPE_LOW_BALANCE,
                channel="sms",
                creator_bid="creator-1",
                target_user_bid="creator-1",
                mobile_snapshot="13800000000",
                source_type="wallet",
                source_bid="creator-1",
                dedupe_key="low_balance:creator-1:5.00:2026-05-21",
                status=CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
                template_code="TPL-LOW",
                template_params_json={"available_credits": "2.00"},
                policy_snapshot_json={"enabled": True},
                provider_response_json={"code": "FAIL"},
                error_code="provider_failed",
                error_message="Provider failed.",
                metadata_json={"reason": "demo"},
                deleted=0,
                created_at=datetime(2026, 5, 21, 8, 0, 0),
                updated_at=datetime(2026, 5, 21, 8, 0, 0),
            )
        )
        dao.db.session.commit()

    payload = list_credit_notifications(app)

    item = payload["items"][0]
    assert item["notification_bid"] == "notification-list-summary"
    assert item["creator_nickname"] == "Creator"
    assert item["template_name"] == "Template TPL-LOW"
    assert item["created_at"] == "2026-05-21T08:00:00Z"
    assert item["updated_at"] == "2026-05-21T08:00:00Z"
    assert "template_params" not in item
    assert "policy_snapshot" not in item
    assert "provider_response" not in item
    assert "metadata" not in item
    assert "dedupe_key" not in item


def test_credit_notification_detail_includes_diagnostic_payloads(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    _seed_creator(app)
    _seed_notification_template(app, template_code="TPL-LOW")
    with app.app_context():
        dao.db.session.add(
            NotificationRecord(
                notification_bid="notification-detail",
                notification_type=CREDIT_NOTIFICATION_TYPE_LOW_BALANCE,
                channel="sms",
                creator_bid="creator-1",
                target_user_bid="creator-1",
                mobile_snapshot="13800000000",
                source_type="wallet",
                source_bid="creator-1",
                dedupe_key="low_balance:creator-1:5.00:2026-05-21",
                status=CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
                template_code="TPL-LOW",
                template_params_json={"available_credits": "2.00"},
                policy_snapshot_json={"enabled": True},
                provider_response_json={"code": "FAIL"},
                error_code="provider_failed",
                error_message="Provider failed.",
                metadata_json={"reason": "demo"},
                deleted=0,
                created_at=datetime(2026, 5, 21, 8, 0, 0),
                updated_at=datetime(2026, 5, 21, 8, 0, 0),
            )
        )
        dao.db.session.commit()

    payload = get_credit_notification_detail(
        app,
        notification_bid="notification-detail",
    )

    assert payload["template_params"] == {"available_credits": "2.00"}
    assert payload["policy_snapshot"] == {"enabled": True}
    assert payload["provider_response"] == {"code": "FAIL"}
    assert payload["metadata"] == {"reason": "demo"}
    assert payload["dedupe_key"] == "low_balance:creator-1:5.00:2026-05-21"
    assert payload["creator_nickname"] == "Creator"
    assert payload["template_name"] == "Template TPL-LOW"
    assert payload["created_at"] == "2026-05-21T08:00:00Z"
    assert payload["updated_at"] == "2026-05-21T08:00:00Z"


def test_credit_notifications_skip_non_creator_billing_facts(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    now = datetime(2026, 5, 21, 0, 0, 0)
    _seed_creator(app, creator_bid="regular-user", is_creator=False)
    _enable_policy(app)

    with app.app_context():
        _seed_credit_ledger(
            ledger_bid="ledger-regular-user",
            creator_bid="regular-user",
        )
        _seed_wallet(creator_bid="regular-user", available_credits="0")
        _seed_bucket(
            creator_bid="regular-user",
            effective_to=now + timedelta(days=1, hours=2),
        )
        dao.db.session.commit()

    granted = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-regular-user",
        enqueue=False,
    )
    expiring = scan_credit_expiring_notifications(app, now=now)
    low_balance = scan_low_balance_notifications(app, now=now)

    assert granted["status"] == "skipped_ineligible_creator"
    assert expiring["candidate_count"] == 0
    assert low_balance["candidate_count"] == 0
    with app.app_context():
        assert NotificationRecord.query.count() == 0


def test_credit_notifications_skip_unregistered_creators(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    now = datetime(2026, 5, 21, 0, 0, 0)
    _seed_creator(
        app,
        creator_bid="unregistered-creator",
        state=USER_STATE_UNREGISTERED,
    )
    _enable_policy(app)

    with app.app_context():
        _seed_credit_ledger(
            ledger_bid="ledger-unregistered-creator",
            creator_bid="unregistered-creator",
        )
        _seed_wallet(creator_bid="unregistered-creator", available_credits="0")
        _seed_bucket(
            creator_bid="unregistered-creator",
            effective_to=now + timedelta(days=1, hours=2),
        )
        dao.db.session.commit()

    granted = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-unregistered-creator",
        enqueue=False,
    )
    expiring = scan_credit_expiring_notifications(app, now=now)
    low_balance = scan_low_balance_notifications(app, now=now)

    assert granted["status"] == "skipped_ineligible_creator"
    assert expiring["candidate_count"] == 0
    assert low_balance["candidate_count"] == 0
    with app.app_context():
        assert NotificationRecord.query.count() == 0


def test_expiring_and_low_balance_scans_stage_deduped_notifications(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    now = datetime(2026, 5, 21, 0, 0, 0)
    _seed_creator(app)
    _enable_policy(app)
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.enqueue_credit_notification",
        lambda app, *, notification_bid: {
            "status": "enqueued",
            "notification_bid": notification_bid,
            "enqueued": True,
        },
    )

    with app.app_context():
        _seed_wallet()
        _seed_bucket(effective_to=now + timedelta(days=1, hours=2))
        dao.db.session.commit()

    expiring_first = scan_credit_expiring_notifications(app, now=now)
    expiring_second = scan_credit_expiring_notifications(app, now=now)
    low_balance_first = scan_low_balance_notifications(app, now=now)
    low_balance_second = scan_low_balance_notifications(app, now=now)

    assert expiring_first["created_count"] == 1
    assert expiring_first["enqueued_count"] == 1
    assert expiring_first["notifications"][0]["dedupe_key"] == (
        "credit_expiring:creator-1:1d:2026-05-21"
    )
    assert expiring_second["created_count"] == 0
    assert expiring_second["notifications"][0]["status"] == "suppressed_duplicate"
    assert low_balance_first["created_count"] == 1
    assert low_balance_first["enqueued_count"] == 1
    assert low_balance_second["created_count"] == 0

    with app.app_context():
        assert NotificationRecord.query.count() == 2
        expiring_notification = NotificationRecord.query.filter_by(
            notification_type=CREDIT_NOTIFICATION_TYPE_EXPIRING
        ).one()
        assert expiring_notification.template_params_json == {
            "credits": "5.00",
            "expires_at": "2026-05-22 02:00:00",
            "window": "1d",
        }


def test_expiring_scan_merges_same_creator_buckets(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    now = datetime(2026, 5, 21, 0, 0, 0)
    _seed_creator(app)
    _enable_policy(app)
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.enqueue_credit_notification",
        lambda app, *, notification_bid: {
            "status": "enqueued",
            "notification_bid": notification_bid,
            "enqueued": True,
        },
    )

    with app.app_context():
        _seed_wallet()
        _seed_bucket(
            wallet_bucket_bid="bucket-creator-1-a",
            effective_to=now + timedelta(days=1, hours=2),
            available_credits="2",
        )
        _seed_bucket(
            wallet_bucket_bid="bucket-creator-1-b",
            effective_to=now + timedelta(days=1, hours=2),
            available_credits="3.5",
        )
        dao.db.session.commit()

    payload = scan_credit_expiring_notifications(app, now=now)
    second_payload = scan_credit_expiring_notifications(app, now=now)

    assert payload["created_count"] == 1
    assert payload["enqueued_count"] == 1
    assert payload["notifications"][0]["dedupe_key"] == (
        "credit_expiring:creator-1:1d:2026-05-21"
    )
    assert second_payload["created_count"] == 0
    assert second_payload["notifications"][0]["status"] == "suppressed_duplicate"
    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_type=CREDIT_NOTIFICATION_TYPE_EXPIRING
        ).one()
        assert notification.template_params_json == {
            "credits": "5.50",
            "expires_at": "2026-05-22 02:00:00",
            "window": "1d",
        }
        assert notification.metadata_json["merged_bucket_count"] == 2
        assert notification.metadata_json["wallet_bucket_bids"] == [
            "bucket-creator-1-a",
            "bucket-creator-1-b",
        ]


def test_expiring_merge_suppresses_existing_bucket_level_record(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    now = datetime(2026, 5, 21, 0, 0, 0)
    _seed_creator(app)
    _enable_policy(app)

    with app.app_context():
        _seed_wallet()
        _seed_bucket(
            wallet_bucket_bid="bucket-creator-1-a",
            effective_to=now + timedelta(days=1, hours=2),
            available_credits="2",
        )
        _seed_bucket(
            wallet_bucket_bid="bucket-creator-1-b",
            effective_to=now + timedelta(days=1, hours=2),
            available_credits="3.5",
        )
        dao.db.session.add(
            NotificationRecord(
                notification_bid="legacy-expiring-record",
                notification_type=CREDIT_NOTIFICATION_TYPE_EXPIRING,
                channel="sms",
                creator_bid="creator-1",
                target_user_bid="creator-1",
                mobile_snapshot="13800000000",
                source_type="wallet_bucket",
                source_bid="bucket-creator-1-a",
                dedupe_key="credit_expiring:bucket-creator-1-a:1d",
                status=CREDIT_NOTIFICATION_STATUS_SENT,
                template_code="TPL-EXPIRING",
                template_params_json={
                    "credits": "2.00",
                    "expires_at": "2026-05-22 02:00:00",
                    "window": "1d",
                },
                policy_snapshot_json={},
                provider_response_json={},
                requested_at=now,
                attempted_at=now,
                sent_at=now,
                metadata_json={
                    "wallet_bucket_bid": "bucket-creator-1-a",
                    "window": "1d",
                },
                deleted=0,
            )
        )
        dao.db.session.commit()

    payload = scan_credit_expiring_notifications(app, now=now)

    assert payload["created_count"] == 0
    assert payload["notifications"][0]["status"] == "suppressed_duplicate"
    assert payload["notifications"][0]["notification_bid"] == "legacy-expiring-record"
    with app.app_context():
        assert NotificationRecord.query.count() == 1


def test_low_balance_estimated_days_scan_uses_daily_ledger_summary(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    now = datetime(2026, 5, 21, 8, 0, 0)
    _seed_creator(app)
    _enable_policy(
        app,
        low_balance_thresholds=[
            {
                "kind": "estimated_days",
                "days": 7,
                "lookback_days": 7,
                "min_consumed_days": 2,
            }
        ],
    )
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.enqueue_credit_notification",
        lambda app, *, notification_bid: {
            "status": "enqueued",
            "notification_bid": notification_bid,
            "enqueued": True,
        },
    )

    with app.app_context():
        _seed_wallet(available_credits="12")
        _seed_daily_consumption(stat_date="2026-05-19", amount="-3")
        _seed_daily_consumption(stat_date="2026-05-20", amount="-3")
        dao.db.session.commit()

    first = scan_low_balance_notifications(app, now=now)
    second = scan_low_balance_notifications(app, now=now)

    assert first["created_count"] == 1
    assert first["enqueued_count"] == 1
    assert first["notifications"][0]["dedupe_key"] == (
        "low_balance:creator-1:estimated_days:7:lookback:7:2026-05-21"
    )
    assert second["created_count"] == 0
    assert second["notifications"][0]["status"] == "suppressed_duplicate"
    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_type=CREDIT_NOTIFICATION_TYPE_LOW_BALANCE
        ).one()
        assert notification.template_params_json == {
            "available_credits": "12.00",
            "avg_daily_consumption": "3.00",
            "estimated_remaining_days": "4.00",
            "lookback_days": "7",
            "threshold": "",
            "threshold_kind": "estimated_days",
            "trigger_days": "7",
        }
        assert notification.metadata_json["consumed_days"] == 2


def test_low_balance_estimated_days_dry_run_reports_non_candidate_reason(
    credit_notifications_app: Flask,
) -> None:
    app = credit_notifications_app
    now = datetime(2026, 5, 21, 8, 0, 0)
    _seed_creator(app)
    _enable_policy(
        app,
        low_balance_thresholds=[
            {
                "kind": "estimated_days",
                "days": 7,
                "lookback_days": 7,
                "min_consumed_days": 2,
            }
        ],
    )

    with app.app_context():
        _seed_wallet(available_credits="30")
        _seed_daily_consumption(stat_date="2026-05-19", amount="-3")
        _seed_daily_consumption(stat_date="2026-05-20", amount="-3")
        dao.db.session.commit()

    payload = scan_low_balance_notifications(app, now=now, dry_run=True)

    assert payload["candidate_count"] == 0
    assert payload["created_count"] == 0
    assert payload["status"] == "noop"
    assert payload["notifications"][0]["reason"] == "remaining_days_above_threshold"
    assert payload["notifications"][0]["estimated_remaining_days"] == "10.00"


def test_low_balance_estimated_days_uses_fallback_fixed_threshold_when_history_is_sparse(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    now = datetime(2026, 5, 21, 8, 0, 0)
    _seed_creator(app)
    _enable_policy(
        app,
        low_balance_thresholds=[
            {
                "kind": "estimated_days",
                "days": 7,
                "lookback_days": 7,
                "min_consumed_days": 2,
                "fallback_fixed_value": "5",
            }
        ],
    )
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.enqueue_credit_notification",
        lambda app, *, notification_bid: {
            "status": "enqueued",
            "notification_bid": notification_bid,
            "enqueued": True,
        },
    )

    with app.app_context():
        _seed_wallet(available_credits="4")
        _seed_daily_consumption(stat_date="2026-05-20", amount="-3")
        dao.db.session.commit()

    payload = scan_low_balance_notifications(app, now=now)

    assert payload["created_count"] == 1
    assert payload["notifications"][0]["dedupe_key"] == (
        "low_balance:creator-1:5.00:2026-05-21"
    )
    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_type=CREDIT_NOTIFICATION_TYPE_LOW_BALANCE
        ).one()
        assert notification.template_params_json["threshold_kind"] == "fixed"
        assert notification.template_params_json["threshold"] == "5.00"
        assert notification.metadata_json["fallback_from"] == "estimated_days"


def test_low_balance_estimated_days_skips_when_valid_daily_consumption_is_missing(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    now = datetime(2026, 5, 21, 8, 0, 0)
    _seed_creator(app)
    _enable_policy(
        app,
        low_balance_thresholds=[
            {
                "kind": "estimated_days",
                "days": 7,
                "lookback_days": 7,
                "min_consumed_days": 2,
                "fallback_fixed_value": "5",
            }
        ],
    )
    enqueue_calls: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.enqueue_credit_notification",
        lambda app, *, notification_bid: enqueue_calls.append(notification_bid),
    )

    with app.app_context():
        _seed_wallet(available_credits="0")
        _seed_daily_consumption(stat_date="2026-05-20", amount="0")
        dao.db.session.commit()

    payload = scan_low_balance_notifications(app, now=now)
    dry_run_payload = scan_low_balance_notifications(app, now=now, dry_run=True)

    assert payload["candidate_count"] == 0
    assert payload["created_count"] == 0
    assert payload["enqueued_count"] == 0
    assert payload["notifications"] == []
    assert enqueue_calls == []
    assert dry_run_payload["candidate_count"] == 0
    assert dry_run_payload["notifications"][0]["reason"] == (
        "missing_daily_consumption_summary"
    )
    assert dry_run_payload["notifications"][0]["estimated_remaining_days"] == ""
    assert dry_run_payload["notifications"][0]["threshold"] == ""
    with app.app_context():
        assert NotificationRecord.query.count() == 0


def test_low_balance_scan_skips_zero_balance_without_estimated_remaining_days(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    now = datetime(2026, 5, 21, 8, 0, 0)
    _seed_creator(app)
    _enable_policy(
        app,
        low_balance_thresholds=[{"kind": "fixed", "value": "0"}],
    )
    enqueue_calls: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.enqueue_credit_notification",
        lambda app, *, notification_bid: enqueue_calls.append(notification_bid),
    )

    with app.app_context():
        _seed_wallet(available_credits="0")
        dao.db.session.commit()

    payload = scan_low_balance_notifications(app, now=now)
    dry_run_payload = scan_low_balance_notifications(app, now=now, dry_run=True)

    assert payload["candidate_count"] == 0
    assert payload["created_count"] == 0
    assert payload["enqueued_count"] == 0
    assert payload["notifications"] == []
    assert enqueue_calls == []
    assert dry_run_payload["candidate_count"] == 0
    assert dry_run_payload["notifications"][0]["reason"] == (
        "zero_balance_missing_estimated_remaining_days"
    )
    with app.app_context():
        assert NotificationRecord.query.count() == 0


def test_low_balance_scan_skips_template_params_missing_for_mode(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    now = datetime(2026, 5, 21, 8, 0, 0)
    _seed_creator(app)
    _enable_policy(
        app,
        low_balance_thresholds=[{"kind": "fixed", "value": "5"}],
    )
    _seed_notification_template(
        app,
        template_code="TPL-LOW",
        placeholders=["available_credits", "estimated_remaining_days"],
    )
    enqueue_calls: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.enqueue_credit_notification",
        lambda app, *, notification_bid: enqueue_calls.append(notification_bid),
    )

    with app.app_context():
        _seed_wallet(available_credits="2")
        dao.db.session.commit()

    payload = scan_low_balance_notifications(app, now=now)
    dry_run_payload = scan_low_balance_notifications(app, now=now, dry_run=True)

    assert payload["candidate_count"] == 0
    assert payload["created_count"] == 0
    assert payload["enqueued_count"] == 0
    assert payload["notifications"] == []
    assert enqueue_calls == []
    assert dry_run_payload["candidate_count"] == 0
    assert dry_run_payload["notifications"][0]["reason"] == "missing_template_params"
    assert dry_run_payload["notifications"][0]["missing_template_params"] == [
        "estimated_remaining_days"
    ]
    with app.app_context():
        assert NotificationRecord.query.count() == 0


def test_low_balance_delivery_skips_zero_balance_without_estimated_remaining_days(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    _seed_creator(app)
    _enable_policy(app)
    send_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.send_sms_ali",
        lambda app, mobile, *, template_code, template_params, sign_name=None: (
            send_calls.append(
                {
                    "mobile": mobile,
                    "template_code": template_code,
                    "template_params": dict(template_params),
                }
            )
            or SimpleNamespace(body=SimpleNamespace(code="OK"))
        ),
    )

    with app.app_context():
        notification = NotificationRecord(
            notification_bid="notification-zero-missing-days",
            notification_type=CREDIT_NOTIFICATION_TYPE_LOW_BALANCE,
            channel="sms",
            creator_bid="creator-1",
            target_user_bid="creator-1",
            mobile_snapshot="13800000000",
            source_type="wallet",
            source_bid="creator-1",
            dedupe_key="low_balance:creator-1:0.00:2026-05-21",
            status=CREDIT_NOTIFICATION_STATUS_PENDING,
            template_code="TPL-LOW",
            template_params_json={
                "available_credits": "0.00",
                "threshold": "0.00",
                "threshold_kind": "fixed",
                "trigger_days": "",
                "lookback_days": "",
                "avg_daily_consumption": "",
                "estimated_remaining_days": "",
            },
            policy_snapshot_json={},
            provider_response_json={},
            metadata_json={},
            deleted=0,
            created_at=datetime(2026, 5, 21, 8, 0, 0),
            updated_at=datetime(2026, 5, 21, 8, 0, 0),
        )
        dao.db.session.add(notification)
        dao.db.session.commit()

    delivered = deliver_credit_notification(
        app,
        notification_bid="notification-zero-missing-days",
    )

    assert delivered["status"] == CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT
    assert delivered["reason"] == "zero_balance_missing_estimated_remaining_days"
    assert send_calls == []
    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_bid="notification-zero-missing-days"
        ).one()
        assert notification.status == CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT
        assert notification.error_code == (
            "zero_balance_missing_estimated_remaining_days"
        )


def test_low_balance_delivery_skips_template_params_missing_for_mode(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    _seed_creator(app)
    _enable_policy(app)
    _seed_notification_template(
        app,
        template_code="TPL-LOW",
        placeholders=["available_credits", "estimated_remaining_days"],
    )
    send_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.send_sms_ali",
        lambda app, mobile, *, template_code, template_params, sign_name=None: (
            send_calls.append(
                {
                    "mobile": mobile,
                    "template_code": template_code,
                    "template_params": dict(template_params),
                }
            )
            or SimpleNamespace(body=SimpleNamespace(code="OK"))
        ),
    )

    with app.app_context():
        notification = NotificationRecord(
            notification_bid="notification-missing-template-param",
            notification_type=CREDIT_NOTIFICATION_TYPE_LOW_BALANCE,
            channel="sms",
            creator_bid="creator-1",
            target_user_bid="creator-1",
            mobile_snapshot="13800000000",
            source_type="wallet",
            source_bid="creator-1",
            dedupe_key="low_balance:creator-1:5.00:2026-05-21",
            status=CREDIT_NOTIFICATION_STATUS_PENDING,
            template_code="TPL-LOW",
            template_params_json={
                "available_credits": "2.00",
                "threshold": "5.00",
                "threshold_kind": "fixed",
                "trigger_days": "",
                "lookback_days": "",
                "avg_daily_consumption": "",
                "estimated_remaining_days": "",
            },
            policy_snapshot_json={},
            provider_response_json={},
            metadata_json={},
            deleted=0,
            created_at=datetime(2026, 5, 21, 8, 0, 0),
            updated_at=datetime(2026, 5, 21, 8, 0, 0),
        )
        dao.db.session.add(notification)
        dao.db.session.commit()

    delivered = deliver_credit_notification(
        app,
        notification_bid="notification-missing-template-param",
    )

    assert delivered["status"] == CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT
    assert delivered["reason"] == "missing_template_params"
    assert delivered["missing_template_params"] == ["estimated_remaining_days"]
    assert send_calls == []
    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_bid="notification-missing-template-param"
        ).one()
        assert notification.status == CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT
        assert notification.error_code == "missing_template_params"


def test_failed_provider_notification_can_be_requeued(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    _seed_creator(app)
    _enable_policy(app)
    captured_kwargs: list[dict[str, str]] = []

    class FakeTask:
        def apply_async(self, kwargs):
            captured_kwargs.append(dict(kwargs))

    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.send_sms_ali",
        lambda app, mobile, *, template_code, template_params, sign_name=None: None,
    )
    monkeypatch.setitem(
        sys.modules,
        "flaskr.common.celery_app",
        SimpleNamespace(
            get_celery_app=lambda flask_app=None: SimpleNamespace(
                tasks={"billing.send_credit_notification": FakeTask()}
            )
        ),
    )

    with app.app_context():
        _seed_credit_ledger(ledger_bid="ledger-provider-failure")

    staged = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-provider-failure",
        enqueue=False,
    )
    failed = deliver_credit_notification(
        app,
        notification_bid=str(staged["notification_bid"]),
    )
    requeued = requeue_credit_notification(
        app,
        notification_bid=str(staged["notification_bid"]),
    )

    assert failed["status"] == CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER
    assert requeued["status"] == "enqueued"
    assert captured_kwargs == [{"notification_bid": staged["notification_bid"]}]
    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_bid=staged["notification_bid"]
        ).one()
        assert notification.status == CREDIT_NOTIFICATION_STATUS_PENDING


def test_requeue_keeps_failed_status_when_enqueue_fails(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    _seed_creator(app)
    _enable_policy(app)
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.send_sms_ali",
        lambda app, mobile, *, template_code, template_params, sign_name=None: None,
    )
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.enqueue_credit_notification",
        lambda app, *, notification_bid: {
            "status": "enqueue_failed",
            "notification_bid": notification_bid,
            "enqueued": False,
        },
    )

    with app.app_context():
        _seed_credit_ledger(ledger_bid="ledger-requeue-failure")

    staged = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-requeue-failure",
        enqueue=False,
    )
    deliver_credit_notification(app, notification_bid=str(staged["notification_bid"]))
    requeued = requeue_credit_notification(
        app,
        notification_bid=str(staged["notification_bid"]),
    )

    assert requeued["enqueued"] is False
    assert requeued["notification_status"] == CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER
    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_bid=staged["notification_bid"]
        ).one()
        assert notification.status == CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER


def test_requeue_records_operator_audit_metadata(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    _seed_creator(app)
    _enable_policy(app)
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.send_sms_ali",
        lambda app, mobile, *, template_code, template_params, sign_name=None: None,
    )
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.enqueue_credit_notification",
        lambda app, *, notification_bid: {
            "status": "enqueued",
            "notification_bid": notification_bid,
            "enqueued": True,
        },
    )

    with app.app_context():
        _seed_credit_ledger(ledger_bid="ledger-requeue-audit")

    staged = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-requeue-audit",
        enqueue=False,
    )
    deliver_credit_notification(app, notification_bid=str(staged["notification_bid"]))
    requeue_credit_notification(
        app,
        notification_bid=str(staged["notification_bid"]),
        operator_user_bid="operator-audit-2",
    )

    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_bid=staged["notification_bid"]
        ).one()
        assert notification.metadata_json["last_requeued_by"] == "operator-audit-2"
        assert notification.metadata_json["last_requeued_at"]
        assert notification.metadata_json["last_requeued_at"].endswith("Z")


def test_provider_exception_marks_notification_failed(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    _seed_creator(app)
    _enable_policy(app)

    def raise_provider_error(*args, **kwargs) -> None:
        raise RuntimeError("provider raised")

    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.send_sms_ali",
        raise_provider_error,
    )
    with app.app_context():
        _seed_credit_ledger(ledger_bid="ledger-provider-exception")

    staged = stage_credit_granted_notification(
        app,
        ledger_bid="ledger-provider-exception",
        enqueue=False,
    )
    delivered = deliver_credit_notification(
        app,
        notification_bid=str(staged["notification_bid"]),
    )

    assert delivered["status"] == CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER
    assert delivered["error_code"] == "provider_exception"
    with app.app_context():
        notification = NotificationRecord.query.filter_by(
            notification_bid=staged["notification_bid"]
        ).one()
        assert notification.error_code == "provider_exception"


def test_send_credit_notification_task_raises_retryable_on_provider_failure(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    monkeypatch.setattr(
        "flaskr.service.billing.tasks._create_task_app",
        lambda: app,
    )
    monkeypatch.setattr(
        "flaskr.service.billing.tasks._deliver_credit_notification",
        lambda app, *, notification_bid: {
            "status": CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
            "notification_bid": notification_bid,
            "error_code": "provider_failed",
        },
    )

    with pytest.raises(CreditNotificationRetryableError):
        send_credit_notification_task(notification_bid="notification-retry-1")


def test_send_credit_notification_task_does_not_retry_config_failure(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    monkeypatch.setattr(
        "flaskr.service.billing.tasks._create_task_app",
        lambda: app,
    )
    monkeypatch.setattr(
        "flaskr.service.billing.tasks._deliver_credit_notification",
        lambda app, *, notification_bid: {
            "status": CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
            "notification_bid": notification_bid,
            "error_code": "missing_template_code",
        },
    )

    payload = send_credit_notification_task(notification_bid="notification-config-1")

    assert payload["status"] == CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER


def test_softlimit_disables_debug_when_policy_threshold_is_reached(
    credit_notifications_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = credit_notifications_app
    _enable_policy(
        app,
        softlimit={
            "enabled": True,
            "threshold": {"kind": "fixed", "value": "5"},
            "disable_debug": True,
        },
    )
    monkeypatch.setattr(
        "flaskr.service.billing.credit_notifications.is_billing_enabled",
        lambda: True,
    )
    with app.app_context():
        _seed_wallet(available_credits="2")
        dao.db.session.commit()

    state = resolve_creator_limit_state(app, "creator-1")

    assert state["state"] == "softlimit"
    assert state["debug_allowed"] is False
    with pytest.raises(AppException):
        assert_creator_debug_allowed(app, "creator-1")

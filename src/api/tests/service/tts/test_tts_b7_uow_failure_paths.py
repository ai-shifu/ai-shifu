"""Failure-path coverage for the streaming/long-task unit-of-work batch (B7).

Voice cloning is claim -> provider -> finalize as consecutive units of work;
audit (risk control) and metering rows persist autonomously so they survive a
rollback of the caller's unit of work.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing.models import CreditWallet
from flaskr.service.user.models import UserInfo  # noqa: F401 - registers user_users

from tests.service.tts.test_minimax_voice_clone import (
    _enqueue_clone,
    _normalize_audio,
    _seed_course_wallet_and_rate,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

_MODULE = "flaskr.service.tts.minimax_voice_clone"


@pytest.fixture
def clone_app(monkeypatch: object) -> Iterator[Flask]:
    """Mirror of ``test_minimax_voice_clone.minimax_clone_app`` (billing on)."""
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        REDIS_KEY_PREFIX="minimax-clone-b7-test",
        TZ="UTC",
    )
    monkeypatch.setattr(
        "flaskr.service.billing.admission.is_billing_enabled", lambda: True
    )
    monkeypatch.setattr(
        "flaskr.service.billing.primitives.is_billing_enabled", lambda: True
    )
    dao.db.init_app(app)
    with app.app_context():
        from flaskr.service.tts.models import TTSMiniMaxClonedVoice  # noqa: F401

        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _stub_resources(monkeypatch: object) -> None:
    monkeypatch.setattr(
        f"{_MODULE}._store_resource_bytes",
        lambda _app, **kwargs: SimpleNamespace(
            resource_bid=f"res-{kwargs['resource_kind']}",
            url=f"/resource/{kwargs['resource_kind']}",
            object_key=f"key/{kwargs['resource_kind']}",
        ),
    )
    monkeypatch.setattr(
        f"{_MODULE}._delete_resource_object", lambda _app, _resource_bid: None
    )
    monkeypatch.setattr(f"{_MODULE}.normalize_audio_blob", _normalize_audio)


def _submit(app: Flask, *, voice_id: str) -> object:
    from flaskr.service.tts.minimax_voice_clone import submit_minimax_voice_clone

    return submit_minimax_voice_clone(
        app,
        owner_user_bid="creator-1",
        shifu_bid="shifu-1",
        display_name="Teacher Voice",
        voice_id=voice_id,
        source_audio_bytes=b"RAW",
        source_filename="recording.webm",
        source_content_type="audio/webm",
        source_capture_method="recording",
    )


def _wallet(app: Flask) -> tuple[Decimal, Decimal]:
    with app.app_context():
        dao.db.session.expire_all()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
        return wallet.available_credits, wallet.reserved_credits


def test_submit_releases_reservation_and_writes_no_row_when_row_insert_fails(
    clone_app: Flask, monkeypatch: object
) -> None:
    """The reservation commits on its own; a failed row step must hand it back."""
    from flaskr.service.tts import minimax_voice_clone
    from flaskr.service.tts.models import TTSMiniMaxClonedVoice

    _seed_course_wallet_and_rate(clone_app)
    _stub_resources(monkeypatch)
    monkeypatch.setattr(f"{_MODULE}._enqueue_minimax_clone_task", _enqueue_clone)

    real_session = dao.db.session

    class _RejectingSession:
        def add(self, instance: object) -> None:
            if isinstance(instance, TTSMiniMaxClonedVoice):
                message = "row insert failed"
                raise RuntimeError(message)  # noqa: TRY004 - simulated DB failure
            real_session.add(instance)

        def __getattr__(self, name: str) -> object:
            return getattr(real_session, name)

    monkeypatch.setattr(
        minimax_voice_clone, "db", SimpleNamespace(session=_RejectingSession())
    )

    with pytest.raises(RuntimeError, match="row insert failed"):
        _submit(clone_app, voice_id="AiShifu_failed_1")

    with clone_app.app_context():
        assert (
            TTSMiniMaxClonedVoice.query.filter_by(voice_id="AiShifu_failed_1").count()
            == 0
        )
    assert _wallet(clone_app) == (Decimal("10.0000000000"), Decimal("0E-10"))


def test_submit_persists_failed_row_when_enqueue_fails(
    clone_app: Flask, monkeypatch: object
) -> None:
    """A broker failure after the row commit lands as a durable failed row."""
    from flaskr.service.tts.minimax_voice_clone import (
        TTS_MINIMAX_CLONE_STATUS_FAILED,
    )
    from flaskr.service.tts.models import TTSMiniMaxClonedVoice

    _seed_course_wallet_and_rate(clone_app)
    _stub_resources(monkeypatch)

    def _broken_enqueue(_app: object, *, voice_bid: str) -> bool:
        _ = voice_bid
        message = "broker down"
        raise RuntimeError(message)

    monkeypatch.setattr(f"{_MODULE}._enqueue_minimax_clone_task", _broken_enqueue)

    returned = _submit(clone_app, voice_id="AiShifu_route_queued_1")

    assert returned.status == TTS_MINIMAX_CLONE_STATUS_FAILED
    with clone_app.app_context():
        dao.db.session.expire_all()
        row = TTSMiniMaxClonedVoice.query.filter_by(
            voice_id="AiShifu_route_queued_1"
        ).one()
        assert row.status == TTS_MINIMAX_CLONE_STATUS_FAILED
        assert row.failure_reason == "enqueue_failed"
        assert row.billing_status == "released"
    assert _wallet(clone_app) == (Decimal("10.0000000000"), Decimal("0E-10"))


def test_run_claim_is_durable_before_provider_call_and_failure_releases(
    clone_app: Flask, monkeypatch: object
) -> None:
    """Step 1 (processing) commits before the provider round trip; a provider failure finalizes as failed + released."""
    from flaskr.service.tts.minimax_voice_clone import (
        TTS_MINIMAX_CLONE_STATUS_FAILED,
        TTS_MINIMAX_CLONE_STATUS_PROCESSING,
        run_minimax_voice_clone,
    )
    from flaskr.service.tts.models import TTSMiniMaxClonedVoice

    _seed_course_wallet_and_rate(clone_app)
    _stub_resources(monkeypatch)
    monkeypatch.setattr(f"{_MODULE}._enqueue_minimax_clone_task", _enqueue_clone)
    submitted = _submit(clone_app, voice_id="AiShifu_teacher_retry_1")

    seen_statuses: list[object] = []

    class _DownClient:
        def upload_clone_audio(self, *_args: object, **_kwargs: object) -> object:
            # Committed state only: the claim must already be durable here,
            # i.e. visible to a query that cannot see uncommitted rows.
            with dao.db.engine.connect() as connection:
                status = connection.exec_driver_sql(
                    "SELECT status FROM tts_minimax_cloned_voices WHERE voice_bid = ?",
                    (submitted.voice_bid,),
                ).scalar()
            seen_statuses.append(status)
            message = "provider down"
            raise RuntimeError(message)

    monkeypatch.setattr(f"{_MODULE}.MiniMaxVoiceCloneClient", _DownClient)

    result = run_minimax_voice_clone(clone_app, voice_bid=submitted.voice_bid)

    assert result.status == "failed"
    with clone_app.app_context():
        dao.db.session.expire_all()
        row = TTSMiniMaxClonedVoice.query.filter_by(voice_bid=submitted.voice_bid).one()
        assert seen_statuses == [TTS_MINIMAX_CLONE_STATUS_PROCESSING], row.status_msg
        assert row.status == TTS_MINIMAX_CLONE_STATUS_FAILED
        assert row.failure_reason == "worker_failed"
        assert row.billing_status == "released"
    assert _wallet(clone_app) == (Decimal("10.0000000000"), Decimal("0E-10"))


def test_risk_control_result_survives_caller_rollback(app: Flask) -> None:
    """The audit row is autonomous: it stays when the surrounding unit of work fails."""
    from flaskr.service.check_risk.funcs import add_risk_control_result
    from flaskr.service.check_risk.models import RiskControlResult
    from flaskr.service.shifu.models import DraftShifu

    def _caller_fails_after_audit_write() -> None:
        with unit_of_work():
            dao.db.session.add(
                DraftShifu(
                    shifu_bid="b7-risk-caller-1",
                    title="rolled back",
                    created_user_bid="user-1",
                    updated_user_bid="user-1",
                )
            )
            result_id = add_risk_control_result(
                app,
                "chat-b7",
                "user-1",
                "text",
                "vendor",
                "pass",
                "{}",
                1,
                "check_text",
            )
            assert result_id > 0
            message = "caller failed"
            raise RuntimeError(message)

    with app.app_context():
        with pytest.raises(RuntimeError, match="caller failed"):
            _caller_fails_after_audit_write()

        dao.db.session.expire_all()
        assert DraftShifu.query.filter_by(shifu_bid="b7-risk-caller-1").count() == 0
        assert RiskControlResult.query.filter_by(chat_id="chat-b7").count() == 1


def test_usage_record_survives_caller_rollback(app: Flask) -> None:
    """Metering rows are autonomous as well: a /run rollback never loses usage."""
    from flaskr.service.metering import UsageContext, record_tts_usage
    from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW
    from flaskr.service.metering.models import BillUsageRecord
    from flaskr.service.shifu.models import DraftShifu

    usage_bids: list[str] = []

    def _caller_fails_after_usage_write() -> None:
        with unit_of_work():
            dao.db.session.add(
                DraftShifu(
                    shifu_bid="b7-usage-caller-1",
                    title="rolled back",
                    created_user_bid="user-1",
                    updated_user_bid="user-1",
                )
            )
            usage_bid = record_tts_usage(
                app,
                UsageContext(
                    user_bid="user-1",
                    shifu_bid="shifu-b7",
                    usage_scene=BILL_USAGE_SCENE_PREVIEW,
                    billable=0,
                ),
                provider="minimax",
                model="voice_clone",
                is_stream=False,
                input=1,
                output=0,
                total=1,
                word_count=0,
                duration_ms=0,
                latency_ms=0,
                enqueue_settlement=False,
            )
            assert usage_bid
            usage_bids.append(usage_bid)
            message = "caller failed"
            raise RuntimeError(message)

    with app.app_context():
        with pytest.raises(RuntimeError, match="caller failed"):
            _caller_fails_after_usage_write()

        dao.db.session.expire_all()
        assert DraftShifu.query.filter_by(shifu_bid="b7-usage-caller-1").count() == 0
        assert BillUsageRecord.query.filter_by(usage_bid=usage_bids[0]).count() == 1

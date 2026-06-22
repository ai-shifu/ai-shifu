from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from flaskr.dao import db
from flaskr.service.billing.consts import (
    BILLING_METRIC_TTS_REQUEST_COUNT,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    CreditUsageRate,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.dtos import UserInfo
from flaskr.service.common.models import ERROR_CODE
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW, BILL_USAGE_TYPE_TTS
from flaskr.service.shifu.models import DraftShifu
from flaskr.service.user.consts import USER_STATE_REGISTERED


def _creator_user(user_bid: str = "creator-route") -> UserInfo:
    return UserInfo(
        user_id=user_bid,
        username=user_bid,
        name="Creator",
        email="",
        mobile="",
        user_state=USER_STATE_REGISTERED,
        wx_openid="",
        language="en-US",
        is_creator=True,
    )


def _seed_course_and_wallet(
    *,
    creator_bid: str = "creator-route",
    shifu_bid: str = "shifu-route",
    amount: str = "10.0000000000",
    rate: str | None = None,
) -> None:
    db.session.query(DraftShifu).filter(DraftShifu.shifu_bid == shifu_bid).delete(
        synchronize_session=False
    )
    db.session.query(CreditUsageRate).filter(
        CreditUsageRate.rate_bid == "rate-route-minimax-voice-clone"
    ).delete(synchronize_session=False)
    db.session.query(CreditWalletBucket).filter(
        CreditWalletBucket.creator_bid == creator_bid
    ).delete(synchronize_session=False)
    db.session.query(CreditWallet).filter(
        CreditWallet.creator_bid == creator_bid
    ).delete(synchronize_session=False)

    wallet = CreditWallet(
        wallet_bid=f"wallet-{creator_bid}",
        creator_bid=creator_bid,
        available_credits=Decimal(amount),
        reserved_credits=Decimal("0"),
        lifetime_granted_credits=Decimal(amount),
        lifetime_consumed_credits=Decimal("0"),
        version=0,
    )
    bucket = CreditWalletBucket(
        wallet_bucket_bid=f"bucket-{creator_bid}",
        wallet_bid=wallet.wallet_bid,
        creator_bid=creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
        source_type=0,
        source_bid="manual",
        priority=10,
        original_credits=Decimal(amount),
        available_credits=Decimal(amount),
        reserved_credits=Decimal("0"),
        consumed_credits=Decimal("0"),
        expired_credits=Decimal("0"),
        effective_from=datetime(2026, 1, 1, 0, 0, 0),
        status=CREDIT_BUCKET_STATUS_ACTIVE,
    )
    shifu = DraftShifu(
        shifu_bid=shifu_bid,
        title="Course",
        created_user_bid=creator_bid,
        updated_user_bid=creator_bid,
    )
    rows = [wallet, bucket, shifu]
    if rate is not None:
        rows.append(
            CreditUsageRate(
                rate_bid="rate-route-minimax-voice-clone",
                usage_type=BILL_USAGE_TYPE_TTS,
                provider="minimax",
                model="voice_clone",
                usage_scene=BILL_USAGE_SCENE_PREVIEW,
                billing_metric=BILLING_METRIC_TTS_REQUEST_COUNT,
                unit_size=1,
                credits_per_unit=Decimal(rate),
                rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
                effective_from=datetime(2026, 1, 1, 0, 0, 0),
                status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
            )
        )
    db.session.add_all(rows)
    db.session.commit()


def _prepare_minimax_tables(app) -> None:
    from flaskr.service.tts.models import TTSMiniMaxClonedVoice

    with app.app_context():
        TTSMiniMaxClonedVoice.__table__.create(db.engine, checkfirst=True)


def _auth(monkeypatch, user_bid: str = "creator-route") -> None:
    user = _creator_user(user_bid)
    monkeypatch.setattr("flaskr.route.user.validate_user", lambda *_args: user)
    monkeypatch.setattr("flaskr.service.shifu.route.validate_user", lambda *_args: user)


def test_minimax_voice_clone_cost_is_zero_without_rate(app, test_client, monkeypatch):
    _prepare_minimax_tables(app)
    _auth(monkeypatch)
    monkeypatch.setattr(
        "flaskr.service.billing.admission.is_billing_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "flaskr.service.billing.primitives.is_billing_enabled",
        lambda: True,
    )

    with app.app_context():
        _seed_course_and_wallet(rate=None)

    resp = test_client.get(
        "/api/shifu/tts/minimax/voices/clone-cost",
        query_string={"shifu_bid": "shifu-route"},
        headers={"Token": "test-token"},
    )
    payload = resp.get_json(force=True)

    assert payload["code"] == 0
    assert payload["data"]["estimated_credits"] == "0"
    assert payload["data"]["can_submit"] is True
    assert payload["data"]["billing_enabled"] is True


def test_minimax_validate_custom_voice_id_route(app, test_client, monkeypatch):
    _prepare_minimax_tables(app)
    _auth(monkeypatch)

    resp = test_client.post(
        "/api/shifu/tts/minimax/voices/validate-id",
        json={"voice_id": "AiShifu_route_1"},
        headers={"Token": "test-token"},
    )
    payload = resp.get_json(force=True)

    assert payload["code"] == 0
    assert payload["data"]["valid"] is True


def test_minimax_voice_clone_submit_creates_queued_voice(
    app,
    test_client,
    monkeypatch,
):
    from flaskr.service.tts.models import (
        TTSMiniMaxClonedVoice,
        TTS_MINIMAX_CLONE_STATUS_QUEUED,
    )

    _prepare_minimax_tables(app)
    _auth(monkeypatch)
    monkeypatch.setattr(
        "flaskr.service.billing.admission.is_billing_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "flaskr.service.billing.primitives.is_billing_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone._enqueue_minimax_clone_task",
        lambda _app, *, voice_bid: True,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.minimax_voice_clone._store_resource_bytes",
        lambda app, **kwargs: SimpleNamespace(
            resource_bid=f"res-{kwargs['resource_kind']}",
            url=f"/resource/{kwargs['resource_kind']}",
            object_key=f"key/{kwargs['resource_kind']}",
        ),
    )

    with app.app_context():
        _seed_course_and_wallet(rate="2.0000000000")

    resp = test_client.post(
        "/api/shifu/tts/minimax/voices/clone",
        data={
            "shifu_bid": "shifu-route",
            "display_name": "Route Voice",
            "voice_id": "AiShifu_route_queued_1",
            "source_capture_method": "recording",
            "source_audio": (BytesIO(b"raw-audio"), "recording.webm"),
        },
        headers={"Token": "test-token"},
        content_type="multipart/form-data",
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 202
    assert payload["code"] == 0
    assert payload["data"]["status"] == TTS_MINIMAX_CLONE_STATUS_QUEUED
    with app.app_context():
        row = TTSMiniMaxClonedVoice.query.filter_by(
            voice_id="AiShifu_route_queued_1"
        ).one()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-route").one()
        assert row.status == TTS_MINIMAX_CLONE_STATUS_QUEUED
        assert row.estimated_credits == Decimal("2.0000000000")
        assert wallet.available_credits == Decimal("8.0000000000")
        assert wallet.reserved_credits == Decimal("2.0000000000")


def test_minimax_voice_clone_submit_rejects_insufficient_credits(
    app,
    test_client,
    monkeypatch,
):
    from flaskr.service.tts.models import TTSMiniMaxClonedVoice

    _prepare_minimax_tables(app)
    _auth(monkeypatch)
    monkeypatch.setattr(
        "flaskr.service.billing.admission.is_billing_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "flaskr.service.billing.primitives.is_billing_enabled",
        lambda: True,
    )

    with app.app_context():
        _seed_course_and_wallet(amount="1.0000000000", rate="2.0000000000")

    resp = test_client.post(
        "/api/shifu/tts/minimax/voices/clone",
        data={
            "shifu_bid": "shifu-route",
            "display_name": "Route Voice",
            "voice_id": "AiShifu_route_low_balance",
            "source_capture_method": "recording",
            "source_audio": (BytesIO(b"raw-audio"), "recording.webm"),
        },
        headers={"Token": "test-token"},
        content_type="multipart/form-data",
    )
    payload = resp.get_json(force=True)

    assert payload["code"] == ERROR_CODE["server.billing.creditInsufficient"]
    with app.app_context():
        assert (
            TTSMiniMaxClonedVoice.query.filter_by(
                voice_id="AiShifu_route_low_balance"
            ).count()
            == 0
        )


def test_minimax_voice_routes_only_expose_current_owner_voices(
    app,
    test_client,
    monkeypatch,
):
    from flaskr.service.tts.models import (
        TTSMiniMaxClonedVoice,
        TTS_MINIMAX_CLONE_STATUS_FAILED,
        TTS_MINIMAX_CLONE_STATUS_READY,
    )

    _prepare_minimax_tables(app)
    _auth(monkeypatch, user_bid="creator-route")

    with app.app_context():
        _seed_course_and_wallet(rate=None)
        db.session.query(TTSMiniMaxClonedVoice).filter(
            TTSMiniMaxClonedVoice.shifu_bid == "shifu-route"
        ).delete(synchronize_session=False)
        db.session.add_all(
            [
                TTSMiniMaxClonedVoice(
                    voice_bid="owned-voice-bid",
                    owner_user_bid="creator-route",
                    shifu_bid="shifu-route",
                    display_name="Owned Voice",
                    voice_id="AiShifu_owned_voice",
                    status=TTS_MINIMAX_CLONE_STATUS_READY,
                    minimax_demo_audio_url="https://cdn.example.com/owned.mp3",
                ),
                TTSMiniMaxClonedVoice(
                    voice_bid="other-voice-bid",
                    owner_user_bid="other-creator",
                    shifu_bid="shifu-route",
                    display_name="Other Voice",
                    voice_id="AiShifu_other_voice",
                    status=TTS_MINIMAX_CLONE_STATUS_FAILED,
                ),
            ]
        )
        db.session.commit()

    list_resp = test_client.get(
        "/api/shifu/tts/minimax/voices",
        query_string={"shifu_bid": "shifu-route"},
        headers={"Token": "test-token"},
    )
    list_payload = list_resp.get_json(force=True)

    assert list_payload["code"] == 0
    assert [voice["voice_bid"] for voice in list_payload["data"]["voices"]] == [
        "owned-voice-bid"
    ]
    assert list_payload["data"]["voices"][0]["minimax_demo_audio_url"] == (
        "https://cdn.example.com/owned.mp3"
    )

    for method, path in [
        ("get", "/api/shifu/tts/minimax/voices/other-voice-bid"),
        ("post", "/api/shifu/tts/minimax/voices/other-voice-bid/retry"),
        ("delete", "/api/shifu/tts/minimax/voices/other-voice-bid"),
    ]:
        response = getattr(test_client, method)(
            path,
            headers={"Token": "test-token"},
        )
        payload = response.get_json(force=True)
        assert payload["code"] == ERROR_CODE["server.shifu.noPermission"]

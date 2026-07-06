import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

import flaskr.dao as dao


def _seed_shifu(
    app,
    shifu_bid: str,
    owner_bid: str,
    price: Decimal,
    ask_provider_config: str = "{}",
):
    from flaskr.service.shifu.models import DraftShifu

    with app.app_context():
        DraftShifu.query.filter_by(shifu_bid=shifu_bid).delete()
        dao.db.session.add(
            DraftShifu(
                shifu_bid=shifu_bid,
                title="Test Shifu",
                description="desc",
                avatar_res_bid="res",
                keywords="test",
                llm="gpt-test",
                llm_temperature=Decimal("0.30"),
                llm_system_prompt="",
                ask_enabled_status=5101,
                ask_llm="gpt-ask",
                ask_llm_temperature=Decimal("0.20"),
                ask_llm_system_prompt="",
                ask_provider_config=ask_provider_config,
                price=price,
                created_user_bid=owner_bid,
                updated_user_bid=owner_bid,
            )
        )
        dao.db.session.commit()


def _mock_shifu_permissions(monkeypatch):
    from flaskr.service.shifu import shifu_draft_funcs

    monkeypatch.setattr(
        shifu_draft_funcs,
        "shifu_permission_verification",
        lambda *_args, **_kwargs: True,
        raising=False,
    )
    monkeypatch.setattr(
        shifu_draft_funcs,
        "get_config",
        lambda key: 0.5 if key == "MIN_SHIFU_PRICE" else None,
        raising=False,
    )


def _mock_route_user(monkeypatch, user_id: str):
    from types import SimpleNamespace

    dummy_user = SimpleNamespace(
        user_id=user_id,
        is_creator=True,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: dummy_user,
        raising=False,
    )
    return dummy_user


def _mock_route_permission(monkeypatch, permission_map: dict[str, bool]):
    from flaskr.service.shifu import route

    def _has_permission(_app, _user_id, _shifu_bid, permission: str):
        return permission_map.get(permission, False)

    monkeypatch.setattr(
        route,
        "shifu_permission_verification",
        _has_permission,
        raising=False,
    )


def test_save_shifu_draft_info_keeps_existing_price_when_input_is_none(
    app, monkeypatch
):
    from flaskr.service.shifu import shifu_draft_funcs
    from flaskr.service.shifu.models import DraftShifu

    shifu_bid = "test-save-shifu-none-price"
    owner_bid = "owner-none-price"
    original_price = Decimal("9.99")
    _seed_shifu(app, shifu_bid, owner_bid, original_price)
    _mock_shifu_permissions(monkeypatch)

    result = shifu_draft_funcs.save_shifu_draft_info(
        app=app,
        user_id=owner_bid,
        shifu_id=shifu_bid,
        shifu_name="Test Shifu",
        shifu_description="desc",
        shifu_avatar="res",
        shifu_keywords=["test"],
        shifu_model="gpt-test",
        shifu_temperature=0.3,
        shifu_price=None,
        shifu_system_prompt=None,
        base_url="http://localhost:5000",
    )

    assert result.price == pytest.approx(9.99)

    with app.app_context():
        latest = (
            DraftShifu.query.filter_by(shifu_bid=shifu_bid, deleted=0)
            .order_by(DraftShifu.id.desc())
            .first()
        )
        assert latest is not None
        assert float(latest.price) == pytest.approx(9.99)
        assert DraftShifu.query.filter_by(shifu_bid=shifu_bid, deleted=0).count() == 1


def test_save_and_get_shifu_draft_info_roundtrip_ask_provider_config(app, monkeypatch):
    from flaskr.service.shifu import shifu_draft_funcs
    from flaskr.service.shifu.models import DraftShifu

    shifu_bid = "test-save-shifu-ask-provider-config"
    owner_bid = "owner-ask-provider-config"
    _seed_shifu(app, shifu_bid, owner_bid, Decimal("1.23"))
    _mock_shifu_permissions(monkeypatch)

    ask_provider_config = {
        "provider": "dify",
        "mode": "provider_only",
        "config": {
            "conversation_id": "conv-123",
            "inputs": {"topic": "pricing"},
        },
    }

    result = shifu_draft_funcs.save_shifu_draft_info(
        app=app,
        user_id=owner_bid,
        shifu_id=shifu_bid,
        shifu_name="Test Shifu",
        shifu_description="desc",
        shifu_avatar="res",
        shifu_keywords=["test"],
        shifu_model="gpt-test",
        shifu_temperature=0.3,
        shifu_price=1.23,
        shifu_system_prompt="",
        base_url="http://localhost:5000",
        ask_enabled_status=5103,
        ask_model="gpt-ask-next",
        ask_temperature=0.8,
        ask_system_prompt="ask prompt",
        ask_provider_config=ask_provider_config,
    )

    assert result.ask_enabled_status == 5103
    assert result.ask_model == "gpt-ask-next"
    assert result.ask_temperature == pytest.approx(0.8)
    assert result.ask_system_prompt == "ask prompt"
    assert result.ask_provider_config == ask_provider_config

    with app.app_context():
        latest = (
            DraftShifu.query.filter_by(shifu_bid=shifu_bid, deleted=0)
            .order_by(DraftShifu.id.desc())
            .first()
        )
        assert latest is not None
        assert latest.ask_enabled_status == 5103
        assert latest.ask_llm == "gpt-ask-next"
        assert float(latest.ask_llm_temperature) == pytest.approx(0.8)
        assert latest.ask_llm_system_prompt == "ask prompt"
        assert json.loads(latest.ask_provider_config) == ask_provider_config

    detail = shifu_draft_funcs.get_shifu_draft_info(
        app=app,
        user_id=owner_bid,
        shifu_id=shifu_bid,
        base_url="http://localhost:5000",
    )

    assert detail.ask_enabled_status == 5103
    assert detail.ask_model == "gpt-ask-next"
    assert detail.ask_temperature == pytest.approx(0.8)
    assert detail.ask_system_prompt == "ask prompt"
    assert detail.ask_provider_config == ask_provider_config


def test_save_shifu_draft_info_normalizes_removed_tts_fields(app, monkeypatch):
    from flaskr.service.shifu import shifu_draft_funcs
    from flaskr.service.shifu.models import DraftShifu

    shifu_bid = "test-save-shifu-tts-normalized"
    owner_bid = "owner-tts-normalized"
    _seed_shifu(app, shifu_bid, owner_bid, Decimal("1.23"))
    _mock_shifu_permissions(monkeypatch)

    captured: dict[str, object] = {}

    def _fake_validate_tts_settings_strict(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            provider="minimax",
            model="speech-01-turbo",
            voice_id="voice-1",
            speed=1.2,
            pitch=kwargs["pitch"],
            emotion=kwargs["emotion"],
        )

    monkeypatch.setattr(
        shifu_draft_funcs,
        "validate_tts_settings_strict",
        _fake_validate_tts_settings_strict,
        raising=False,
    )

    shifu_draft_funcs.save_shifu_draft_info(
        app=app,
        user_id=owner_bid,
        shifu_id=shifu_bid,
        shifu_name="Test Shifu",
        shifu_description="desc",
        shifu_avatar="res",
        shifu_keywords=["test"],
        shifu_model="gpt-test",
        shifu_temperature=0.3,
        shifu_price=1.23,
        shifu_system_prompt="",
        base_url="http://localhost:5000",
        tts_enabled=True,
        tts_provider="minimax",
        tts_model="speech-01-turbo",
        tts_voice_id="voice-1",
        tts_speed=1.2,
        tts_pitch=9,
        tts_emotion="happy",
    )

    assert captured["pitch"] == 0
    assert captured["emotion"] == ""

    with app.app_context():
        latest = (
            DraftShifu.query.filter_by(shifu_bid=shifu_bid, deleted=0)
            .order_by(DraftShifu.id.desc())
            .first()
        )
        assert latest is not None
        assert latest.tts_pitch == 0
        assert latest.tts_emotion == ""


def test_get_draft_meta_route_serializes_utc_timestamp(app, test_client, monkeypatch):
    from flaskr.service.shifu.models import DraftOutlineItem

    shifu_bid = "test-draft-meta-timezone"
    owner_bid = "owner-draft-meta-timezone"
    outline_bid = "lesson-draft-meta-timezone"
    _seed_shifu(app, shifu_bid, owner_bid, Decimal("1.00"))
    _mock_route_user(monkeypatch, owner_bid)

    with app.app_context():
        DraftOutlineItem.query.filter_by(
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
        ).delete()
        dao.db.session.add(
            DraftOutlineItem(
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
                title="Lesson",
                content="content",
                updated_user_bid=owner_bid,
                created_user_bid=owner_bid,
                updated_at=datetime(2026, 6, 30, 5, 37, 42),
                created_at=datetime(2026, 6, 30, 5, 37, 42),
            )
        )
        dao.db.session.commit()

    response = test_client.get(
        f"/api/shifu/shifus/{shifu_bid}/draft-meta?outline_bid={outline_bid}",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["updated_at"] == "2026-06-30T05:37:42Z"


def test_get_draft_meta_route_allows_view_only_permission(
    app, test_client, monkeypatch
):
    from flaskr.service.shifu.models import DraftOutlineItem

    shifu_bid = "test-draft-meta-view-only"
    owner_bid = "owner-draft-meta-view-only"
    shared_user_bid = "shared-draft-meta-view-only"
    outline_bid = "lesson-draft-meta-view-only"
    _seed_shifu(app, shifu_bid, owner_bid, Decimal("1.00"))
    _mock_route_user(monkeypatch, shared_user_bid)
    _mock_route_permission(monkeypatch, {"view": True, "edit": False})

    with app.app_context():
        DraftOutlineItem.query.filter_by(
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
        ).delete()
        dao.db.session.add(
            DraftOutlineItem(
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
                title="Lesson",
                content="content",
                updated_user_bid=owner_bid,
                created_user_bid=owner_bid,
                updated_at=datetime(2026, 7, 2, 10, 0, 0),
                created_at=datetime(2026, 7, 2, 10, 0, 0),
            )
        )
        dao.db.session.commit()

    response = test_client.get(
        f"/api/shifu/shifus/{shifu_bid}/draft-meta?outline_bid={outline_bid}",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["updated_at"] == "2026-07-02T10:00:00Z"

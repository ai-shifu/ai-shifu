import json
from decimal import Decimal

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

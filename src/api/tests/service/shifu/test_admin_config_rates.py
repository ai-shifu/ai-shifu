from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flaskr.dao import db
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_CACHE_TOKENS,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import CreditUsageRate
from flaskr.service.billing import rate_references
from flaskr.service.common import credit_rate_references
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_LLM
from flaskr.service.shifu.admin_operations import config_rates


def _credit_rate(
    *,
    rate_bid: str,
    model: str,
    metric: int,
    credits_per_unit: str,
    unit_size: int = 1,
) -> CreditUsageRate:
    return CreditUsageRate(
        rate_bid=rate_bid,
        usage_type=BILL_USAGE_TYPE_LLM,
        provider="qwen",
        model=model,
        usage_scene=BILL_USAGE_SCENE_PROD,
        billing_metric=metric,
        unit_size=unit_size,
        credits_per_unit=Decimal(credits_per_unit),
        rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
        effective_from=datetime(2026, 1, 1, 0, 0, 0),
        effective_to=None,
        status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
    )


def _seed_default_llm_rates() -> None:
    db.session.add_all(
        [
            _credit_rate(
                rate_bid="rate-input",
                model="deepseek-v4-flash",
                metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                credits_per_unit="1",
            ),
            _credit_rate(
                rate_bid="rate-cache",
                model="deepseek-v4-flash",
                metric=BILLING_METRIC_LLM_CACHE_TOKENS,
                credits_per_unit="0.5",
            ),
            _credit_rate(
                rate_bid="rate-output",
                model="deepseek-v4-flash",
                metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                credits_per_unit="3",
            ),
        ]
    )
    db.session.commit()


def test_update_llm_rate_uses_rate_model_and_keeps_metric_ratios(monkeypatch, app):
    def config_getter(key, default=None):
        return {
            "DEFAULT_LLM_MODEL": "qwen/deepseek-v4-flash",
            "LLM_CREDIT_1X_PER_1000_OUTPUT_TOKENS": "3000",
            "TTS_CHARS_PER_LLM_TOKEN": "1",
        }.get(key, default)

    monkeypatch.setattr(config_rates, "get_config", config_getter)
    monkeypatch.setattr(
        credit_rate_references,
        "get_config",
        config_getter,
    )
    monkeypatch.setattr(
        config_rates,
        "get_current_models",
        lambda _app: [
            {
                "model": "qwen/deepseek-v4-flash",
                "display_name": "DeepSeek-V4-Flash",
            }
        ],
    )
    fixed_now = datetime(2026, 7, 20, 13, 30, 43, 990000)
    monkeypatch.setattr(config_rates, "now_utc", lambda: fixed_now)
    monkeypatch.setattr(
        config_rates,
        "_resolve_llm_rate_identity",
        lambda _model: ("qwen", ["deepseek-v4-flash", "qwen/deepseek-v4-flash"]),
    )
    monkeypatch.setattr(
        rate_references,
        "resolve_llm_rate_identity",
        lambda _model: ("qwen", ["deepseek-v4-flash", "qwen/deepseek-v4-flash"]),
    )

    with app.app_context():
        db.session.query(CreditUsageRate).delete()
        _seed_default_llm_rates()

        result = config_rates.update_operator_rate_config(
            app,
            payload={
                "usage_type": "llm",
                "provider": "qwen",
                "model": "qwen/deepseek-v4-flash",
                "rate_model": "deepseek-v4-flash",
                "display_name": "DeepSeek-V4-Flash",
                "billing_metric": "llm_output_tokens",
                "unit_size": 1,
                "credits_per_unit": 12,
                "status": "active",
            },
            operator_user_bid="operator-test",
        )

        config = config_rates.get_operator_rate_config(app)
        row = config["llm_rates"][0]
        rate_change_at = fixed_now.replace(microsecond=0)
        active_rows = {
            rate.billing_metric: rate
            for rate in CreditUsageRate.query.filter(
                CreditUsageRate.deleted == 0,
                CreditUsageRate.status == CREDIT_USAGE_RATE_STATUS_ACTIVE,
                CreditUsageRate.provider == "qwen",
                CreditUsageRate.model == "deepseek-v4-flash",
                CreditUsageRate.effective_from == rate_change_at,
                CreditUsageRate.effective_to.is_(None),
            ).all()
        }
        superseded_rows = CreditUsageRate.query.filter(
            CreditUsageRate.deleted == 0,
            CreditUsageRate.status == CREDIT_USAGE_RATE_STATUS_ACTIVE,
            CreditUsageRate.provider == "qwen",
            CreditUsageRate.model == "deepseek-v4-flash",
            CreditUsageRate.effective_from == datetime(2026, 1, 1, 0, 0, 0),
        ).all()

        assert result["rate_model"] == "deepseek-v4-flash"
        assert result["multiplier"] == 4
        assert row["multiplier"] == 4
        assert active_rows[BILLING_METRIC_LLM_INPUT_TOKENS].credits_per_unit == Decimal(
            "4"
        )
        assert active_rows[BILLING_METRIC_LLM_CACHE_TOKENS].credits_per_unit == Decimal(
            "2.0"
        )
        assert active_rows[
            BILLING_METRIC_LLM_OUTPUT_TOKENS
        ].credits_per_unit == Decimal("12")
        assert active_rows[BILLING_METRIC_LLM_OUTPUT_TOKENS].effective_from == (
            rate_change_at
        )
        assert len(superseded_rows) == 3
        assert {row.status for row in superseded_rows} == {
            CREDIT_USAGE_RATE_STATUS_ACTIVE
        }
        assert {row.effective_to for row in superseded_rows} == {rate_change_at}

        # A second save in the same DB second should update the deterministic
        # version instead of colliding on the rate lookup unique key.
        second_result = config_rates.update_operator_rate_config(
            app,
            payload={
                "usage_type": "llm",
                "provider": "qwen",
                "model": "qwen/deepseek-v4-flash",
                "rate_model": "deepseek-v4-flash",
                "display_name": "DeepSeek-V4-Flash",
                "billing_metric": "llm_output_tokens",
                "unit_size": 1,
                "credits_per_unit": 21,
                "status": "active",
            },
            operator_user_bid="operator-test",
        )
        config = config_rates.get_operator_rate_config(app)
        db.session.expire_all()
        active_output_rows = CreditUsageRate.query.filter(
            CreditUsageRate.deleted == 0,
            CreditUsageRate.status == CREDIT_USAGE_RATE_STATUS_ACTIVE,
            CreditUsageRate.provider == "qwen",
            CreditUsageRate.model == "deepseek-v4-flash",
            CreditUsageRate.billing_metric == BILLING_METRIC_LLM_OUTPUT_TOKENS,
            CreditUsageRate.effective_from == rate_change_at,
            CreditUsageRate.effective_to.is_(None),
        ).all()

        assert second_result["multiplier"] == 7
        assert config["llm_rates"][0]["multiplier"] == 7
        assert len(active_output_rows) == 1
        assert active_output_rows[0].credits_per_unit == Decimal("21")

        db.session.query(CreditUsageRate).delete()
        db.session.commit()


def test_update_new_llm_rate_uses_default_metric_ratios(monkeypatch, app):
    def config_getter(key, default=None):
        return {
            "DEFAULT_LLM_MODEL": "qwen/deepseek-v4-flash",
            "LLM_CREDIT_1X_PER_1000_OUTPUT_TOKENS": "3000",
            "TTS_CHARS_PER_LLM_TOKEN": "1",
        }.get(key, default)

    def resolve_identity(model: str):
        provider, actual_model = model.split("/", 1)
        return provider, [actual_model, model]

    monkeypatch.setattr(config_rates, "get_config", config_getter)
    monkeypatch.setattr(credit_rate_references, "get_config", config_getter)
    monkeypatch.setattr(config_rates, "_resolve_llm_rate_identity", resolve_identity)
    monkeypatch.setattr(rate_references, "resolve_llm_rate_identity", resolve_identity)
    monkeypatch.setattr(
        config_rates,
        "get_current_models",
        lambda _app: [
            {
                "model": "qwen/new-rate-model",
                "display_name": "New Rate Model",
            }
        ],
    )

    with app.app_context():
        db.session.query(CreditUsageRate).delete()
        _seed_default_llm_rates()

        config_rates.update_operator_rate_config(
            app,
            payload={
                "usage_type": "llm",
                "provider": "qwen",
                "model": "qwen/new-rate-model",
                "rate_model": "new-rate-model",
                "display_name": "New Rate Model",
                "billing_metric": "llm_output_tokens",
                "unit_size": 1,
                "credits_per_unit": 12,
                "status": "active",
            },
            operator_user_bid="operator-test",
        )

        active_rows = {
            rate.billing_metric: rate
            for rate in CreditUsageRate.query.filter(
                CreditUsageRate.deleted == 0,
                CreditUsageRate.status == CREDIT_USAGE_RATE_STATUS_ACTIVE,
                CreditUsageRate.provider == "qwen",
                CreditUsageRate.model == "new-rate-model",
            ).all()
        }

        assert active_rows[BILLING_METRIC_LLM_INPUT_TOKENS].credits_per_unit == Decimal(
            "4"
        )
        assert active_rows[BILLING_METRIC_LLM_CACHE_TOKENS].credits_per_unit == Decimal(
            "2"
        )
        assert active_rows[
            BILLING_METRIC_LLM_OUTPUT_TOKENS
        ].credits_per_unit == Decimal("12")

        db.session.query(CreditUsageRate).delete()
        db.session.commit()


def test_operator_rate_config_exposes_fixed_credit_1x_baseline(monkeypatch, app):
    def config_getter(key, default=None):
        return {
            "DEFAULT_LLM_MODEL": "ark/doubao-seed-2-0-lite-260428",
            "LLM_CREDIT_1X_PER_1000_OUTPUT_TOKENS": "0.066667",
            "TTS_CHARS_PER_LLM_TOKEN": "0.216",
        }.get(key, default)

    monkeypatch.setattr(config_rates, "get_config", config_getter)
    monkeypatch.setattr(credit_rate_references, "get_config", config_getter)
    monkeypatch.setattr(
        config_rates,
        "get_current_models",
        lambda _app: [
            {
                "model": "qwen/deepseek-v4-flash",
                "display_name": "DeepSeek-V4-Flash",
            }
        ],
    )
    monkeypatch.setattr(config_rates, "get_all_provider_configs", lambda: {})
    monkeypatch.setattr(
        config_rates,
        "_resolve_llm_rate_identity",
        lambda _model: ("qwen", ["deepseek-v4-flash", "qwen/deepseek-v4-flash"]),
    )

    with app.app_context():
        db.session.query(CreditUsageRate).delete()
        _seed_default_llm_rates()

        config = config_rates.get_operator_rate_config(app)

        assert config["baseline"]["default_llm_model"] == (
            "ark/doubao-seed-2-0-lite-260428"
        )
        assert config["baseline"]["per_1000_output_tokens"] == 0.066667
        assert config["baseline"]["unit_cost"] == 0.000066667
        assert config["baseline"]["is_configured"] is True
        assert config["llm_rates"][0]["multiplier"] == 44999.78

        db.session.query(CreditUsageRate).delete()
        db.session.commit()


def test_update_rate_rejects_missing_credit_1x_anchor(monkeypatch, app):
    def config_getter(key, default=None):
        return {
            "DEFAULT_LLM_MODEL": "qwen/deepseek-v4-flash",
            "TTS_CHARS_PER_LLM_TOKEN": "1",
        }.get(key, default)

    monkeypatch.setattr(config_rates, "get_config", config_getter)
    monkeypatch.setattr(credit_rate_references, "get_config", config_getter)
    monkeypatch.setattr(
        config_rates,
        "_resolve_llm_rate_identity",
        lambda _model: ("qwen", ["deepseek-v4-flash", "qwen/deepseek-v4-flash"]),
    )

    with app.app_context():
        db.session.query(CreditUsageRate).delete()
        _seed_default_llm_rates()

        try:
            config_rates.update_operator_rate_config(
                app,
                payload={
                    "usage_type": "llm",
                    "provider": "qwen",
                    "model": "qwen/deepseek-v4-flash",
                    "rate_model": "deepseek-v4-flash",
                    "display_name": "DeepSeek-V4-Flash",
                    "billing_metric": "llm_output_tokens",
                    "unit_size": 1,
                    "credits_per_unit": 12,
                    "status": "active",
                },
                operator_user_bid="operator-test",
            )
        except Exception as exc:
            assert "llm_credit_1x_per_1000_output_tokens" in str(exc)
        else:
            raise AssertionError("missing 1x anchor should reject save")

        assert CreditUsageRate.query.count() == 3
        assert {rate.effective_to for rate in CreditUsageRate.query.all()} == {None}

        db.session.query(CreditUsageRate).delete()
        db.session.commit()

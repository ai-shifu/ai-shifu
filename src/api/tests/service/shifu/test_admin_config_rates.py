"""Verify admin config rates behavior."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from flaskr.dao import db
from flaskr.service.billing import rate_references
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_CACHE_TOKENS,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_METRIC_TTS_OUTPUT_CHARS,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
    CREDIT_USAGE_RATE_STATUS_INACTIVE,
)
from flaskr.service.billing.models import CreditUsageRate
from flaskr.service.common import credit_rate_references
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.shifu.admin_operations import config_rates
from sqlalchemy import event


def _credit_rate(
    *,
    rate_bid: str,
    model: str,
    metric: int,
    credits_per_unit: str,
    unit_size: int = 1,
    usage_type: int = BILL_USAGE_TYPE_LLM,
    provider: str = "qwen",
    effective_from: datetime = datetime(2026, 1, 1, 0, 0, 0),
    effective_to: datetime | None = None,
    status: int = CREDIT_USAGE_RATE_STATUS_ACTIVE,
    deleted: int = 0,
) -> CreditUsageRate:
    return CreditUsageRate(
        rate_bid=rate_bid,
        usage_type=usage_type,
        provider=provider,
        model=model,
        usage_scene=BILL_USAGE_SCENE_PROD,
        billing_metric=metric,
        unit_size=unit_size,
        credits_per_unit=Decimal(credits_per_unit),
        rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
        effective_from=effective_from,
        effective_to=effective_to,
        status=status,
        deleted=deleted,
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


def test_update_llm_rate_uses_rate_model_and_keeps_metric_ratios(
    monkeypatch: pytest.MonkeyPatch, app: object
) -> None:
    def config_getter(key: object, default: object | None = None) -> object:
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
        alias_output = _credit_rate(
            rate_bid="rate-output-alias",
            model="qwen/deepseek-v4-flash",
            metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
            credits_per_unit="30",
        )
        db.session.add(alias_output)
        db.session.commit()

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
            4
        )
        assert active_rows[BILLING_METRIC_LLM_CACHE_TOKENS].credits_per_unit == Decimal(
            "2.0"
        )
        assert active_rows[
            BILLING_METRIC_LLM_OUTPUT_TOKENS
        ].credits_per_unit == Decimal(12)
        assert active_rows[BILLING_METRIC_LLM_OUTPUT_TOKENS].effective_from == (
            rate_change_at
        )
        assert len(superseded_rows) == 3
        assert {row.status for row in superseded_rows} == {
            CREDIT_USAGE_RATE_STATUS_ACTIVE
        }
        assert {row.effective_to for row in superseded_rows} == {rate_change_at}
        db.session.refresh(alias_output)
        assert alias_output.effective_to is None

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
        assert active_output_rows[0].credits_per_unit == Decimal(21)
        db.session.refresh(alias_output)
        assert alias_output.effective_to is None

        db.session.query(CreditUsageRate).delete()
        db.session.commit()


def test_update_db_only_llm_alias_only_supersedes_explicit_alias(
    monkeypatch: pytest.MonkeyPatch, app: object
) -> None:
    fixed_now = datetime(2026, 7, 20, 13, 30, 43, 990000)
    monkeypatch.setattr(config_rates, "now_utc", lambda: fixed_now)
    monkeypatch.setattr(
        config_rates, "_load_llm_credit_1x_reference_cost", lambda: Decimal(3)
    )
    monkeypatch.setattr(config_rates, "get_config", lambda _key, default=None: default)
    monkeypatch.setattr(
        config_rates,
        "_resolve_llm_rate_identity",
        lambda _model: ("qwen", ["qwen/foo", "qwen/qwen/foo"]),
    )

    with app.app_context():
        db.session.query(CreditUsageRate).delete()
        raw_output = _credit_rate(
            rate_bid="raw-output",
            provider="qwen",
            model="foo",
            metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
            credits_per_unit="3",
        )
        alias_output = _credit_rate(
            rate_bid="alias-output",
            provider="qwen",
            model="qwen/foo",
            metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
            credits_per_unit="6",
        )
        db.session.add_all([raw_output, alias_output])
        db.session.commit()

        result = config_rates.update_operator_rate_config(
            app,
            payload={
                "usage_type": "llm",
                "provider": "qwen",
                "model": "qwen/qwen/foo",
                "rate_model": "qwen/foo",
                "display_name": "qwen/qwen/foo",
                "billing_metric": "llm_output_tokens",
                "unit_size": 1,
                "credits_per_unit": 12,
                "status": "active",
            },
            operator_user_bid="operator-test",
        )

        rate_change_at = fixed_now.replace(microsecond=0)
        active_alias_rows = {
            row.billing_metric: row
            for row in CreditUsageRate.query.filter(
                CreditUsageRate.provider == "qwen",
                CreditUsageRate.model == "qwen/foo",
                CreditUsageRate.effective_from == rate_change_at,
                CreditUsageRate.effective_to.is_(None),
            ).all()
        }
        db.session.refresh(raw_output)
        db.session.refresh(alias_output)

        assert result["rate_model"] == "qwen/foo"
        assert raw_output.deleted == 0
        assert raw_output.status == CREDIT_USAGE_RATE_STATUS_ACTIVE
        assert raw_output.effective_to is None
        assert alias_output.effective_to == rate_change_at
        assert set(active_alias_rows) == {
            BILLING_METRIC_LLM_INPUT_TOKENS,
            BILLING_METRIC_LLM_CACHE_TOKENS,
            BILLING_METRIC_LLM_OUTPUT_TOKENS,
        }
        assert active_alias_rows[
            BILLING_METRIC_LLM_OUTPUT_TOKENS
        ].credits_per_unit == Decimal(12)

        db.session.query(CreditUsageRate).delete()
        db.session.commit()


def test_update_new_llm_rate_uses_default_metric_ratios(
    monkeypatch: pytest.MonkeyPatch, app: object
) -> None:
    def config_getter(key: object, default: object | None = None) -> object:
        return {
            "DEFAULT_LLM_MODEL": "qwen/deepseek-v4-flash",
            "LLM_CREDIT_1X_PER_1000_OUTPUT_TOKENS": "3000",
            "TTS_CHARS_PER_LLM_TOKEN": "1",
        }.get(key, default)

    def resolve_identity(model: str) -> tuple[object, list[object]]:
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
            4
        )
        assert active_rows[BILLING_METRIC_LLM_CACHE_TOKENS].credits_per_unit == Decimal(
            2
        )
        assert active_rows[
            BILLING_METRIC_LLM_OUTPUT_TOKENS
        ].credits_per_unit == Decimal(12)

        db.session.query(CreditUsageRate).delete()
        db.session.commit()


def test_operator_rate_config_exposes_fixed_credit_1x_baseline(
    monkeypatch: pytest.MonkeyPatch, app: object
) -> None:
    def config_getter(key: object, default: object | None = None) -> object:
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
    monkeypatch.setattr(config_rates, "get_all_provider_configs", dict)
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


def test_update_rate_rejects_missing_credit_1x_anchor(
    monkeypatch: pytest.MonkeyPatch, app: object
) -> None:
    def config_getter(key: object, default: object | None = None) -> object:
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

        with pytest.raises(AppError) as exc_info:
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

        assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]

        assert CreditUsageRate.query.count() == 3
        assert {rate.effective_to for rate in CreditUsageRate.query.all()} == {None}

        db.session.query(CreditUsageRate).delete()
        db.session.commit()


def test_operator_rate_config_appends_only_current_exact_db_identities(
    monkeypatch: pytest.MonkeyPatch, app: object
) -> None:
    fixed_now = datetime(2026, 7, 21, 12, 0, 0)
    monkeypatch.setattr(config_rates, "now_utc", lambda: fixed_now)
    monkeypatch.setattr(
        config_rates, "_load_llm_credit_1x_reference_cost", lambda: Decimal(1)
    )
    monkeypatch.setattr(
        config_rates,
        "load_llm_credit_1x_per_1000_output_tokens",
        lambda: Decimal(1000),
    )
    monkeypatch.setattr(
        config_rates, "_load_tts_chars_per_llm_token", lambda: Decimal(1)
    )
    monkeypatch.setattr(config_rates, "get_config", lambda _key, default=None: default)
    monkeypatch.setattr(
        config_rates,
        "get_current_models",
        lambda _app: [
            {"model": "qwen/runtime", "display_name": "Runtime"},
            {"model": "qwen/foo", "display_name": "Foo"},
        ],
    )
    monkeypatch.setattr(
        config_rates,
        "_resolve_llm_rate_identity",
        lambda model: ("qwen", [model.removeprefix("qwen/"), model]),
    )
    monkeypatch.setattr(
        config_rates,
        "get_all_provider_configs",
        lambda: {
            "model_options": [
                {"provider": "voice", "model": "voice-1", "label": "Voice 1"}
            ]
        },
    )

    with app.app_context():
        db.session.query(CreditUsageRate).delete()
        db.session.add_all(
            [
                _credit_rate(
                    rate_bid="runtime",
                    provider="qwen",
                    model="runtime",
                    metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    credits_per_unit="2",
                ),
                _credit_rate(
                    rate_bid="runtime-alias",
                    provider="qwen",
                    model="qwen/runtime",
                    metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    credits_per_unit="2",
                ),
                _credit_rate(
                    rate_bid="foo-alias",
                    provider="qwen",
                    model="qwen/foo",
                    metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    credits_per_unit="2",
                ),
                _credit_rate(
                    rate_bid="custom-b",
                    provider="custom-b",
                    model="beta",
                    metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    credits_per_unit="3",
                ),
                _credit_rate(
                    rate_bid="custom-a",
                    provider="custom-a",
                    model="alpha",
                    metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    credits_per_unit="4",
                ),
                _credit_rate(
                    rate_bid="wild-provider",
                    provider="*",
                    model="fallback",
                    metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    credits_per_unit="5",
                ),
                _credit_rate(
                    rate_bid="wild-model",
                    provider="custom",
                    model="*",
                    metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    credits_per_unit="5",
                ),
                _credit_rate(
                    rate_bid="historical",
                    provider="custom",
                    model="historical",
                    metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    credits_per_unit="5",
                    effective_to=fixed_now - timedelta(seconds=1),
                ),
                _credit_rate(
                    rate_bid="inactive",
                    provider="custom",
                    model="inactive",
                    metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    credits_per_unit="5",
                    status=CREDIT_USAGE_RATE_STATUS_INACTIVE,
                ),
                _credit_rate(
                    rate_bid="deleted",
                    provider="custom",
                    model="deleted",
                    metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    credits_per_unit="5",
                    deleted=1,
                ),
                _credit_rate(
                    rate_bid="future",
                    provider="custom",
                    model="future",
                    metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    credits_per_unit="5",
                    effective_from=fixed_now + timedelta(seconds=1),
                ),
                _credit_rate(
                    rate_bid="tts-default",
                    usage_type=BILL_USAGE_TYPE_TTS,
                    provider="custom-tts",
                    model="",
                    metric=BILLING_METRIC_TTS_OUTPUT_CHARS,
                    credits_per_unit="0.5",
                ),
            ]
        )
        db.session.commit()

        active_rate_selects = 0

        def count_active_rate_selects(
            _connection: object,
            _cursor: object,
            statement: object,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            nonlocal active_rate_selects
            if "credit_usage_rates" in statement.lower():
                active_rate_selects += 1

        engine = db.engine
        event.listen(engine, "before_cursor_execute", count_active_rate_selects)
        try:
            result = config_rates.get_operator_rate_config(app)
        finally:
            event.remove(engine, "before_cursor_execute", count_active_rate_selects)

        assert [
            (row["provider"], row["rate_model"], row["display_name"])
            for row in result["llm_rates"]
        ] == [
            ("qwen", "runtime", "Runtime"),
            ("qwen", "foo", "Foo"),
            ("custom-a", "alpha", "custom-a/alpha"),
            ("custom-b", "beta", "custom-b/beta"),
            ("qwen", "qwen/runtime", "qwen/qwen/runtime"),
        ]
        assert result["llm_rates"][0]["rate_bid"] == "runtime"
        assert result["llm_rates"][0]["source"] == "exact"
        assert result["llm_rates"][0]["rate_model"] == "runtime"
        assert (
            result["llm_rates"][0]["matched_rate_provider"],
            result["llm_rates"][0]["matched_rate_model"],
        ) == ("qwen", "runtime")
        assert result["llm_rates"][1]["rate_bid"] == "foo-alias"
        assert result["llm_rates"][1]["source"] == "exact"
        assert result["llm_rates"][1]["rate_model"] == "foo"
        assert (
            result["llm_rates"][1]["matched_rate_provider"],
            result["llm_rates"][1]["matched_rate_model"],
        ) == ("qwen", "qwen/foo")
        assert result["llm_rates"][2]["rate_bid"] == "custom-a"
        assert result["llm_rates"][3]["rate_bid"] == "custom-b"
        assert result["llm_rates"][4]["rate_bid"] == "runtime-alias"
        assert result["llm_rates"][4]["source"] == "exact"
        assert (
            result["llm_rates"][4]["matched_rate_provider"],
            result["llm_rates"][4]["matched_rate_model"],
        ) == ("qwen", "qwen/runtime")
        assert [
            (row["provider"], row["rate_model"], row["display_name"])
            for row in result["tts_rates"]
        ] == [
            ("voice", "voice-1", "Voice 1"),
            ("custom-tts", "", "custom-tts"),
        ]
        assert (
            result["tts_rates"][0]["matched_rate_provider"],
            result["tts_rates"][0]["matched_rate_model"],
        ) == (None, None)
        assert result["tts_rates"][1]["rate_bid"] == "tts-default"
        assert (
            result["tts_rates"][1]["matched_rate_provider"],
            result["tts_rates"][1]["matched_rate_model"],
        ) == ("custom-tts", "")
        assert active_rate_selects == 1

        db.session.query(CreditUsageRate).delete()
        db.session.commit()


@pytest.mark.parametrize(
    ("credits_per_unit", "expected_input", "expected_cache"),
    [
        (Decimal(12), Decimal(3), Decimal("1.5")),
        (Decimal("0.25"), Decimal("0.0625"), Decimal("0.03125")),
        (
            Decimal("0.0001000005"),
            Decimal("0.0000250001"),
            Decimal("0.0000125001"),
        ),
        (
            Decimal("0.0000000004"),
            Decimal("0.0000000001"),
            Decimal("0.0000000001"),
        ),
    ],
    ids=["whole-number", "fractional", "anchor-1.5x", "half-up-boundary"],
)
def test_create_only_llm_uses_raw_rate_model_without_superseding_alias(
    monkeypatch: pytest.MonkeyPatch,
    app: object,
    credits_per_unit: object,
    expected_input: object,
    expected_cache: object,
) -> None:
    fixed_now = datetime(2026, 7, 21, 12, 0, 0)
    monkeypatch.setattr(config_rates, "now_utc", lambda: fixed_now)
    monkeypatch.setattr(
        config_rates, "_load_llm_credit_1x_reference_cost", lambda: Decimal(3)
    )
    monkeypatch.setattr(config_rates, "get_config", lambda _key, default=None: default)
    monkeypatch.setattr(
        config_rates,
        "_resolve_llm_rate_identity",
        lambda _model: ("custom", ["new-model", "custom/new-model"]),
    )

    with app.app_context():
        db.session.query(CreditUsageRate).delete()
        alias_rate = _credit_rate(
            rate_bid="alias-output",
            provider="custom",
            model="custom/new-model",
            metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
            credits_per_unit="3",
        )
        db.session.add(alias_rate)
        db.session.commit()

        result = config_rates.update_operator_rate_config(
            app,
            payload={
                "create_only": True,
                "usage_type": "llm",
                "provider": "custom",
                "model": "custom/new-model",
                "rate_model": "new-model",
                "billing_metric": "llm_output_tokens",
                "unit_size": 1,
                "credits_per_unit": credits_per_unit,
                "status": "active",
            },
            operator_user_bid="operator-test",
        )

        created = {
            row.billing_metric: row
            for row in CreditUsageRate.query.filter(
                CreditUsageRate.provider == "custom",
                CreditUsageRate.model == "new-model",
            ).all()
        }
        db.session.refresh(alias_rate)

        assert result["rate_model"] == "new-model"
        assert set(created) == {
            BILLING_METRIC_LLM_INPUT_TOKENS,
            BILLING_METRIC_LLM_CACHE_TOKENS,
            BILLING_METRIC_LLM_OUTPUT_TOKENS,
        }
        assert (
            created[BILLING_METRIC_LLM_INPUT_TOKENS].credits_per_unit == expected_input
        )
        assert (
            created[BILLING_METRIC_LLM_CACHE_TOKENS].credits_per_unit == expected_cache
        )
        assert (
            created[BILLING_METRIC_LLM_OUTPUT_TOKENS].credits_per_unit
            == credits_per_unit
        )
        assert alias_rate.effective_to is None

        db.session.query(CreditUsageRate).delete()
        db.session.commit()


def test_create_only_rejects_duplicate_active_exact_identity(
    monkeypatch: pytest.MonkeyPatch, app: object
) -> None:
    fixed_now = datetime(2026, 7, 21, 12, 0, 0)
    monkeypatch.setattr(config_rates, "now_utc", lambda: fixed_now)
    monkeypatch.setattr(
        config_rates, "_load_llm_credit_1x_reference_cost", lambda: Decimal(3)
    )
    monkeypatch.setattr(
        config_rates,
        "_resolve_llm_rate_identity",
        lambda _model: ("custom", ["new-model", "custom/new-model"]),
    )

    with app.app_context():
        db.session.query(CreditUsageRate).delete()
        db.session.add(
            _credit_rate(
                rate_bid="existing-output",
                provider="custom",
                model="new-model",
                metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                credits_per_unit="3",
            )
        )
        db.session.commit()

        with pytest.raises(AppError) as exc_info:
            config_rates.update_operator_rate_config(
                app,
                payload={
                    "create_only": True,
                    "usage_type": "llm",
                    "provider": "custom",
                    "model": "custom/new-model",
                    "rate_model": "new-model",
                    "billing_metric": "llm_output_tokens",
                    "unit_size": 1,
                    "credits_per_unit": 12,
                    "status": "active",
                },
                operator_user_bid="operator-test",
            )

        assert (
            exc_info.value.code == ERROR_CODE["server.billing.rateConfigAlreadyExists"]
        )
        assert CreditUsageRate.query.count() == 1
        assert CreditUsageRate.query.one().effective_to is None

        db.session.query(CreditUsageRate).delete()
        db.session.commit()


@pytest.mark.parametrize(
    "overrides",
    [
        {"create_only": "true"},
        {"provider": "*"},
        {"provider": "p" * 33},
        {"provider": "custom\nprovider"},
        {"rate_model": "*"},
        {"rate_model": "m" * 101},
        {"model": "", "rate_model": ""},
        {"unit_size": "invalid"},
        {"unit_size": 2},
        {"billing_metric": "llm_input_tokens"},
        {"status": "inactive"},
        {"credits_per_unit": "NaN"},
        {"credits_per_unit": "Infinity"},
        {"credits_per_unit": "0.00000000001"},
        {"credits_per_unit": "10000000000"},
        pytest.param(
            {"credits_per_unit": "0.0000000001"},
            id="tiny-output-derived-rate",
        ),
    ],
)
def test_create_only_rejects_invalid_identity_and_fixed_fields(
    monkeypatch: pytest.MonkeyPatch, app: object, overrides: object
) -> None:
    monkeypatch.setattr(
        config_rates, "_load_llm_credit_1x_reference_cost", lambda: Decimal(3)
    )
    monkeypatch.setattr(
        config_rates,
        "_resolve_llm_rate_identity",
        lambda _model: ("custom", ["new-model", "custom/new-model"]),
    )
    payload = {
        "create_only": True,
        "usage_type": "llm",
        "provider": "custom",
        "model": "custom/new-model",
        "rate_model": "new-model",
        "billing_metric": "llm_output_tokens",
        "unit_size": 1,
        "credits_per_unit": 12,
        "status": "active",
    }
    payload.update(overrides)

    with app.app_context(), pytest.raises(AppError) as exc_info:
        config_rates.update_operator_rate_config(
            app,
            payload=payload,
            operator_user_bid="operator-test",
        )

    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


@pytest.mark.parametrize(
    "credits_per_unit",
    ["0.5", "9999999999.9999999999"],
    ids=["regular", "numeric-max"],
)
def test_create_only_tts_allows_empty_default_model(
    monkeypatch: pytest.MonkeyPatch, app: object, credits_per_unit: object
) -> None:
    fixed_now = datetime(2026, 7, 21, 12, 0, 0)
    monkeypatch.setattr(config_rates, "now_utc", lambda: fixed_now)
    monkeypatch.setattr(
        config_rates, "_load_llm_credit_1x_reference_cost", lambda: Decimal(3)
    )
    monkeypatch.setattr(
        config_rates, "_load_tts_chars_per_llm_token", lambda: Decimal(1)
    )

    with app.app_context():
        db.session.query(CreditUsageRate).delete()

        result = config_rates.update_operator_rate_config(
            app,
            payload={
                "create_only": True,
                "usage_type": "tts",
                "provider": "custom-tts",
                "model": "",
                "rate_model": "",
                "billing_metric": "tts_output_chars",
                "unit_size": 1,
                "credits_per_unit": credits_per_unit,
                "status": "active",
            },
            operator_user_bid="operator-test",
        )

        row = CreditUsageRate.query.one()
        assert result["rate_model"] == ""
        assert row.provider == "custom-tts"
        assert row.model == ""
        assert row.billing_metric == BILLING_METRIC_TTS_OUTPUT_CHARS

        db.session.query(CreditUsageRate).delete()
        db.session.commit()

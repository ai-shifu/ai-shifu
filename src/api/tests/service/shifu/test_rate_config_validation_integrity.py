"""Reject invalid rate writes atomically and retain provider-level TTS pricing."""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.billing.consts import (
    BILLING_METRIC_TTS_OUTPUT_CHARS,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import CreditUsageRate
from flaskr.service.common.models import AppError
from flaskr.service.metering.consts import BILL_USAGE_TYPE_TTS
from flaskr.service.shifu.admin_operations import config_rates as rates


@pytest.fixture
def rate_scope(app: object, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    provider = uuid.uuid4().hex
    monkeypatch.setattr(
        rates, "_load_llm_credit_1x_reference_cost", lambda: Decimal("0.002")
    )
    monkeypatch.setattr(
        rates, "load_llm_credit_1x_per_1000_output_tokens", lambda: Decimal(2)
    )
    monkeypatch.setattr(rates, "get_current_models", lambda _app: [])
    monkeypatch.setattr(
        rates, "get_all_provider_configs", lambda: {"model_options": []}
    )
    with app.app_context():
        yield provider
        db.session.rollback()
        CreditUsageRate.query.filter_by(provider=provider).delete()
        db.session.commit()


def _payload(default_provider: str, **overrides: object) -> dict:
    return {
        "create_only": True,
        "usage_type": "tts",
        "billing_metric": "tts_output_chars",
        "provider": default_provider,
        "model": "voice",
        "unit_size": 1,
        "credits_per_unit": "0.002",
        "status": "active",
        **overrides,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"usage_type": None},
        {"usage_type": "unknown"},
        {"usage_type": 999},
        {"billing_metric": None},
        {"billing_metric": "unknown"},
        {"billing_metric": 999},
        {"billing_metric": "llm_output_tokens"},
        {"create_only": "true"},
        {"provider": ""},
        {"provider": "x" * 51},
        {"model": "x" * 101},
        {"model": "wild*card"},
        {"provider": "hidden\x00provider"},
        {"unit_size": "not a number"},
        {"unit_size": 2},
        {"unit_size": "NaN"},
        {"credits_per_unit": "invalid"},
        {"credits_per_unit": "NaN"},
        {"credits_per_unit": "Infinity"},
        {"credits_per_unit": "-1"},
        {"credits_per_unit": "0"},
        {"credits_per_unit": "0.00000000001"},
        {"credits_per_unit": "1E100"},
        {"status": "inactive"},
        {"status": {"bad": "status"}},
        {"status": 999},
    ],
)
def test_invalid_rate_payload_is_rejected_without_persisting_any_rate(
    app: object, rate_scope: str, overrides: dict
) -> None:
    payload = _payload(rate_scope, **overrides)
    before = CreditUsageRate.query.count()
    with pytest.raises(AppError) as caught:
        rates.update_operator_rate_config(
            app, payload=payload, operator_user_bid="operator"
        )
    assert caught.value.code == 2001
    assert CreditUsageRate.query.count() == before


@pytest.mark.parametrize("baseline", [None, Decimal(0)])
def test_rate_write_requires_configured_positive_baseline(
    app: object,
    rate_scope: str,
    monkeypatch: pytest.MonkeyPatch,
    baseline: Decimal | None,
) -> None:
    monkeypatch.setattr(rates, "_load_llm_credit_1x_reference_cost", lambda: baseline)
    with pytest.raises(AppError) as caught:
        rates.update_operator_rate_config(
            app, payload=_payload(rate_scope), operator_user_bid="operator"
        )
    assert caught.value.code == 2001
    assert CreditUsageRate.query.filter_by(provider=rate_scope).count() == 0


def test_provider_wide_tts_rate_accepts_numeric_contract_and_explicit_empty_rate_model(
    app: object, rate_scope: str
) -> None:
    result = rates.update_operator_rate_config(
        app,
        payload=_payload(
            rate_scope,
            usage_type=BILL_USAGE_TYPE_TTS,
            billing_metric=BILLING_METRIC_TTS_OUTPUT_CHARS,
            rate_model="",
            unit_size=None,
            status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
        ),
        operator_user_bid="operator",
    )
    row = CreditUsageRate.query.filter_by(provider=rate_scope).one()
    assert row.model == ""
    assert row.unit_size == 1
    assert row.credits_per_unit == Decimal("0.002")
    assert row.effective_from.microsecond == 0
    assert result["source"] == "exact"
    assert result["provider"] == rate_scope
    assert result["rate_model"] == ""


def test_failure_building_rate_response_rolls_back_new_pricing_rows(
    app: object, rate_scope: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    render = Mock(side_effect=RuntimeError("response lookup failed"))
    monkeypatch.setattr(rates, "_serialize_rate_row", render)
    with pytest.raises(RuntimeError, match="response lookup failed"):
        rates.update_operator_rate_config(
            app, payload=_payload(rate_scope), operator_user_bid="operator"
        )
    assert CreditUsageRate.query.filter_by(provider=rate_scope).count() == 0
    render.assert_called_once()
    assert render.call_args.kwargs["provider"] == rate_scope


def test_rate_catalog_ignores_incomplete_and_duplicate_options(
    app: object, rate_scope: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        rates,
        "get_current_models",
        lambda _app: [
            {"model": ""},
            {"model": "voice"},
            {"model": "voice"},
        ],
    )
    monkeypatch.setattr(
        rates, "_resolve_llm_rate_identity", lambda _model: (rate_scope, ["voice"])
    )
    monkeypatch.setattr(
        rates,
        "get_all_provider_configs",
        lambda: {
            "model_options": [
                {"provider": "", "model": "unknown"},
                {"provider": rate_scope, "model": "voice"},
                {"provider": rate_scope, "model": "voice"},
            ]
        },
    )
    llm = rates._build_llm_rows(app, Decimal("0.002"), {})
    tts = rates._build_tts_rows(Decimal("0.002"), {})
    assert [(item["provider"], item["model"]) for item in llm] == [
        (rate_scope, "voice")
    ]
    assert [(item["provider"], item["model"]) for item in tts] == [
        (rate_scope, "voice")
    ]
    assert llm[0]["source"] == tts[0]["source"] == "unconfigured"

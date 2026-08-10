from __future__ import annotations

import unicodedata
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from flask import Flask
from flaskr.api.llm import get_current_models
from flaskr.api.tts import get_all_provider_configs
from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.billing.consts import (
    BILLING_METRIC_LABELS,
    BILLING_METRIC_LLM_CACHE_TOKENS,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_METRIC_TTS_OUTPUT_CHARS,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
    CREDIT_USAGE_RATE_STATUS_INACTIVE,
    CREDIT_USAGE_RATE_STATUS_LABELS,
)
from flaskr.service.billing.models import CreditUsageRate
from flaskr.service.common.credit_rate_references import (
    load_llm_credit_1x_per_1000_output_tokens,
    load_llm_credit_1x_unit_cost,
)
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.config.funcs import get_config
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.util import generate_id
from flaskr.util.datetime import now_utc, to_utc_iso

_RATE_METRICS = {
    BILL_USAGE_TYPE_LLM: (
        BILLING_METRIC_LLM_INPUT_TOKENS,
        BILLING_METRIC_LLM_CACHE_TOKENS,
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
    ),
    BILL_USAGE_TYPE_TTS: (BILLING_METRIC_TTS_OUTPUT_CHARS,),
}
_USAGE_TYPE_LABELS = {
    BILL_USAGE_TYPE_LLM: "llm",
    BILL_USAGE_TYPE_TTS: "tts",
}
_USAGE_TYPE_CODES = {value: key for key, value in _USAGE_TYPE_LABELS.items()}
_SCENE_LABELS = {BILL_USAGE_SCENE_PROD: "production"}
_METRIC_CODES = {value: key for key, value in BILLING_METRIC_LABELS.items()}
_LLM_MISSING_RATE_FALLBACK_RATIOS = {
    BILLING_METRIC_LLM_INPUT_TOKENS: Decimal("0.25"),
    BILLING_METRIC_LLM_CACHE_TOKENS: Decimal("0.125"),
    BILLING_METRIC_LLM_OUTPUT_TOKENS: Decimal(1),
}
_PROVIDER_MAX_LENGTH = 32
_MODEL_MAX_LENGTH = 100
_CREDITS_PER_UNIT_QUANTIZER = Decimal("0.0000000001")
_CREDITS_PER_UNIT_MAX = Decimal("9999999999.9999999999")
_ActiveRateIndex = dict[tuple[int, int, str, str], CreditUsageRate]


def _rate_effective_now():
    # MySQL DATETIME columns in this schema do not keep fractional seconds.
    # Truncate before writing so a just-saved rate is immediately readable and
    # repeated saves in one second hit the same deterministic version.
    return now_utc().replace(microsecond=0)


def _decimal(value: Any, *, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, TypeError, ValueError):
        raise_param_error(field_name)
    if not result.is_finite() or result < 0:
        raise_param_error(field_name)
    return result


def _validate_create_only_credits_per_unit(value: Decimal) -> None:
    try:
        quantized = value.quantize(_CREDITS_PER_UNIT_QUANTIZER)
    except InvalidOperation:
        raise_param_error("credits_per_unit")
    if value <= 0 or quantized != value or value > _CREDITS_PER_UNIT_MAX:
        raise_param_error("credits_per_unit")


def _quantize_derived_credits_per_unit(value: Decimal) -> Decimal:
    try:
        return value.quantize(
            _CREDITS_PER_UNIT_QUANTIZER,
            rounding=ROUND_HALF_UP,
        )
    except InvalidOperation:
        raise_param_error("credits_per_unit")


def _normalize_create_only(payload: dict[str, Any]) -> bool:
    if "create_only" not in payload:
        return False
    value = payload.get("create_only")
    if not isinstance(value, bool):
        raise_param_error("create_only")
    return value


def _validate_exact_identifier(
    value: str,
    *,
    field_name: str,
    max_length: int,
    required: bool,
) -> str:
    normalized = str(value or "").strip()
    if required and not normalized:
        raise_param_error(field_name)
    if len(normalized) > max_length:
        raise_param_error(field_name)
    if "*" in normalized or any(
        unicodedata.category(char).startswith("C") for char in normalized
    ):
        raise_param_error(field_name)
    return normalized


def _decimal_to_number(value: Decimal | float | str) -> int | float:
    decimal_value = Decimal(str(value or 0))
    normalized = decimal_value.normalize()
    if normalized == normalized.to_integral_value():
        return int(normalized)
    return float(normalized)


def _unit_cost(rate: CreditUsageRate | None) -> Decimal | None:
    if rate is None:
        return None
    try:
        unit_size = max(int(rate.unit_size or 1), 1)
        return Decimal(str(rate.credits_per_unit or 0)) / Decimal(str(unit_size))
    except (InvalidOperation, TypeError, ValueError, ZeroDivisionError):
        return None


def _format_multiplier(value: Decimal | None) -> float | None:
    if value is None:
        return None
    if value < 0:
        return None
    rounded = value.quantize(Decimal("0.01"))
    return float(rounded)


def _load_tts_chars_per_llm_token() -> Decimal | None:
    try:
        value = Decimal(str(get_config("TTS_CHARS_PER_LLM_TOKEN", "") or ""))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return value if value > 0 else None


def _resolve_llm_rate_identity(model: str) -> tuple[str, list[str]]:
    normalized = str(model or "").strip()
    if not normalized:
        return "", []
    from flaskr.api.llm import _resolve_billing_rate_identity

    return _resolve_billing_rate_identity(normalized)


def _load_llm_credit_1x_reference_cost() -> Decimal | None:
    """Return the fixed 1x anchor used by the operator config page."""

    return load_llm_credit_1x_unit_cost()


def _load_default_llm_metric_ratio(metric: int) -> Decimal:
    if metric == BILLING_METRIC_LLM_OUTPUT_TOKENS:
        return Decimal(1)

    default_model = str(get_config("DEFAULT_LLM_MODEL", "") or "").strip()
    if default_model:
        provider, model_candidates = _resolve_llm_rate_identity(default_model)
        metric_cost = _unit_cost(
            _rate_for_identity(
                usage_type=BILL_USAGE_TYPE_LLM,
                provider=provider,
                model_candidates=model_candidates,
                billing_metric=metric,
            )
        )
        output_cost = _unit_cost(
            _rate_for_identity(
                usage_type=BILL_USAGE_TYPE_LLM,
                provider=provider,
                model_candidates=model_candidates,
                billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
            )
        )
        if metric_cost and output_cost and output_cost > 0:
            return metric_cost / output_cost

    return _LLM_MISSING_RATE_FALLBACK_RATIOS.get(metric, Decimal(1))


def _llm_credits_for_missing_metric(
    *,
    metric: int,
    output_unit_cost: Decimal,
    unit_size: int,
) -> Decimal:
    ratio = _load_default_llm_metric_ratio(metric)
    return output_unit_cost * ratio * Decimal(str(unit_size))


def _rate_for_identity(
    *,
    usage_type: int,
    provider: str,
    model_candidates: list[str],
    billing_metric: int,
    rate_index: _ActiveRateIndex | None = None,
) -> CreditUsageRate | None:
    normalized_provider = str(provider or "").strip()
    normalized_models = [
        str(model or "").strip()
        for model in model_candidates
        if str(model or "").strip()
    ]
    if not normalized_models:
        normalized_models = [""]
    if rate_index is not None:
        providers = list(dict.fromkeys((normalized_provider, "*")))
        models = list(dict.fromkeys((*normalized_models, "*")))
        for candidate_provider in providers:
            for candidate_model in models:
                rate = rate_index.get(
                    (
                        usage_type,
                        billing_metric,
                        candidate_provider,
                        candidate_model,
                    )
                )
                if rate is not None:
                    return rate
        return None

    model_priority = {
        model: len(normalized_models) - index
        for index, model in enumerate(normalized_models)
    }
    settlement_at = now_utc()
    rows = (
        CreditUsageRate.query.filter(
            CreditUsageRate.deleted == 0,
            CreditUsageRate.status == CREDIT_USAGE_RATE_STATUS_ACTIVE,
            CreditUsageRate.usage_type == usage_type,
            CreditUsageRate.usage_scene == BILL_USAGE_SCENE_PROD,
            CreditUsageRate.billing_metric == billing_metric,
        )
        .order_by(CreditUsageRate.effective_from.desc(), CreditUsageRate.id.desc())
        .all()
    )
    candidates = [
        row
        for row in rows
        if row.effective_from <= settlement_at
        and (row.effective_to is None or row.effective_to > settlement_at)
        and str(row.provider or "") in {normalized_provider, "*"}
        and str(row.model or "") in set(normalized_models).union({"*"})
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            str(row.provider or "") == normalized_provider,
            str(row.model or "") in set(normalized_models),
            model_priority.get(str(row.model or ""), 0),
            row.effective_from,
            int(row.id or 0),
        ),
        reverse=True,
    )
    return candidates[0]


def _load_active_rate_index() -> _ActiveRateIndex:
    effective_at = now_utc()
    billing_metrics = tuple(
        {metric for metrics in _RATE_METRICS.values() for metric in metrics}
    )
    rows = (
        CreditUsageRate.query.filter(
            CreditUsageRate.deleted == 0,
            CreditUsageRate.status == CREDIT_USAGE_RATE_STATUS_ACTIVE,
            CreditUsageRate.usage_type.in_(tuple(_RATE_METRICS)),
            CreditUsageRate.usage_scene == BILL_USAGE_SCENE_PROD,
            CreditUsageRate.billing_metric.in_(billing_metrics),
            CreditUsageRate.effective_from <= effective_at,
        )
        .filter(
            (CreditUsageRate.effective_to.is_(None))
            | (CreditUsageRate.effective_to > effective_at)
        )
        .order_by(CreditUsageRate.effective_from.desc(), CreditUsageRate.id.desc())
        .all()
    )
    rate_index: _ActiveRateIndex = {}
    for row in rows:
        key = (
            int(row.usage_type),
            int(row.billing_metric),
            str(row.provider or ""),
            str(row.model or ""),
        )
        rate_index.setdefault(key, row)
    return rate_index


def _serialize_rate_row(
    *,
    usage_type: int,
    provider: str,
    model: str,
    model_candidates: list[str] | None = None,
    rate_model: str | None = None,
    display_name: str,
    billing_metric: int,
    baseline_cost: Decimal | None,
    tts_chars_per_llm_token: Decimal | None,
    rate_index: _ActiveRateIndex | None = None,
) -> dict[str, Any]:
    rate_model_candidates = model_candidates or [model]
    resolved_rate_model = rate_model or (
        rate_model_candidates[0] if rate_model_candidates else model
    )
    rate = _rate_for_identity(
        usage_type=usage_type,
        provider=provider,
        model_candidates=rate_model_candidates,
        billing_metric=billing_metric,
        rate_index=rate_index,
    )
    unit_cost = _unit_cost(rate)
    multiplier: Decimal | None = None
    if unit_cost is not None and baseline_cost and baseline_cost > 0:
        if usage_type == BILL_USAGE_TYPE_TTS:
            if tts_chars_per_llm_token and tts_chars_per_llm_token > 0:
                multiplier = (unit_cost * tts_chars_per_llm_token) / baseline_cost
        else:
            multiplier = unit_cost / baseline_cost

    exact = bool(
        rate
        and str(rate.provider or "") == str(provider or "")
        and str(rate.model or "") in {str(item or "") for item in rate_model_candidates}
    )
    return {
        "rate_bid": str(rate.rate_bid or "") if rate else "",
        "matched_rate_provider": str(rate.provider) if rate else None,
        "matched_rate_model": str(rate.model) if rate else None,
        "usage_type": _USAGE_TYPE_LABELS.get(usage_type, str(usage_type)),
        "usage_type_code": int(usage_type),
        "provider": provider,
        "model": model,
        "rate_model": resolved_rate_model,
        "display_name": display_name or model or provider or "*",
        "usage_scene": _SCENE_LABELS[BILL_USAGE_SCENE_PROD],
        "usage_scene_code": BILL_USAGE_SCENE_PROD,
        "billing_metric": BILLING_METRIC_LABELS.get(
            billing_metric, str(billing_metric)
        ),
        "billing_metric_code": int(billing_metric),
        "unit_size": int(rate.unit_size or 1) if rate else 1,
        "credits_per_unit": _decimal_to_number(rate.credits_per_unit) if rate else 0,
        "unit_cost": _decimal_to_number(unit_cost or Decimal(0)),
        "multiplier": _format_multiplier(multiplier),
        "rounding_mode": (
            int(rate.rounding_mode or CREDIT_ROUNDING_MODE_CEIL)
            if rate
            else CREDIT_ROUNDING_MODE_CEIL
        ),
        "status": (
            CREDIT_USAGE_RATE_STATUS_LABELS.get(int(rate.status or 0), "unconfigured")
            if rate
            else "unconfigured"
        ),
        "status_code": int(rate.status or 0) if rate else 0,
        "effective_from": to_utc_iso(rate.effective_from) if rate else None,
        "effective_to": to_utc_iso(rate.effective_to) if rate else None,
        "updated_at": to_utc_iso(rate.updated_at) if rate else None,
        "source": "exact" if exact else ("default" if rate else "unconfigured"),
    }


def _build_llm_rows(
    app: Flask,
    baseline_cost: Decimal | None,
    rate_index: _ActiveRateIndex,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    catalog_seen: set[tuple[str, str]] = set()
    seen: set[tuple[str, str]] = set()
    for option in get_current_models(app):
        model = str(option.get("model") or "").strip()
        if not model:
            continue
        provider, model_candidates = _resolve_llm_rate_identity(model)
        rate_model = model_candidates[0] if model_candidates else model
        display_name = str(option.get("display_name") or model).strip()
        key = (provider, rate_model)
        if key in catalog_seen:
            continue
        catalog_seen.add(key)
        row = _serialize_rate_row(
            usage_type=BILL_USAGE_TYPE_LLM,
            provider=provider,
            model=model,
            model_candidates=model_candidates,
            rate_model=rate_model,
            display_name=display_name,
            billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
            baseline_cost=baseline_cost,
            tts_chars_per_llm_token=None,
            rate_index=rate_index,
        )
        rows.append(row)
        matched_provider = row["matched_rate_provider"]
        matched_model = row["matched_rate_model"]
        if matched_provider is not None and matched_model is not None:
            seen.add((str(matched_provider), str(matched_model)))
    for provider, rate_model in _load_active_exact_rate_identities(
        rate_index, BILL_USAGE_TYPE_LLM
    ):
        key = (provider, rate_model)
        if key in seen:
            continue
        seen.add(key)
        model = f"{provider}/{rate_model}"
        rows.append(
            _serialize_rate_row(
                usage_type=BILL_USAGE_TYPE_LLM,
                provider=provider,
                model=model,
                model_candidates=[rate_model],
                rate_model=rate_model,
                display_name=model,
                billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                baseline_cost=baseline_cost,
                tts_chars_per_llm_token=None,
                rate_index=rate_index,
            )
        )
    return rows


def _build_tts_rows(
    baseline_cost: Decimal | None,
    rate_index: _ActiveRateIndex,
) -> list[dict[str, Any]]:
    config = get_all_provider_configs()
    tts_chars_per_llm_token = _load_tts_chars_per_llm_token()
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for option in config.get("model_options") or []:
        provider = str(option.get("provider") or "").strip()
        model = str(option.get("model") or "").strip()
        if not provider:
            continue
        key = (provider, model)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            _serialize_rate_row(
                usage_type=BILL_USAGE_TYPE_TTS,
                provider=provider,
                model=model,
                model_candidates=[model],
                rate_model=model,
                display_name=str(option.get("label") or model or provider).strip(),
                billing_metric=BILLING_METRIC_TTS_OUTPUT_CHARS,
                baseline_cost=baseline_cost,
                tts_chars_per_llm_token=tts_chars_per_llm_token,
                rate_index=rate_index,
            )
        )
    for provider, model in _load_active_exact_rate_identities(
        rate_index, BILL_USAGE_TYPE_TTS
    ):
        key = (provider, model)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            _serialize_rate_row(
                usage_type=BILL_USAGE_TYPE_TTS,
                provider=provider,
                model=model,
                model_candidates=[model],
                rate_model=model,
                display_name=f"{provider}/{model}" if model else provider,
                billing_metric=BILLING_METRIC_TTS_OUTPUT_CHARS,
                baseline_cost=baseline_cost,
                tts_chars_per_llm_token=tts_chars_per_llm_token,
                rate_index=rate_index,
            )
        )
    return rows


def _load_active_exact_rate_identities(
    rate_index: _ActiveRateIndex, usage_type: int
) -> list[tuple[str, str]]:
    identities: set[tuple[str, str]] = set()
    for indexed_usage_type, metric, indexed_provider, indexed_model in rate_index:
        if indexed_usage_type != usage_type or metric not in _RATE_METRICS[usage_type]:
            continue
        provider = indexed_provider.strip()
        model = indexed_model.strip()
        if not provider or "*" in provider or "*" in model:
            continue
        if usage_type == BILL_USAGE_TYPE_LLM and not model:
            continue
        identities.add((provider, model))
    return sorted(identities)


def get_operator_rate_config(app: Flask) -> dict[str, Any]:
    with app_context_scope(app):
        baseline_cost = _load_llm_credit_1x_reference_cost()
        baseline_per_1000 = load_llm_credit_1x_per_1000_output_tokens()
        rate_index = _load_active_rate_index()
        return {
            "baseline": {
                "default_llm_model": str(get_config("DEFAULT_LLM_MODEL", "") or ""),
                "unit_cost": _decimal_to_number(baseline_cost or Decimal(0)),
                "per_1000_output_tokens": _decimal_to_number(
                    baseline_per_1000 or Decimal(0)
                ),
                "is_configured": bool(baseline_cost and baseline_cost > 0),
                "tts_chars_per_llm_token": _decimal_to_number(
                    _load_tts_chars_per_llm_token() or Decimal(0)
                ),
            },
            "llm_rates": _build_llm_rows(app, baseline_cost, rate_index),
            "tts_rates": _build_tts_rows(baseline_cost, rate_index),
        }


def _normalize_usage_type(value: Any) -> int:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _USAGE_TYPE_CODES:
            return _USAGE_TYPE_CODES[normalized]
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        raise_param_error("usage_type")
    if numeric not in _RATE_METRICS:
        raise_param_error("usage_type")
    return numeric


def _normalize_metric(value: Any, *, usage_type: int) -> int:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in _METRIC_CODES:
            metric = _METRIC_CODES[normalized]
        else:
            raise_param_error("billing_metric")
    else:
        try:
            metric = int(value)
        except (TypeError, ValueError):
            raise_param_error("billing_metric")
    if metric not in _RATE_METRICS[usage_type]:
        raise_param_error("billing_metric")
    return metric


def update_operator_rate_config(
    app: Flask,
    *,
    payload: dict[str, Any],
    operator_user_bid: str,
) -> dict[str, Any]:
    with app_context_scope(app), unit_of_work():
        create_only = _normalize_create_only(payload)
        usage_type = _normalize_usage_type(payload.get("usage_type"))
        billing_metric = _normalize_metric(
            payload.get("billing_metric"), usage_type=usage_type
        )
        expected_create_metric = (
            BILLING_METRIC_LLM_OUTPUT_TOKENS
            if usage_type == BILL_USAGE_TYPE_LLM
            else BILLING_METRIC_TTS_OUTPUT_CHARS
        )
        if create_only and billing_metric != expected_create_metric:
            raise_param_error("billing_metric")
        provider = str(payload.get("provider") or "").strip()
        requested_model = str(payload.get("model") or "").strip()
        model = requested_model
        has_explicit_rate_model = "rate_model" in payload
        rate_model = str(payload.get("rate_model") or "").strip()
        model_candidates = [model]
        if usage_type == BILL_USAGE_TYPE_LLM:
            if create_only and not requested_model:
                raise_param_error("model")
            resolved_provider, resolved_model_candidates = _resolve_llm_rate_identity(
                requested_model
            )
            if not provider:
                provider = resolved_provider
            model_candidates = resolved_model_candidates or [model]
            model = rate_model or model_candidates[0]
            if model and model not in model_candidates:
                model_candidates = [model, *model_candidates]
        elif create_only and "rate_model" in payload:
            model = rate_model
            model_candidates = [model]
        if create_only:
            provider = _validate_exact_identifier(
                provider,
                field_name="provider",
                max_length=_PROVIDER_MAX_LENGTH,
                required=True,
            )
            model = _validate_exact_identifier(
                model,
                field_name="model",
                max_length=_MODEL_MAX_LENGTH,
                required=usage_type == BILL_USAGE_TYPE_LLM,
            )
        elif not provider and usage_type == BILL_USAGE_TYPE_TTS:
            raise_param_error("provider")
        if create_only:
            raw_unit_size = payload.get("unit_size", 1)
            if raw_unit_size is None:
                raw_unit_size = 1
            try:
                decimal_unit_size = Decimal(str(raw_unit_size).strip())
                if decimal_unit_size != Decimal(1):
                    raise_param_error("unit_size")
                unit_size = 1
            except (InvalidOperation, TypeError, ValueError):
                raise_param_error("unit_size")
        else:
            raw_unit_size = payload.get("unit_size") or 1
            unit_size = int(raw_unit_size)
        if unit_size <= 0:
            raise_param_error("unit_size")

        baseline_cost = _load_llm_credit_1x_reference_cost()
        if baseline_cost is None or baseline_cost <= 0:
            raise_param_error("llm_credit_1x_per_1000_output_tokens")

        credits_per_unit = _decimal(
            payload.get("credits_per_unit"), field_name="credits_per_unit"
        )
        if credits_per_unit <= 0:
            raise_param_error("credits_per_unit")
        if create_only:
            _validate_create_only_credits_per_unit(credits_per_unit)
        status = payload.get("status")
        if isinstance(status, str):
            status_code = (
                CREDIT_USAGE_RATE_STATUS_ACTIVE
                if status.strip().lower() == "active"
                else CREDIT_USAGE_RATE_STATUS_INACTIVE
            )
        else:
            try:
                status_code = int(status or CREDIT_USAGE_RATE_STATUS_ACTIVE)
            except (TypeError, ValueError):
                if create_only:
                    raise_param_error("status")
                raise
        if status_code not in {
            CREDIT_USAGE_RATE_STATUS_ACTIVE,
            CREDIT_USAGE_RATE_STATUS_INACTIVE,
        }:
            raise_param_error("status")
        if create_only and status_code != CREDIT_USAGE_RATE_STATUS_ACTIVE:
            raise_param_error("status")

        now = _rate_effective_now()
        metrics_to_update = (
            _RATE_METRICS[BILL_USAGE_TYPE_LLM]
            if usage_type == BILL_USAGE_TYPE_LLM
            else (billing_metric,)
        )
        if create_only:
            existing_exact_rate = (
                CreditUsageRate.query.filter(
                    CreditUsageRate.deleted == 0,
                    CreditUsageRate.status == CREDIT_USAGE_RATE_STATUS_ACTIVE,
                    CreditUsageRate.usage_type == usage_type,
                    CreditUsageRate.provider == provider,
                    CreditUsageRate.model == model,
                    CreditUsageRate.usage_scene == BILL_USAGE_SCENE_PROD,
                    CreditUsageRate.billing_metric.in_(metrics_to_update),
                    CreditUsageRate.effective_from <= now,
                )
                .filter(
                    (CreditUsageRate.effective_to.is_(None))
                    | (CreditUsageRate.effective_to > now)
                )
                .first()
            )
            if existing_exact_rate is not None:
                raise_error("server.billing.rateConfigAlreadyExists")
        target_unit_cost = credits_per_unit / Decimal(str(unit_size))
        current_rates_by_metric: dict[int, CreditUsageRate | None] = {}
        if usage_type == BILL_USAGE_TYPE_LLM:
            current_rates_by_metric = {
                metric: _rate_for_identity(
                    usage_type=usage_type,
                    provider=provider,
                    model_candidates=model_candidates,
                    billing_metric=metric,
                )
                for metric in metrics_to_update
            }
        llm_scale: Decimal | None = None
        if usage_type == BILL_USAGE_TYPE_LLM:
            current_output_cost = _unit_cost(
                current_rates_by_metric.get(BILLING_METRIC_LLM_OUTPUT_TOKENS)
            )
            if current_output_cost and current_output_cost > 0:
                llm_scale = target_unit_cost / current_output_cost

        existing_rows: list[CreditUsageRate] = []
        if not create_only:
            models_to_supersede = (
                [model]
                if usage_type == BILL_USAGE_TYPE_LLM and has_explicit_rate_model
                else model_candidates
            )
            existing_rows = (
                CreditUsageRate.query.filter(
                    CreditUsageRate.deleted == 0,
                    CreditUsageRate.usage_type == usage_type,
                    CreditUsageRate.provider == provider,
                    CreditUsageRate.model.in_(models_to_supersede),
                    CreditUsageRate.usage_scene == BILL_USAGE_SCENE_PROD,
                    CreditUsageRate.billing_metric.in_(metrics_to_update),
                    CreditUsageRate.status == CREDIT_USAGE_RATE_STATUS_ACTIVE,
                )
                .filter(CreditUsageRate.effective_from <= now)
                .filter(
                    (CreditUsageRate.effective_to.is_(None))
                    | (CreditUsageRate.effective_to > now)
                )
                .order_by(
                    CreditUsageRate.effective_from.desc(), CreditUsageRate.id.desc()
                )
                .all()
            )
        for row in existing_rows:
            row.effective_to = now

        for metric in metrics_to_update:
            next_unit_size = unit_size
            next_credits_per_unit = credits_per_unit
            if usage_type == BILL_USAGE_TYPE_LLM:
                current_metric_rate = current_rates_by_metric.get(metric)
                current_metric_cost = _unit_cost(current_metric_rate)
                if create_only and metric == BILLING_METRIC_LLM_OUTPUT_TOKENS:
                    next_credits_per_unit = credits_per_unit
                elif (
                    llm_scale is not None
                    and current_metric_rate is not None
                    and current_metric_cost is not None
                ):
                    next_unit_size = max(int(current_metric_rate.unit_size or 1), 1)
                    next_credits_per_unit = (
                        current_metric_cost * llm_scale * Decimal(str(next_unit_size))
                    )
                else:
                    next_credits_per_unit = _llm_credits_for_missing_metric(
                        metric=metric,
                        output_unit_cost=target_unit_cost,
                        unit_size=next_unit_size,
                    )
            if create_only:
                if (
                    usage_type == BILL_USAGE_TYPE_LLM
                    and metric != BILLING_METRIC_LLM_OUTPUT_TOKENS
                ):
                    next_credits_per_unit = _quantize_derived_credits_per_unit(
                        next_credits_per_unit
                    )
                _validate_create_only_credits_per_unit(next_credits_per_unit)
            same_second_row = CreditUsageRate.query.filter(
                CreditUsageRate.deleted == 0,
                CreditUsageRate.usage_type == usage_type,
                CreditUsageRate.provider == provider,
                CreditUsageRate.model == model,
                CreditUsageRate.usage_scene == BILL_USAGE_SCENE_PROD,
                CreditUsageRate.billing_metric == metric,
                CreditUsageRate.effective_from == now,
            ).first()
            if same_second_row is not None:
                same_second_row.unit_size = next_unit_size
                same_second_row.credits_per_unit = next_credits_per_unit
                same_second_row.rounding_mode = CREDIT_ROUNDING_MODE_CEIL
                same_second_row.effective_to = None
                same_second_row.status = status_code
                continue
            db.session.add(
                CreditUsageRate(
                    rate_bid=generate_id(app),
                    usage_type=usage_type,
                    provider=provider,
                    model=model,
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    billing_metric=metric,
                    unit_size=next_unit_size,
                    credits_per_unit=next_credits_per_unit,
                    rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
                    effective_from=now,
                    effective_to=None,
                    status=status_code,
                )
            )
        return _serialize_rate_row(
            usage_type=usage_type,
            provider=provider,
            model=model,
            model_candidates=model_candidates,
            rate_model=model,
            display_name=str(payload.get("display_name") or model or provider),
            billing_metric=(
                BILLING_METRIC_LLM_OUTPUT_TOKENS
                if usage_type == BILL_USAGE_TYPE_LLM
                else billing_metric
            ),
            baseline_cost=baseline_cost,
            tts_chars_per_llm_token=_load_tts_chars_per_llm_token(),
        )

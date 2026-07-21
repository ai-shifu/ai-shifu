from __future__ import annotations

from decimal import Decimal, InvalidOperation
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
from flaskr.service.common.models import raise_param_error
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
    BILLING_METRIC_LLM_OUTPUT_TOKENS: Decimal("1"),
}


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
    if result < 0:
        raise_param_error(field_name)
    return result


def _decimal_to_number(value: Decimal | int | float | str) -> int | float:
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


def _load_default_llm_reference_cost(
    default_model: str | None = None,
) -> Decimal | None:
    """Return the stable 1x anchor used by the operator config page."""

    default_model = str(
        default_model
        if default_model is not None
        else get_config("DEFAULT_LLM_MODEL", "") or ""
    ).strip()
    if not default_model:
        return None
    provider, model_candidates = _resolve_llm_rate_identity(default_model)
    normalized_models = [
        str(model or "").strip()
        for model in model_candidates
        if str(model or "").strip()
    ]
    if not normalized_models:
        return None
    model_priority = {
        model: len(normalized_models) - index
        for index, model in enumerate(normalized_models)
    }
    rows = (
        CreditUsageRate.query.filter(
            CreditUsageRate.deleted == 0,
            CreditUsageRate.usage_type == BILL_USAGE_TYPE_LLM,
            CreditUsageRate.provider == provider,
            CreditUsageRate.model.in_(normalized_models),
            CreditUsageRate.usage_scene == BILL_USAGE_SCENE_PROD,
            CreditUsageRate.billing_metric == BILLING_METRIC_LLM_OUTPUT_TOKENS,
        )
        .order_by(CreditUsageRate.effective_from.asc(), CreditUsageRate.id.asc())
        .all()
    )
    if not rows:
        return None
    rows.sort(
        key=lambda row: (
            row.effective_from,
            -model_priority.get(str(row.model or ""), 0),
            int(row.id or 0),
        )
    )
    return _unit_cost(rows[0])


def _load_default_llm_metric_ratio(metric: int) -> Decimal:
    if metric == BILLING_METRIC_LLM_OUTPUT_TOKENS:
        return Decimal("1")

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

    return _LLM_MISSING_RATE_FALLBACK_RATIOS.get(metric, Decimal("1"))


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
) -> CreditUsageRate | None:
    normalized_provider = str(provider or "").strip()
    normalized_models = [
        str(model or "").strip()
        for model in model_candidates
        if str(model or "").strip()
    ]
    if not normalized_models:
        normalized_models = [""]
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
        "unit_cost": _decimal_to_number(unit_cost or Decimal("0")),
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


def _build_llm_rows(app: Flask, baseline_cost: Decimal | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for option in get_current_models(app):
        model = str(option.get("model") or "").strip()
        if not model:
            continue
        provider, model_candidates = _resolve_llm_rate_identity(model)
        rate_model = model_candidates[0] if model_candidates else model
        display_name = str(option.get("display_name") or model).strip()
        key = (provider, rate_model)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            _serialize_rate_row(
                usage_type=BILL_USAGE_TYPE_LLM,
                provider=provider,
                model=model,
                model_candidates=model_candidates,
                rate_model=rate_model,
                display_name=display_name,
                billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                baseline_cost=baseline_cost,
                tts_chars_per_llm_token=None,
            )
        )
    return rows


def _build_tts_rows(baseline_cost: Decimal | None) -> list[dict[str, Any]]:
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
            )
        )
    return rows


def get_operator_rate_config(app: Flask) -> dict[str, Any]:
    with app_context_scope(app):
        baseline_cost = _load_default_llm_reference_cost()
        return {
            "baseline": {
                "default_llm_model": str(get_config("DEFAULT_LLM_MODEL", "") or ""),
                "unit_cost": _decimal_to_number(baseline_cost or Decimal("0")),
                "tts_chars_per_llm_token": _decimal_to_number(
                    _load_tts_chars_per_llm_token() or Decimal("0")
                ),
            },
            "llm_rates": _build_llm_rows(app, baseline_cost),
            "tts_rates": _build_tts_rows(baseline_cost),
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
        usage_type = _normalize_usage_type(payload.get("usage_type"))
        billing_metric = _normalize_metric(
            payload.get("billing_metric"), usage_type=usage_type
        )
        provider = str(payload.get("provider") or "").strip()
        requested_model = str(payload.get("model") or "").strip()
        model = requested_model
        rate_model = str(payload.get("rate_model") or "").strip()
        model_candidates = [model]
        if usage_type == BILL_USAGE_TYPE_LLM:
            resolved_provider, resolved_model_candidates = _resolve_llm_rate_identity(
                requested_model
            )
            if not provider:
                provider = resolved_provider
            model_candidates = resolved_model_candidates or [model]
            model = rate_model or model_candidates[0]
            if model and model not in model_candidates:
                model_candidates = [model, *model_candidates]
        if not provider and usage_type == BILL_USAGE_TYPE_TTS:
            raise_param_error("provider")
        unit_size = int(payload.get("unit_size") or 1)
        if unit_size <= 0:
            raise_param_error("unit_size")

        credits_per_unit = _decimal(
            payload.get("credits_per_unit"), field_name="credits_per_unit"
        )
        if credits_per_unit <= 0:
            raise_param_error("credits_per_unit")
        status = payload.get("status")
        if isinstance(status, str):
            status_code = (
                CREDIT_USAGE_RATE_STATUS_ACTIVE
                if status.strip().lower() == "active"
                else CREDIT_USAGE_RATE_STATUS_INACTIVE
            )
        else:
            status_code = int(status or CREDIT_USAGE_RATE_STATUS_ACTIVE)
        if status_code not in {
            CREDIT_USAGE_RATE_STATUS_ACTIVE,
            CREDIT_USAGE_RATE_STATUS_INACTIVE,
        }:
            raise_param_error("status")

        now = _rate_effective_now()
        metrics_to_update = (
            _RATE_METRICS[BILL_USAGE_TYPE_LLM]
            if usage_type == BILL_USAGE_TYPE_LLM
            else (billing_metric,)
        )
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

        existing_rows = (
            CreditUsageRate.query.filter(
                CreditUsageRate.deleted == 0,
                CreditUsageRate.usage_type == usage_type,
                CreditUsageRate.provider == provider,
                CreditUsageRate.model.in_(model_candidates),
                CreditUsageRate.usage_scene == BILL_USAGE_SCENE_PROD,
                CreditUsageRate.billing_metric.in_(metrics_to_update),
                CreditUsageRate.status == CREDIT_USAGE_RATE_STATUS_ACTIVE,
            )
            .filter(CreditUsageRate.effective_from <= now)
            .filter(
                (CreditUsageRate.effective_to.is_(None))
                | (CreditUsageRate.effective_to > now)
            )
            .order_by(CreditUsageRate.effective_from.desc(), CreditUsageRate.id.desc())
            .all()
        )
        for row in existing_rows:
            row.effective_to = now
            row.status = CREDIT_USAGE_RATE_STATUS_INACTIVE

        for metric in metrics_to_update:
            next_unit_size = unit_size
            next_credits_per_unit = credits_per_unit
            if usage_type == BILL_USAGE_TYPE_LLM:
                current_metric_rate = current_rates_by_metric.get(metric)
                current_metric_cost = _unit_cost(current_metric_rate)
                if (
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
        baseline_cost = _load_default_llm_reference_cost()
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

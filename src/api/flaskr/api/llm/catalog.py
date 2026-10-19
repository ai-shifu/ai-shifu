"""Build course and follow-up model catalogs with credit multipliers."""

from __future__ import annotations

from decimal import ROUND_CEILING
from typing import TYPE_CHECKING, Any

# Package-level names are resolved through the package module at call time so
# tests and operators that patch `flaskr.api.llm.<name>` keep affecting this code.
import flaskr.api.llm as llm_package
from flaskr.api.llm.providers import (
    _rate_per_token,
    _select_credit_usage_rate,
)
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import CreditUsageRate
from flaskr.service.billing.rate_references import format_credit_multiplier
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
)

from .live_catalog import (
    GEMINI_LIVE_MODEL_ALLOWLIST,
    get_gemini_live_voice_options,
    is_live_follow_up_model,
)

if TYPE_CHECKING:
    from flask import Flask


def _build_model_options(
    app: Flask, available_models: list[str]
) -> list[dict[str, object]]:
    """Build a physical catalog from configured slots, never provider discovery alone."""
    from flaskr.api.llm.model_selection import get_configured_model_slots

    available_set = set(available_models)
    seen = set()
    options = []
    for slot in get_configured_model_slots():
        model = slot["model"]
        if model not in available_set or model in seen:
            continue
        seen.add(model)
        options.append({"model": model, "display_name": slot["display_name"]})
    return llm_package._attach_credit_multipliers(app, options)


def _resolve_billing_rate_identity(model: str) -> tuple[str, list[str]]:
    provider, actual_model = llm_package._resolve_provider_for_model(model)
    candidates: list[str] = []
    for candidate in (actual_model, model):
        normalized = str(candidate or "").strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return provider or "", candidates


def _load_llm_output_rate_rows(app: Flask) -> list[CreditUsageRate]:
    with app.app_context():
        return (
            CreditUsageRate.query.filter(
                CreditUsageRate.deleted == 0,
                CreditUsageRate.status == CREDIT_USAGE_RATE_STATUS_ACTIVE,
                CreditUsageRate.usage_type == BILL_USAGE_TYPE_LLM,
                CreditUsageRate.usage_scene == BILL_USAGE_SCENE_PROD,
                CreditUsageRate.billing_metric == BILLING_METRIC_LLM_OUTPUT_TOKENS,
            )
            .order_by(CreditUsageRate.effective_from.desc(), CreditUsageRate.id.desc())
            .all()
        )


def _attach_credit_multipliers(
    app: Flask, options: list[dict[str, object]]
) -> list[dict[str, object]]:
    from flaskr.api.llm.model_selection import get_default_llm_model

    default_model = get_default_llm_model()
    if not options:
        return [{**option, "credit_multiplier": None} for option in options]

    try:
        rows = llm_package._load_llm_output_rate_rows(app)
        now = llm_package.now_utc()
        default_rate = llm_package.load_llm_credit_1x_unit_cost()
        if default_rate is None or default_rate <= 0:
            return [{**option, "credit_multiplier": None} for option in options]

        enriched: list[dict[str, Any]] = []
        for option in options:
            model = str(option.get("model") or "").strip()
            provider, model_candidates = llm_package._resolve_billing_rate_identity(
                model
            )
            model_rate = _rate_per_token(
                _select_credit_usage_rate(
                    rows,
                    provider=provider,
                    model_candidates=model_candidates,
                    now=now,
                )
            )
            multiplier = None
            multiplier_label = None
            if model_rate is not None and model_rate > 0:
                multiplier_value = model_rate / default_rate
                multiplier = int(
                    multiplier_value.to_integral_value(rounding=ROUND_CEILING)
                )
                multiplier_label = format_credit_multiplier(multiplier_value)
            enriched.append(
                {
                    **option,
                    "credit_multiplier": multiplier,
                    "credit_multiplier_label": multiplier_label,
                    "is_default": model == default_model,
                }
            )
    except Exception as exc:
        llm_package._log_warning(f"load LLM credit multipliers error: {exc}")
        return [{**option, "credit_multiplier": None} for option in options]
    else:
        return enriched


def get_current_models(app: Flask) -> list[dict[str, object]]:
    """Return configured physical text models for internal and gateway consumers."""
    from flaskr.api.llm.model_selection import (
        get_configured_model_slots,
        resolve_model_slot,
    )

    litellm_models: list[str] = []
    for slot in get_configured_model_slots():
        try:
            litellm_models.append(resolve_model_slot(slot["index"]))
        except AppError as exc:
            if exc.code not in {
                ERROR_CODE["server.llm.modelUnavailable"],
                ERROR_CODE["server.llm.modelSelectionNotConfigured"],
            }:
                raise
    available_models = [
        model
        for model in dict.fromkeys(litellm_models)
        if not is_live_follow_up_model(model)
        and (
            not llm_package.MODEL_SUPPORTED_GENERATION_METHODS.get(model)
            or "generateContent"
            in llm_package.MODEL_SUPPORTED_GENERATION_METHODS[model]
        )
    ]
    return llm_package._build_model_options(app, available_models)


def is_live_follow_up_model_available(model: object) -> bool:
    """Return whether an allowlisted Live model was capability-discovered."""
    normalized_model = str(model or "").strip()
    if (
        not llm_package.is_gemini_live_enabled()
        or normalized_model not in GEMINI_LIVE_MODEL_ALLOWLIST
    ):
        return False
    gemini_state = llm_package.PROVIDER_STATES.get("gemini")
    if not gemini_state or not gemini_state.enabled:
        return False
    if normalized_model not in gemini_state.models:
        return False
    return "bidiGenerateContent" in llm_package.MODEL_SUPPORTED_GENERATION_METHODS.get(
        normalized_model, frozenset()
    )


def get_follow_up_models(app: Flask) -> list[dict[str, object]]:
    """Return model options with stable follow-up interaction capabilities."""
    options = [
        {
            **option,
            "interaction_mode": "text",
            "allowed_roles": ["main", "follow_up"],
            "billing_mode": "billable",
            "voices": [],
        }
        for option in llm_package.get_legacy_course_model_options(app)
    ]
    for model in GEMINI_LIVE_MODEL_ALLOWLIST:
        if not llm_package.is_live_follow_up_model_available(model):
            continue
        options.append(
            {
                "model": model,
                "display_name": "Gemini Live",
                "credit_multiplier": None,
                "credit_multiplier_label": None,
                "is_default": False,
                "interaction_mode": "live_voice",
                "allowed_roles": ["follow_up"],
                "billing_mode": "free_preview",
                "voices": get_gemini_live_voice_options(),
            }
        )
    return options


def get_course_model_options(app: Flask) -> list[dict[str, object]]:
    """Return numbered course choices with labels, availability, and credit rates."""
    from flaskr.api.llm.model_selection import (
        get_configured_model_slots,
        resolve_model_slot,
    )

    options = []
    available_options = []
    for slot in get_configured_model_slots():
        option = {
            "index": slot["index"],
            "display_name": slot["display_name"],
            "available": False,
            "is_default": slot["index"] == "1",
            "credit_multiplier": None,
            "credit_multiplier_label": None,
        }
        try:
            model = resolve_model_slot(slot["index"])
        except AppError as exc:
            if exc.code not in {
                ERROR_CODE["server.llm.modelUnavailable"],
                ERROR_CODE["server.llm.modelSelectionNotConfigured"],
            }:
                raise
        else:
            option["available"] = True
            available_options.append((option, model))
        options.append(option)
    if available_options:
        models = dict.fromkeys(model for _, model in available_options)
        rates_by_model = {
            rates["model"]: rates
            for rates in llm_package._attach_credit_multipliers(
                app, [{"model": model} for model in models]
            )
        }
        for option, model in available_options:
            rates = rates_by_model[model]
            option.update(
                credit_multiplier=rates.get("credit_multiplier"),
                credit_multiplier_label=rates.get("credit_multiplier_label"),
            )
    return options


def get_legacy_course_model_options(app: Flask) -> list[dict[str, object]]:
    """Adapt course options to catalogs that expect an index in the model field."""
    return [
        {**option, "model": option["index"]}
        for option in llm_package.get_course_model_options(app)
    ]

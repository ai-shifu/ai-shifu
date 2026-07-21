from __future__ import annotations

from decimal import Decimal, InvalidOperation

from flaskr.service.billing.consts import BILLING_METRIC_LLM_OUTPUT_TOKENS
from flaskr.service.billing.models import CreditUsageRate
from flaskr.service.config.funcs import get_config
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_LLM
from flaskr.service.metering.models import BillUsageRecord
from flaskr.util.datetime import now_utc


def rate_unit_cost(rate: CreditUsageRate | None) -> Decimal | None:
    if rate is None:
        return None
    try:
        unit_size = max(int(rate.unit_size or 1), 1)
        return Decimal(str(rate.credits_per_unit or 0)) / Decimal(str(unit_size))
    except (InvalidOperation, TypeError, ValueError, ZeroDivisionError):
        return None


def format_credit_multiplier(value: Decimal | None) -> str | None:
    if value is None or value <= 0:
        return None
    rounded = value.quantize(Decimal("0.01"))
    text = format(rounded.normalize(), "f").rstrip("0").rstrip(".")
    return f"{text or '0'}x"


def resolve_llm_rate_identity(model: str) -> tuple[str, list[str]]:
    normalized = str(model or "").strip()
    if not normalized:
        return "", []
    try:
        from flaskr.api.llm import _resolve_billing_rate_identity

        return _resolve_billing_rate_identity(normalized)
    except Exception:
        if "/" in normalized:
            provider, actual_model = normalized.split("/", 1)
            return provider.strip(), [actual_model.strip(), normalized]
        return "", [normalized]


def _load_current_default_llm_output_cost(
    default_model: str | None = None,
) -> Decimal | None:
    from flaskr.service.billing.charges import load_usage_rate

    default_model = str(
        default_model
        if default_model is not None
        else get_config("DEFAULT_LLM_MODEL", "") or ""
    ).strip()
    provider = ""
    model_candidates = [default_model] if default_model else [""]
    if default_model:
        provider, model_candidates = resolve_llm_rate_identity(default_model)
    for model in model_candidates or [""]:
        rate = load_usage_rate(
            usage=BillUsageRecord(
                usage_type=BILL_USAGE_TYPE_LLM,
                provider=provider,
                model=model,
                usage_scene=BILL_USAGE_SCENE_PROD,
            ),
            billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
            settlement_at=now_utc(),
        )
        cost = rate_unit_cost(rate)
        if cost and cost > 0:
            return cost
    return None


def load_default_llm_reference_cost(default_model: str | None = None) -> Decimal | None:
    """Return the stable 1x anchor for model multiplier display.

    The configurable page can edit the default LLM itself. If display code uses
    the current default-model price as the denominator, the edited default model
    always renders as 1x. Use the earliest default-model output-token price as
    the stable reference instead.
    """

    default_model = str(
        default_model
        if default_model is not None
        else get_config("DEFAULT_LLM_MODEL", "") or ""
    ).strip()
    if not default_model:
        return _load_current_default_llm_output_cost(default_model)
    provider, model_candidates = resolve_llm_rate_identity(default_model)
    normalized_models = [
        str(model or "").strip()
        for model in model_candidates
        if str(model or "").strip()
    ]
    if not normalized_models:
        return _load_current_default_llm_output_cost(default_model)
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
        return _load_current_default_llm_output_cost(default_model)
    rows.sort(
        key=lambda row: (
            row.effective_from,
            -model_priority.get(str(row.model or ""), 0),
            int(row.id or 0),
        )
    )
    return rate_unit_cost(rows[0]) or _load_current_default_llm_output_cost(
        default_model
    )

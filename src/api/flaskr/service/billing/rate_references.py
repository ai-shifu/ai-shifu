"""Handle rate references for creator billing."""

from __future__ import annotations

from decimal import Decimal

from .consts import RENAMED_LLM_BILLING_PROVIDERS, RENAMED_LLM_MODEL_PREFIXES


def format_credit_multiplier(value: Decimal | None) -> str | None:
    """Format credit multiplier."""
    if value is None or value <= 0:
        return None
    rounded = value.quantize(Decimal("0.01"))
    if rounded == rounded.to_integral_value():
        # Whole numbers must not lose trailing zeros: stripping "30" to "3".
        text = str(int(rounded))
    else:
        text = format(rounded.normalize(), "f").rstrip("0").rstrip(".")
    return f"{text or '0'}x"


def legacy_llm_rate_aliases(
    providers: set[str], model_candidates: list[str]
) -> tuple[set[str], list[str]]:
    """Return earlier provider names and model ids for LiteLLM-named identities.

    Rate rows exist only under the earlier names until migration a3c5e7f9b1d2
    copies them, so lookups also try these. An earlier-named row ranks below
    rows under the current names and above ``*`` provider rows, as its copy
    does, so the selected rate is the same before and after the migration. Legacy
    model ids rank below every current model candidate.
    """
    current = {str(provider or "").strip() for provider in providers} - {""}
    legacy_providers = {
        legacy
        for legacy, renamed in RENAMED_LLM_BILLING_PROVIDERS.items()
        if renamed in current
    } - current
    legacy_models: list[str] = []
    for candidate in model_candidates:
        for legacy_prefix, prefix in RENAMED_LLM_MODEL_PREFIXES.items():
            if candidate.startswith(prefix) and len(candidate) > len(prefix):
                legacy_model = legacy_prefix + candidate[len(prefix) :]
                if (
                    legacy_model not in model_candidates
                    and legacy_model not in legacy_models
                ):
                    legacy_models.append(legacy_model)
    return legacy_providers, legacy_models


def resolve_llm_rate_identity(model: str) -> tuple[str, list[str]]:
    """Resolve LLM rate identity."""
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

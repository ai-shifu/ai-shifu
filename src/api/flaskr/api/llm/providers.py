"""Describe LLM providers and select credit usage rates for model options."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from flaskr.service.billing.models import CreditUsageRate


from flaskr.util.datetime import NAIVE_DATETIME_MIN


@dataclass
class ProviderConfig:
    """Describe configuration for one LLM provider."""

    key: str
    api_key_env: str
    base_url_env: str | None = None
    default_base_url: str | None = None
    prefix: str = ""
    fetch_models: bool = True
    filter_fn: Callable[[str], bool] | None = None
    static_models: list[str] = field(default_factory=list)
    extra_models: list[str] = field(default_factory=list)
    wildcard_prefixes: tuple[str, ...] = ()
    config_hint: str = ""
    custom_llm_provider: str | None = None
    model_loader: (
        Callable[
            [ProviderConfig, dict[str, str], str | None], list[str | tuple[str, str]]
        ]
        | None
    ) = None


@dataclass
class ProviderState:
    """Track availability and retry state for one LLM provider."""

    enabled: bool
    params: dict[str, str] | None
    models: list[str]
    prefix: str = ""
    wildcard_prefixes: tuple[str, ...] = ()


def _build_models_url(base_url: str | None) -> str:
    base = base_url or "https://api.openai.com/v1"
    return f"{base.rstrip('/')}/models"


QWEN_PREFIX = "qwen/"


ERNIE_V2_PREFIX = "ernie/"


GLM_PREFIX = "glm/"


SILICON_PREFIX = "silicon/"


GEMINI_PREFIX = ""


DEEPSEEK_FALLBACK_MODELS = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "deepseek-chat",
    "deepseek-reasoner",
]


def _rate_per_token(rate: CreditUsageRate | None) -> Decimal | None:
    if rate is None:
        return None
    try:
        unit_size = max(int(rate.unit_size or 1), 1)
        return Decimal(str(rate.credits_per_unit or 0)) / Decimal(str(unit_size))
    except (InvalidOperation, ValueError, TypeError, ZeroDivisionError):
        return None


def _select_credit_usage_rate(
    rows: list[CreditUsageRate],
    *,
    provider: str,
    model_candidates: list[str],
    now: datetime,
) -> CreditUsageRate | None:
    normalized_provider = str(provider or "").strip()
    normalized_models = [
        str(model or "").strip() for model in model_candidates if model
    ]
    if not normalized_models:
        return None
    candidate_set = set(normalized_models)
    model_priority = {
        model: len(normalized_models) - index
        for index, model in enumerate(normalized_models)
    }
    candidates = [
        row
        for row in rows
        if row.effective_from <= now
        and (row.effective_to is None or row.effective_to > now)
        and row.provider in {normalized_provider, "*"}
        and row.model in candidate_set.union({"*"})
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            row.provider == normalized_provider,
            row.model in candidate_set,
            model_priority.get(row.model, 0),
            row.effective_from or NAIVE_DATETIME_MIN,
            int(row.id or 0),
        ),
        reverse=True,
    )
    return candidates[0]

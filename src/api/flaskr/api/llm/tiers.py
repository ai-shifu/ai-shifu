"""Resolve reserved course model aliases at the provider boundary."""

from __future__ import annotations

from typing import Literal

from flaskr.service.common.models import (
    ERROR_CODE,
    AppError,
    raise_error,
    raise_param_error,
)
from flaskr.service.config import get_config

ModelTier = Literal["fast", "balanced", "ultimate"]
MODEL_TIERS = ("fast", "balanced", "ultimate")


def validate_model_tier(value: object, field: str = "model") -> str | None:
    """Validate a nullable tier without accepting arbitrary model names."""
    if value is None:
        return None
    if not isinstance(value, str) or value not in MODEL_TIERS:
        raise_param_error(field)
    return value


def normalize_course_model(model: object, field: str = "model") -> str:
    """Store explicit Fast defaults in existing course model fields."""
    if model is not None and not isinstance(model, str):
        raise_param_error(field)
    return str(model or "").strip() or "fast"


def selection_model(record: object, *, follow_up: bool = False) -> str:
    """Read a model alias or legacy identity without contacting a provider."""
    field = "ask_llm" if follow_up else "llm"
    return str(getattr(record, field, "") or "").strip()


def selection_metadata(record: object, *, follow_up: bool = False) -> dict:
    """Carry the selected revision through runtime usage recording."""
    field = "ask_llm" if follow_up else "llm"
    model = selection_model(record, follow_up=follow_up)
    tier = model if model in MODEL_TIERS else None
    return {
        "model_tier": tier,
        "model_selection_origin": "tier" if tier else "legacy_model",
        "model_selection_field": field,
        "model_selection_table": getattr(record, "__tablename__", ""),
        "model_selection_record_id": getattr(record, "id", None),
    }


def resolve_tier_model(tier: object) -> str:
    """Resolve a configured text model, rejecting missing or unusable routes."""
    from flaskr.api.llm import get_litellm_params_and_model
    from flaskr.service.learn.live_follow_up_config import is_live_follow_up_model

    normalized = validate_model_tier(tier)
    if normalized is None:
        raise_error("server.llm.modelSelectionNotConfigured")
    model = str(get_config(f"LLM_TIER_{normalized.upper()}_MODEL", "") or "").strip()
    if not model or model in MODEL_TIERS or is_live_follow_up_model(model):
        raise_error("server.llm.modelTierUnavailable")
    try:
        params, _, _ = get_litellm_params_and_model(model)
    except AppError as exc:
        if exc.code != ERROR_CODE["server.llm.specifiedLlmNotConfigured"]:
            raise
        # Provider diagnostics are internal; the teacher-facing error is bounded.
        raise_error("server.llm.modelTierUnavailable")
    if not params:
        raise_error("server.llm.modelTierUnavailable")
    return model


def resolve_selection(model: str, metadata: dict | None = None) -> tuple[str, dict]:
    """Snapshot one invocation's model and preserve its selection provenance."""
    values = dict(metadata or {})
    if values.get("resolved_model") and model == values["resolved_model"]:
        return model, values
    selected = str(model or "").strip()
    tier = selected if selected in MODEL_TIERS else None
    values["model_tier"] = tier
    values.setdefault("model_selection_origin", "tier" if tier else "legacy_model")
    resolved = resolve_tier_model(tier) if tier else selected
    if not resolved:
        raise_error("server.llm.modelSelectionNotConfigured")
    values["resolved_model"] = resolved
    return resolved, values

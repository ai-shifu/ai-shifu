"""Course model selection, distinct from provider/model identities."""

from __future__ import annotations

from typing import Literal

from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.config import get_config

ModelTier = Literal["fast", "balanced", "ultimate"]
MODEL_TIERS = ("fast", "balanced", "ultimate")
TIER_UNSET = object()


def validate_model_tier(value: object, field: str = "llm_tier") -> str | None:
    """Validate a nullable tier without accepting arbitrary model names."""
    if value is None:
        return None
    if not isinstance(value, str) or value not in MODEL_TIERS:
        raise_param_error(field)
    return value


def normalize_course_tier(tier: object, model: object) -> str | None:
    """Materialize the default on writes, while preserving legacy selections."""
    value = validate_model_tier(tier)
    return value or (None if str(model or "").strip() else "fast")


def merge_course_tier(
    incoming: object,
    *,
    current_tier: str | None,
    current_model: str,
    incoming_model: str | None,
    field: str,
) -> str | None:
    """Preserve PATCH omission and reject conflicting legacy-client writes."""
    if (
        current_tier
        and incoming is TIER_UNSET
        and incoming_model is not None
        and incoming_model != current_model
    ):
        raise_param_error(field)
    tier = (
        current_tier if incoming is TIER_UNSET else validate_model_tier(incoming, field)
    )
    return normalize_course_tier(
        tier, current_model if incoming_model is None else incoming_model
    )


def selection_model(record: object, *, follow_up: bool = False) -> str:
    """Return the legacy identity only when no tier overrides it (no I/O)."""
    field = "ask_llm" if follow_up else "llm"
    if getattr(record, field + "_tier", None):
        return ""
    return str(getattr(record, field, "") or "").strip()


def selection_metadata(record: object, *, follow_up: bool = False) -> dict:
    """Carry the selected revision through runtime usage recording."""
    field = "ask_llm" if follow_up else "llm"
    tier = getattr(record, field + "_tier", None)
    values = {
        "model_tier": tier,
        "model_selection_origin": "tier" if tier else "legacy_model",
        "model_selection_field": field,
        "model_selection_table": getattr(record, "__tablename__", ""),
        "model_selection_record_id": getattr(record, "id", None),
    }

    if tier and values["model_selection_record_id"]:
        from flask import has_app_context

        from flaskr.service.shifu.models import ModelTierMigrationAudit

        if has_app_context():
            audit = ModelTierMigrationAudit.query.filter_by(
                table_name=values["model_selection_table"],
                row_id=values["model_selection_record_id"],
                field_name=field + "_tier",
                new_tier=tier,
            ).first()
            if audit:
                values["model_selection_origin"] = "migrated_default"
                values["model_migration_batch"] = audit.batch_bid
    return values


def resolve_tier_model(tier: object) -> str:
    """Resolve a configured text model, rejecting missing or unusable routes."""
    from flaskr.api.llm import get_litellm_params_and_model
    from flaskr.service.learn.live_follow_up_config import is_live_follow_up_model

    normalized = validate_model_tier(tier)
    if normalized is None:
        raise_error("server.llm.modelSelectionNotConfigured")
    model = str(get_config(f"LLM_TIER_{normalized.upper()}_MODEL", "") or "").strip()
    if not model or is_live_follow_up_model(model):
        raise_error("server.llm.modelTierUnavailable")
    try:
        params, _, _ = get_litellm_params_and_model(model)
    except Exception:
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
    tier = values.get("model_tier")
    resolved = resolve_tier_model(tier) if tier else str(model or "").strip()
    if not resolved:
        raise_error("server.llm.modelSelectionNotConfigured")
    if "model_tier" in values:
        values["resolved_model"] = resolved
    return resolved, values

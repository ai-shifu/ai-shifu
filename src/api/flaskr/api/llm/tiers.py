"""Resolve stable course model numbers without rewriting saved selections."""

from __future__ import annotations

from flaskr.common.config import get_config
from flaskr.service.common.models import ERROR_CODE, AppError, raise_error
from flaskr.service.config import get_config as get_override_config
from flaskr.service.config import has_config_override

MODEL_INDEXES = tuple(str(index) for index in range(1, 10))


def _slot_config(key: str) -> str:
    # Numbered slots are environment settings. Only explicit process-local
    # overrides (used by isolated Arena runs) may bypass that source; absent
    # optional slots must not trigger database or cache lookups.
    reader = get_override_config if has_config_override(key) else get_config
    return str(reader(key, "") or "").strip()


def get_configured_model_slots() -> list[dict[str, str]]:
    """Read complete independent slots, retaining their stable numbers."""
    slots = []
    for index in MODEL_INDEXES:
        name = _slot_config(f"LLM_MODEL_{index}_NAME")
        model = _slot_config(f"LLM_MODEL_{index}_ID")
        if name and model:
            slots.append({"index": index, "display_name": name, "model": model})
    return slots


def course_model_selection(model: object) -> dict[str, object]:
    """Describe the effective course selection without resolving its provider."""
    selected = model.strip() if isinstance(model, str) else ""
    configured = {slot["index"] for slot in get_configured_model_slots()}
    if selected in configured:
        return {"index": selected, "fallback": False, "fallback_reason": None}
    if selected in MODEL_INDEXES:
        reason = "unconfigured_index"
    elif model is None or (isinstance(model, str) and not selected):
        reason = "missing_selection"
    else:
        reason = "invalid_selection"
    return {"index": "1", "fallback": True, "fallback_reason": reason}


def normalize_course_model(model: object, field: str = "model") -> str:
    """Normalize an explicitly saved text choice without changing stored reads."""
    _ = field
    return str(course_model_selection(model)["index"])


def selection_model(record: object, *, follow_up: bool = False) -> str:
    """Read the original saved selection without contacting a provider."""
    field = "ask_llm" if follow_up else "llm"
    return str(getattr(record, field, "") or "")


def selection_metadata(record: object, *, follow_up: bool = False) -> dict:
    """Carry original selection and revision identity through usage recording."""
    from flaskr.service.learn.live_follow_up_config import is_live_follow_up_model

    field = "ask_llm" if follow_up else "llm"
    model = selection_model(record, follow_up=follow_up)
    values = {
        "model_selection_scope": "course",
        "model_selection_original": model,
        "model_selection_field": field,
        "model_selection_table": getattr(record, "__tablename__", ""),
        "model_selection_record_id": getattr(record, "id", None),
    }
    if follow_up and is_live_follow_up_model(model):
        values["model_selection_scope"] = "live"
        return values
    selection = course_model_selection(model)
    values.update(
        model_index=selection["index"],
        model_selection_fallback=selection["fallback"],
        model_selection_fallback_reason=selection["fallback_reason"],
    )
    return values


def resolve_tier_model(index: object) -> str:
    """Resolve one complete numbered slot, rejecting unusable text routes."""
    from flaskr.api.llm import (
        MODEL_SUPPORTED_GENERATION_METHODS,
        get_litellm_params_and_model,
    )
    from flaskr.service.learn.live_follow_up_config import is_live_follow_up_model

    slot = next(
        (slot for slot in get_configured_model_slots() if slot["index"] == index),
        None,
    )
    if slot is None:
        raise_error("server.llm.modelSelectionNotConfigured")
    model = slot["model"]
    capabilities = MODEL_SUPPORTED_GENERATION_METHODS.get(model)
    if (
        model in MODEL_INDEXES
        or is_live_follow_up_model(model)
        or (capabilities and "generateContent" not in capabilities)
    ):
        raise_error("server.llm.modelTierUnavailable")
    try:
        params, _, _ = get_litellm_params_and_model(model)
    except AppError as exc:
        if exc.code != ERROR_CODE["server.llm.specifiedLlmNotConfigured"]:
            raise
        # Provider diagnostics can contain physical identities; keep them internal.
        raise_error("server.llm.modelTierUnavailable")
    if not params:
        raise_error("server.llm.modelTierUnavailable")
    return model


def resolve_course_selection(
    model: object, metadata: dict | None = None
) -> tuple[str, dict]:
    """Snapshot a course call after applying the default-number compatibility rule."""
    values = dict(metadata or {})
    if (
        values.get("model_selection_scope") == "course"
        and values.get("model_index") in MODEL_INDEXES
        and values.get("resolved_model")
        and model == values["resolved_model"]
    ):
        return str(model), values
    selection = course_model_selection(model)
    values.update(
        model_selection_scope="course",
        model_selection_original=model,
        model_index=selection["index"],
        model_selection_fallback=selection["fallback"],
        model_selection_fallback_reason=selection["fallback_reason"],
    )
    resolved = resolve_tier_model(selection["index"])
    values["resolved_model"] = resolved
    return resolved, values


def resolve_selection(model: str, metadata: dict | None = None) -> tuple[str, dict]:
    """Resolve scoped course selections while preserving generic physical IDs."""
    values = dict(metadata or {})
    if values.get("model_selection_scope") == "course":
        return resolve_course_selection(model, values)
    selected = str(model or "").strip()
    if not selected:
        raise_error("server.llm.modelSelectionNotConfigured")
    values["resolved_model"] = selected
    return selected, values

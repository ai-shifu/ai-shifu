"""Shared validation contract for AI-assisted source attribution."""

from dataclasses import dataclass
from uuid import UUID

from flaskr.service.common.models import raise_param_error

CREATION_SOURCE_AI_ASSISTANT = "ai_assistant"
SOURCE_PRODUCT_LOBSTER = "lobster"


@dataclass(frozen=True)
class SourceAttributionInput:
    """Validated, low-cardinality attribution supplied by an AI workflow."""

    creation_source: str
    source_product: str
    handoff_id: str


def parse_source_attribution(
    value: object,
    *,
    field_name: str,
) -> SourceAttributionInput | None:
    """Validate one optional structured attribution payload."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise_param_error(field_name)

    allowed_keys = {"creation_source", "source_product", "handoff_id"}
    if set(value) != allowed_keys:
        raise_param_error(field_name)

    creation_source = value.get("creation_source")
    source_product = value.get("source_product")
    handoff_id = value.get("handoff_id")
    if creation_source != CREATION_SOURCE_AI_ASSISTANT:
        raise_param_error(f"{field_name}.creation_source")
    if source_product != SOURCE_PRODUCT_LOBSTER:
        raise_param_error(f"{field_name}.source_product")
    if not isinstance(handoff_id, str):
        raise_param_error(f"{field_name}.handoff_id")
    try:
        parsed_handoff_id = UUID(handoff_id)
    except (ValueError, AttributeError, TypeError):
        raise_param_error(f"{field_name}.handoff_id")
    canonical_handoff_id = str(parsed_handoff_id)
    if handoff_id != canonical_handoff_id:
        raise_param_error(f"{field_name}.handoff_id")

    return SourceAttributionInput(
        creation_source=creation_source,
        source_product=source_product,
        handoff_id=canonical_handoff_id,
    )

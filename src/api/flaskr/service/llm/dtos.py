"""DTOs for LLM model catalog routes."""

from typing import Literal

from flaskr.common.swagger import register_schema_to_swagger
from pydantic import BaseModel, Field


@register_schema_to_swagger
class FollowUpVoiceOptionDTO(BaseModel):
    """Describe one provider-owned Live voice option."""

    voice_id: str = Field(..., description="Gemini prebuilt voiceName identifier")
    style: str = Field(..., description="Stable provider voice style")

    def __json__(self) -> dict[str, str]:
        """Return this voice option as a JSON-ready mapping."""
        return self.model_dump()


@register_schema_to_swagger
class FollowUpModelOptionDTO(BaseModel):
    """Describe one model and its supported application roles."""

    model: str = Field(..., description="Model identifier")
    display_name: str = Field(..., description="Display label")
    interaction_mode: Literal["text", "live_voice"] = Field(
        ..., description="Follow-up interaction mode"
    )
    allowed_roles: list[Literal["main", "follow_up"]] = Field(
        ..., description="Model picker roles where this model is valid"
    )
    billing_mode: Literal["billable", "free_preview"] = Field(
        ..., description="Current product billing contract"
    )
    voices: list[FollowUpVoiceOptionDTO] = Field(
        default_factory=list, description="Available Live voices"
    )
    credit_multiplier: int | None = Field(
        default=None, description="Output-token credit multiplier"
    )
    credit_multiplier_label: str | None = Field(
        default=None, description="Formatted credit multiplier"
    )
    is_default: bool = Field(default=False, description="Default text model")

    def __json__(self) -> dict[str, object]:
        """Return this follow-up model option as a JSON-ready mapping."""
        return self.model_dump()

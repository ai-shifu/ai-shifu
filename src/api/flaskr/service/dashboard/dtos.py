"""DTOs for teacher-facing analytics dashboard."""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field

from flaskr.common.swagger import register_schema_to_swagger


@register_schema_to_swagger
class DashboardEmptyDTO(BaseModel):
    """Placeholder DTO for initial module wiring."""

    ok: bool = Field(default=True, description="Always true", required=False)

    def __json__(self) -> Dict[str, Any]:
        return {"ok": bool(self.ok)}


@register_schema_to_swagger
class DashboardOutlineDTO(BaseModel):
    """Published outline item exposed to the dashboard."""

    outline_item_bid: str = Field(
        ..., description="Outline item business identifier", required=False
    )
    title: str = Field(..., description="Outline title", required=False)
    type: int = Field(..., description="Outline type", required=False)
    hidden: bool = Field(default=False, description="Hidden flag", required=False)
    parent_bid: str = Field(
        default="", description="Parent outline bid", required=False
    )
    position: str = Field(default="", description="Outline position", required=False)

    def __json__(self) -> Dict[str, Any]:
        return {
            "outline_item_bid": self.outline_item_bid,
            "title": self.title,
            "type": self.type,
            "hidden": bool(self.hidden),
            "parent_bid": self.parent_bid,
            "position": self.position,
        }

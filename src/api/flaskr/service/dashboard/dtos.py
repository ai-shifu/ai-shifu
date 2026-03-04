"""DTOs for teacher-facing analytics dashboard."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from flaskr.common.swagger import register_schema_to_swagger


@register_schema_to_swagger
class DashboardEntrySummaryDTO(BaseModel):
    """Dashboard entry summary metrics."""

    course_count: int = Field(..., description="Visible course count", required=False)
    learner_count: int = Field(
        ..., description="Distinct learner count", required=False
    )
    order_count: int = Field(..., description="Order count", required=False)
    order_amount: str = Field(
        ..., description="Order amount with 2 decimal places", required=False
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "course_count": int(self.course_count),
            "learner_count": int(self.learner_count),
            "order_count": int(self.order_count),
            "order_amount": self.order_amount,
        }


@register_schema_to_swagger
class DashboardEntryCourseItemDTO(BaseModel):
    """Dashboard entry list item for a single course."""

    shifu_bid: str = Field(
        ..., description="Course business identifier", required=False
    )
    shifu_name: str = Field(..., description="Course name", required=False)
    learner_count: int = Field(
        ..., description="Distinct learner count", required=False
    )
    order_count: int = Field(..., description="Order count", required=False)
    order_amount: str = Field(
        ..., description="Order amount with 2 decimal places", required=False
    )
    last_active_at: str = Field(
        default="",
        description="Course last active timestamp (ISO)",
        required=False,
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "shifu_bid": self.shifu_bid,
            "shifu_name": self.shifu_name,
            "learner_count": int(self.learner_count),
            "order_count": int(self.order_count),
            "order_amount": self.order_amount,
            "last_active_at": self.last_active_at,
        }


@register_schema_to_swagger
class DashboardEntryDTO(BaseModel):
    """Dashboard entry response payload."""

    summary: DashboardEntrySummaryDTO = Field(
        ..., description="Dashboard summary metrics", required=False
    )
    page: int = Field(..., description="Current page", required=False)
    page_size: int = Field(..., description="Page size", required=False)
    page_count: int = Field(..., description="Page count", required=False)
    total: int = Field(..., description="Total course count", required=False)
    items: List[DashboardEntryCourseItemDTO] = Field(
        default_factory=list, description="Course rows", required=False
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "summary": self.summary.__json__(),
            "page": int(self.page),
            "page_size": int(self.page_size),
            "page_count": int(self.page_count),
            "total": int(self.total),
            "items": [item.__json__() for item in self.items],
        }

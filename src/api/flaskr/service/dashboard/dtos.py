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
    last_active_at_display: str = Field(
        default="",
        description="Course last active timestamp for direct display",
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
            "last_active_at_display": self.last_active_at_display,
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


@register_schema_to_swagger
class DashboardCourseDetailBasicInfoDTO(BaseModel):
    """Dashboard detail basic course information."""

    shifu_bid: str = Field(
        ..., description="Course business identifier", required=False
    )
    course_name: str = Field(..., description="Course name", required=False)
    created_at: str = Field(
        default="",
        description="Course creation timestamp (ISO)",
        required=False,
    )
    created_at_display: str = Field(
        default="",
        description="Course creation timestamp for direct display",
        required=False,
    )
    chapter_count: int = Field(..., description="Visible lesson count", required=False)
    learner_count: int = Field(
        ..., description="Distinct learner count", required=False
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "shifu_bid": self.shifu_bid,
            "course_name": self.course_name,
            "created_at": self.created_at,
            "created_at_display": self.created_at_display,
            "chapter_count": int(self.chapter_count),
            "learner_count": int(self.learner_count),
        }


@register_schema_to_swagger
class DashboardCourseDetailMetricsDTO(BaseModel):
    """Dashboard detail metrics for a single course."""

    order_count: int = Field(..., description="Order count", required=False)
    order_amount: str = Field(
        ..., description="Order amount with 2 decimal places", required=False
    )
    completed_learner_count: int = Field(
        ..., description="Completed learner count", required=False
    )
    completion_rate: str = Field(
        ..., description="Completion rate percentage with 2 decimals", required=False
    )
    active_learner_count_last_7_days: int = Field(
        ..., description="Distinct active learners in last 7 days", required=False
    )
    total_follow_up_count: int = Field(
        ..., description="Total follow-up question count", required=False
    )
    avg_follow_up_count_per_learner: str = Field(
        ...,
        description="Average follow-up count per learner with 2 decimals",
        required=False,
    )
    avg_learning_duration_seconds: int = Field(
        ..., description="Average learning duration in seconds", required=False
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "order_count": int(self.order_count),
            "order_amount": self.order_amount,
            "completed_learner_count": int(self.completed_learner_count),
            "completion_rate": self.completion_rate,
            "active_learner_count_last_7_days": int(
                self.active_learner_count_last_7_days
            ),
            "total_follow_up_count": int(self.total_follow_up_count),
            "avg_follow_up_count_per_learner": self.avg_follow_up_count_per_learner,
            "avg_learning_duration_seconds": int(self.avg_learning_duration_seconds),
        }


@register_schema_to_swagger
class DashboardCourseDetailSectionChartDTO(BaseModel):
    """Dashboard chart point for per-section learning and follow-up stats."""

    chapter_outline_item_bid: str = Field(
        ..., description="Parent chapter outline item bid", required=False
    )
    chapter_title: str = Field(..., description="Parent chapter title", required=False)
    section_outline_item_bid: str = Field(
        ..., description="Section outline item bid", required=False
    )
    section_title: str = Field(..., description="Section title", required=False)
    position: str = Field(..., description="Section outline position", required=False)
    learning_user_count: int = Field(
        ..., description="Distinct learner count for this section", required=False
    )
    learning_record_count: int = Field(
        ..., description="Total learning record count for this section", required=False
    )
    follow_up_user_count: int = Field(
        ...,
        description="Distinct follow-up user count for this section",
        required=False,
    )
    follow_up_question_count: int = Field(
        ...,
        description="Total follow-up question count for this section",
        required=False,
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "chapter_outline_item_bid": self.chapter_outline_item_bid,
            "chapter_title": self.chapter_title,
            "section_outline_item_bid": self.section_outline_item_bid,
            "section_title": self.section_title,
            "position": self.position,
            "learning_user_count": self.learning_user_count,
            "learning_record_count": self.learning_record_count,
            "follow_up_user_count": self.follow_up_user_count,
            "follow_up_question_count": self.follow_up_question_count,
        }


@register_schema_to_swagger
class DashboardCourseDetailChartsDTO(BaseModel):
    """Dashboard detail chart data."""

    sections: List[DashboardCourseDetailSectionChartDTO] = Field(
        default_factory=list,
        description="Per-section learning and follow-up stats",
        required=False,
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "sections": [item.__json__() for item in self.sections],
        }


@register_schema_to_swagger
class DashboardCourseDetailDTO(BaseModel):
    """Dashboard detail response payload."""

    basic_info: DashboardCourseDetailBasicInfoDTO = Field(
        ..., description="Course basic information", required=False
    )
    metrics: DashboardCourseDetailMetricsDTO = Field(
        ..., description="Course detail metrics", required=False
    )
    charts: DashboardCourseDetailChartsDTO = Field(
        default_factory=DashboardCourseDetailChartsDTO,
        description="Course detail chart data",
        required=False,
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "basic_info": self.basic_info.__json__(),
            "metrics": self.metrics.__json__(),
            "charts": self.charts.__json__(),
        }

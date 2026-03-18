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
class DashboardSeriesPointDTO(BaseModel):
    """A single chart series point."""

    label: str = Field(..., description="Point label", required=False)
    value: int = Field(..., description="Point value", required=False)

    def __json__(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "value": int(self.value),
        }


@register_schema_to_swagger
class DashboardCourseDetailQuestionsByChapterItemDTO(BaseModel):
    """Chart item for follow-up questions by chapter."""

    outline_item_bid: str = Field(
        ..., description="Outline item business identifier", required=False
    )
    title: str = Field(..., description="Outline title", required=False)
    ask_count: int = Field(..., description="Follow-up ask count", required=False)

    def __json__(self) -> Dict[str, Any]:
        return {
            "outline_item_bid": self.outline_item_bid,
            "title": self.title,
            "ask_count": int(self.ask_count),
        }


@register_schema_to_swagger
class DashboardCourseDetailChartsDTO(BaseModel):
    """Chart payloads for the course detail page."""

    questions_by_chapter: List[DashboardCourseDetailQuestionsByChapterItemDTO] = Field(
        default_factory=list,
        description="Follow-up question distribution by chapter",
        required=False,
    )
    questions_by_time: List[DashboardSeriesPointDTO] = Field(
        default_factory=list,
        description="Follow-up question distribution by time",
        required=False,
    )
    learning_activity_trend: List[DashboardSeriesPointDTO] = Field(
        default_factory=list,
        description="Learning activity trend",
        required=False,
    )
    chapter_progress_distribution: List[DashboardSeriesPointDTO] = Field(
        default_factory=list,
        description="Chapter progress distribution",
        required=False,
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "questions_by_chapter": [
                item.__json__() for item in self.questions_by_chapter
            ],
            "questions_by_time": [item.__json__() for item in self.questions_by_time],
            "learning_activity_trend": [
                item.__json__() for item in self.learning_activity_trend
            ],
            "chapter_progress_distribution": [
                item.__json__() for item in self.chapter_progress_distribution
            ],
        }


@register_schema_to_swagger
class DashboardCourseDetailLearnerItemDTO(BaseModel):
    """Learner summary row for course detail page."""

    user_bid: str = Field(..., description="User business identifier", required=False)
    nickname: str = Field(..., description="User nickname", required=False)
    progress_percent: str = Field(
        ...,
        description="Completed leaf chapter percentage with 2 decimals",
        required=False,
    )
    follow_up_ask_count: int = Field(
        default=0,
        description="Follow-up ask count within the applied range",
        required=False,
    )
    last_active_at: str = Field(
        default="",
        description="Last active timestamp (ISO) within the applied range",
        required=False,
    )
    last_active_at_display: str = Field(
        default="",
        description="Last active timestamp for direct display",
        required=False,
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "user_bid": self.user_bid,
            "nickname": self.nickname,
            "progress_percent": self.progress_percent,
            "follow_up_ask_count": int(self.follow_up_ask_count),
            "last_active_at": self.last_active_at,
            "last_active_at_display": self.last_active_at_display,
        }


@register_schema_to_swagger
class DashboardCourseDetailLearnersDTO(BaseModel):
    """Paginated learner payload for course detail page."""

    page: int = Field(..., description="Current learner page", required=False)
    page_size: int = Field(..., description="Learner page size", required=False)
    total: int = Field(..., description="Total learner count", required=False)
    items: List[DashboardCourseDetailLearnerItemDTO] = Field(
        default_factory=list,
        description="Learner rows",
        required=False,
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "page": int(self.page),
            "page_size": int(self.page_size),
            "total": int(self.total),
            "items": [item.__json__() for item in self.items],
        }


@register_schema_to_swagger
class DashboardCourseDetailAppliedRangeDTO(BaseModel):
    """Applied date range for behavior-based metrics."""

    start_date: str = Field(
        default="",
        description="Applied start date (YYYY-MM-DD)",
        required=False,
    )
    end_date: str = Field(
        default="",
        description="Applied end date (YYYY-MM-DD)",
        required=False,
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
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
        ..., description="Course detail chart payloads", required=False
    )
    learners: DashboardCourseDetailLearnersDTO = Field(
        ..., description="Course learner list payload", required=False
    )
    applied_range: DashboardCourseDetailAppliedRangeDTO = Field(
        ..., description="Applied date range for behavior metrics", required=False
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "basic_info": self.basic_info.__json__(),
            "metrics": self.metrics.__json__(),
            "charts": self.charts.__json__(),
            "learners": self.learners.__json__(),
            "applied_range": self.applied_range.__json__(),
        }

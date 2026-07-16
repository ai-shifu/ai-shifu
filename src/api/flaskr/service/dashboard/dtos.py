"""DTOs for teacher-facing analytics dashboard."""

from __future__ import annotations

from datetime import datetime

from typing import List

from pydantic import BaseModel, Field

from flaskr.common.swagger import register_schema_to_swagger
from flaskr.service.common.dto_base import AutoJsonMixin


@register_schema_to_swagger
class DashboardEntrySummaryDTO(AutoJsonMixin, BaseModel):
    """Dashboard entry summary metrics."""

    course_count: int = Field(..., description="Visible course count", required=False)
    learner_count: int = Field(
        ..., description="Distinct learner count", required=False
    )
    order_count: int = Field(..., description="Order count", required=False)
    order_amount: str = Field(
        ..., description="Order amount with 2 decimal places", required=False
    )


@register_schema_to_swagger
class DashboardEntryCourseItemDTO(AutoJsonMixin, BaseModel):
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
    last_active_at: datetime | None = Field(
        default=None,
        description="Course last active timestamp (ISO)",
        required=False,
    )


@register_schema_to_swagger
class DashboardEntryDTO(AutoJsonMixin, BaseModel):
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


@register_schema_to_swagger
class DashboardCourseDetailBasicInfoDTO(AutoJsonMixin, BaseModel):
    """Dashboard detail basic course information."""

    shifu_bid: str = Field(
        ..., description="Course business identifier", required=False
    )
    course_name: str = Field(..., description="Course name", required=False)
    course_status: str = Field(
        default="published",
        description="Course status for creator dashboard",
        required=False,
    )
    created_at: datetime | None = Field(
        default=None,
        description="Course creation timestamp (ISO)",
        required=False,
    )
    chapter_count: int = Field(..., description="Visible lesson count", required=False)
    learner_count: int = Field(
        ..., description="Distinct learner count", required=False
    )


@register_schema_to_swagger
class DashboardCourseDetailMetricsDTO(AutoJsonMixin, BaseModel):
    """Dashboard detail metrics for a single course."""

    order_count: int = Field(..., description="Order count", required=False)
    order_amount: str = Field(
        ..., description="Order amount with 2 decimal places", required=False
    )
    new_learner_count_last_7_days: int = Field(
        ..., description="Distinct new learners in last 7 days", required=False
    )
    learning_learner_count: int = Field(
        ..., description="Learners currently in progress", required=False
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
    rating_score: str = Field(
        default="",
        description="Average course rating with 1 decimal place",
        required=False,
    )


@register_schema_to_swagger
class DashboardCourseDetailLearnerItemDTO(AutoJsonMixin, BaseModel):
    """Dashboard learner row for a single course."""

    user_bid: str = Field(
        ..., description="Learner business identifier", required=False
    )
    mobile: str = Field(default="", description="Learner mobile", required=False)
    email: str = Field(default="", description="Learner email", required=False)
    nickname: str = Field(default="", description="Learner nickname", required=False)
    learned_lesson_count: int = Field(
        ..., description="Completed or started visible lesson count", required=False
    )
    total_lesson_count: int = Field(
        ..., description="Total visible lesson count", required=False
    )
    learning_status: str = Field(
        ..., description="Learner progress status", required=False
    )
    follow_up_count: int = Field(
        ..., description="Follow-up question count", required=False
    )
    last_learning_at: datetime | None = Field(
        default=None,
        description="Last learning timestamp (ISO)",
        required=False,
    )
    joined_at: datetime | None = Field(
        default=None,
        description="Joined-at timestamp (ISO)",
        required=False,
    )


@register_schema_to_swagger
class DashboardCourseDetailLearnersDTO(AutoJsonMixin, BaseModel):
    """Dashboard detail learner list payload."""

    page: int = Field(..., description="Current page", required=False)
    page_size: int = Field(..., description="Page size", required=False)
    page_count: int = Field(..., description="Page count", required=False)
    total: int = Field(..., description="Total learner count", required=False)
    items: List[DashboardCourseDetailLearnerItemDTO] = Field(
        default_factory=list, description="Learner rows", required=False
    )


@register_schema_to_swagger
class DashboardCourseDetailDTO(AutoJsonMixin, BaseModel):
    """Dashboard detail response payload."""

    basic_info: DashboardCourseDetailBasicInfoDTO = Field(
        ..., description="Course basic information", required=False
    )
    metrics: DashboardCourseDetailMetricsDTO = Field(
        ..., description="Course detail metrics", required=False
    )


@register_schema_to_swagger
class DashboardCourseFollowUpSummaryDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up summary metrics for a single course."""

    follow_up_count: int = Field(..., description="Follow-up count", required=False)
    user_count: int = Field(
        ..., description="Distinct learner count with follow-ups", required=False
    )
    lesson_count: int = Field(
        ..., description="Distinct lesson count with follow-ups", required=False
    )
    latest_follow_up_at: datetime | None = Field(
        default=None,
        description="Latest follow-up time for direct display",
        required=False,
    )


@register_schema_to_swagger
class DashboardCourseFollowUpItemDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up list row for a single course."""

    generated_block_bid: str = Field(
        ..., description="Follow-up business identifier", required=False
    )
    progress_record_bid: str = Field(
        default="", description="Progress record identifier", required=False
    )
    user_bid: str = Field(default="", description="Learner identifier", required=False)
    mobile: str = Field(default="", description="Learner mobile", required=False)
    email: str = Field(default="", description="Learner email", required=False)
    nickname: str = Field(default="", description="Learner nickname", required=False)
    chapter_title: str = Field(default="", description="Chapter title", required=False)
    lesson_title: str = Field(default="", description="Lesson title", required=False)
    follow_up_content: str = Field(
        default="", description="Follow-up content", required=False
    )
    has_source_output: bool = Field(
        default=False,
        description="Whether the original output source could be resolved",
        required=False,
    )
    turn_index: int = Field(default=0, description="Turn index", required=False)
    created_at: datetime | None = Field(
        default=None,
        description="Follow-up created time for direct display",
        required=False,
    )


@register_schema_to_swagger
class DashboardCourseFollowUpListDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up list response payload."""

    summary: DashboardCourseFollowUpSummaryDTO = Field(
        ..., description="Follow-up summary", required=False
    )
    page: int = Field(..., description="Current page", required=False)
    page_size: int = Field(..., description="Page size", required=False)
    page_count: int = Field(..., description="Page count", required=False)
    total: int = Field(..., description="Total follow-up count", required=False)
    items: List[DashboardCourseFollowUpItemDTO] = Field(
        default_factory=list, description="Follow-up rows", required=False
    )


@register_schema_to_swagger
class DashboardCourseFollowUpDetailBasicInfoDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up detail basic information."""

    generated_block_bid: str = Field(
        ..., description="Follow-up business identifier", required=False
    )
    progress_record_bid: str = Field(
        default="", description="Progress record identifier", required=False
    )
    user_bid: str = Field(default="", description="Learner identifier", required=False)
    mobile: str = Field(default="", description="Learner mobile", required=False)
    email: str = Field(default="", description="Learner email", required=False)
    nickname: str = Field(default="", description="Learner nickname", required=False)
    chapter_title: str = Field(default="", description="Chapter title", required=False)
    lesson_title: str = Field(default="", description="Lesson title", required=False)
    created_at: datetime | None = Field(
        default=None,
        description="Follow-up created time for direct display",
        required=False,
    )
    turn_index: int = Field(default=0, description="Turn index", required=False)


@register_schema_to_swagger
class DashboardCourseFollowUpCurrentRecordDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up current record detail."""

    follow_up_content: str = Field(
        default="", description="Current follow-up content", required=False
    )
    answer_content: str = Field(
        default="", description="Current answer content", required=False
    )


@register_schema_to_swagger
class DashboardCourseFollowUpTimelineItemDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up timeline row."""

    role: str = Field(..., description="Timeline role", required=False)
    content: str = Field(default="", description="Timeline content", required=False)
    created_at: datetime | None = Field(
        default=None,
        description="Timeline created time for direct display",
        required=False,
    )
    is_current: bool = Field(default=False, description="Current turn", required=False)


@register_schema_to_swagger
class DashboardCourseFollowUpDetailDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up detail response payload."""

    basic_info: DashboardCourseFollowUpDetailBasicInfoDTO = Field(
        ..., description="Follow-up basic information", required=False
    )
    current_record: DashboardCourseFollowUpCurrentRecordDTO = Field(
        ..., description="Current follow-up record", required=False
    )
    timeline: List[DashboardCourseFollowUpTimelineItemDTO] = Field(
        default_factory=list, description="Follow-up timeline", required=False
    )


@register_schema_to_swagger
class DashboardCourseRatingSummaryDTO(AutoJsonMixin, BaseModel):
    """Dashboard rating summary metrics for a single course."""

    average_score: str = Field(
        default="",
        description="Average rating score with 1 decimal place",
        required=False,
    )
    rating_count: int = Field(..., description="Rating count", required=False)
    user_count: int = Field(
        ..., description="Distinct learner count with ratings", required=False
    )
    latest_rated_at: datetime | None = Field(
        default=None,
        description="Latest rating time for direct display",
        required=False,
    )


@register_schema_to_swagger
class DashboardCourseRatingItemDTO(AutoJsonMixin, BaseModel):
    """Dashboard rating list row for a single course."""

    lesson_feedback_bid: str = Field(
        ..., description="Rating business identifier", required=False
    )
    progress_record_bid: str = Field(
        default="", description="Progress record identifier", required=False
    )
    user_bid: str = Field(default="", description="Learner identifier", required=False)
    mobile: str = Field(default="", description="Learner mobile", required=False)
    email: str = Field(default="", description="Learner email", required=False)
    nickname: str = Field(default="", description="Learner nickname", required=False)
    chapter_title: str = Field(default="", description="Chapter title", required=False)
    lesson_title: str = Field(default="", description="Lesson title", required=False)
    score: int = Field(..., description="Rating score", required=False)
    comment: str = Field(default="", description="Rating comment", required=False)
    rated_at: datetime | None = Field(
        default=None,
        description="Rating time for direct display",
        required=False,
    )


@register_schema_to_swagger
class DashboardCourseRatingListDTO(AutoJsonMixin, BaseModel):
    """Dashboard rating list response payload."""

    summary: DashboardCourseRatingSummaryDTO = Field(
        ..., description="Rating summary", required=False
    )
    page: int = Field(..., description="Current page", required=False)
    page_size: int = Field(..., description="Page size", required=False)
    page_count: int = Field(..., description="Page count", required=False)
    total: int = Field(..., description="Total rating count", required=False)
    items: List[DashboardCourseRatingItemDTO] = Field(
        default_factory=list, description="Rating rows", required=False
    )

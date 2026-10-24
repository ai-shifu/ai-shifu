"""DTOs for teacher-facing analytics dashboard."""

from __future__ import annotations

from datetime import datetime

from flaskr.common.swagger import register_schema_to_swagger
from flaskr.service.common.dto_base import AutoJsonMixin
from pydantic import BaseModel, Field


@register_schema_to_swagger
class DashboardEntrySummaryDTO(AutoJsonMixin, BaseModel):
    """Dashboard entry summary metrics."""

    course_count: int = Field(..., description="Visible course count")
    learner_count: int = Field(..., description="Distinct learner count")
    order_count: int = Field(..., description="Order count")
    order_amount: str = Field(..., description="Order amount with 2 decimal places")


@register_schema_to_swagger
class DashboardEntryCourseItemDTO(AutoJsonMixin, BaseModel):
    """Dashboard entry list item for a single course."""

    shifu_bid: str = Field(..., description="Course business identifier")
    shifu_name: str = Field(..., description="Course name")
    learner_count: int = Field(..., description="Distinct learner count")
    order_count: int = Field(..., description="Order count")
    order_amount: str = Field(..., description="Order amount with 2 decimal places")
    last_active_at: datetime | None = Field(
        default=None,
        description="Course last active timestamp (ISO)",
    )


@register_schema_to_swagger
class DashboardEntryDTO(AutoJsonMixin, BaseModel):
    """Dashboard entry response payload."""

    summary: DashboardEntrySummaryDTO = Field(
        ..., description="Dashboard summary metrics"
    )
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Page size")
    page_count: int = Field(..., description="Page count")
    total: int = Field(..., description="Total course count")
    items: list[DashboardEntryCourseItemDTO] = Field(
        default_factory=list, description="Course rows"
    )


@register_schema_to_swagger
class DashboardCourseDetailBasicInfoDTO(AutoJsonMixin, BaseModel):
    """Dashboard detail basic course information."""

    shifu_bid: str = Field(..., description="Course business identifier")
    course_name: str = Field(..., description="Course name")
    course_status: str = Field(
        default="published",
        description="Course status for creator dashboard",
    )
    created_at: datetime | None = Field(
        default=None,
        description="Course creation timestamp (ISO)",
    )
    chapter_count: int = Field(..., description="Visible lesson count")
    learner_count: int = Field(..., description="Distinct learner count")


@register_schema_to_swagger
class DashboardCourseDetailMetricsDTO(AutoJsonMixin, BaseModel):
    """Dashboard detail metrics for a single course."""

    order_count: int = Field(..., description="Order count")
    order_amount: str = Field(..., description="Order amount with 2 decimal places")
    learning_learner_count: int = Field(
        ..., description="Learners currently in progress"
    )
    completed_learner_count: int = Field(..., description="Completed learner count")
    completion_rate: str = Field(
        ..., description="Completion rate percentage with 2 decimals"
    )
    total_follow_up_count: int = Field(
        ..., description="Total follow-up question count"
    )
    rating_score: str = Field(
        default="",
        description="Average course rating with 1 decimal place",
    )


@register_schema_to_swagger
class DashboardCourseDetailLearnerItemDTO(AutoJsonMixin, BaseModel):
    """Dashboard learner row for a single course."""

    user_bid: str = Field(..., description="Learner business identifier")
    mobile: str = Field(default="", description="Learner mobile")
    email: str = Field(default="", description="Learner email")
    nickname: str = Field(default="", description="Learner nickname")
    learned_lesson_count: int = Field(
        ..., description="Completed or started visible lesson count"
    )
    total_lesson_count: int = Field(..., description="Total visible lesson count")
    learning_status: str = Field(..., description="Learner progress status")
    follow_up_count: int = Field(..., description="Follow-up question count")
    last_learning_at: datetime | None = Field(
        default=None,
        description="Last learning timestamp (ISO)",
    )
    joined_at: datetime | None = Field(
        default=None,
        description="Joined-at timestamp (ISO)",
    )


@register_schema_to_swagger
class DashboardCourseDetailLearnersDTO(AutoJsonMixin, BaseModel):
    """Dashboard detail learner list payload."""

    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Page size")
    page_count: int = Field(..., description="Page count")
    total: int = Field(..., description="Total learner count")
    items: list[DashboardCourseDetailLearnerItemDTO] = Field(
        default_factory=list, description="Learner rows"
    )


@register_schema_to_swagger
class DashboardCourseLearningModeMetricDTO(AutoJsonMixin, BaseModel):
    """Dashboard per-learning-mode performance metric."""

    mode: str = Field(..., description="Learning mode")
    participant_count: int = Field(..., description="Distinct participant count")
    consumed_credits: str = Field(..., description="Total consumed credits")
    consumption_speed: str = Field(
        ...,
        description="Average consumed credits per day in the last 7 days",
    )
    average_consumed_credits: str = Field(
        ..., description="Average consumed credits per participant"
    )


@register_schema_to_swagger
class DashboardCourseDetailDTO(AutoJsonMixin, BaseModel):
    """Dashboard detail response payload."""

    basic_info: DashboardCourseDetailBasicInfoDTO = Field(
        ..., description="Course basic information"
    )
    metrics: DashboardCourseDetailMetricsDTO = Field(
        ..., description="Course detail metrics"
    )
    learning_mode_metrics: list[DashboardCourseLearningModeMetricDTO] = Field(
        default_factory=list,
        description="Per-learning-mode performance metrics",
    )


@register_schema_to_swagger
class DashboardCourseFollowUpSummaryDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up summary metrics for a single course."""

    follow_up_count: int = Field(..., description="Follow-up count")
    user_count: int = Field(..., description="Distinct learner count with follow-ups")
    lesson_count: int = Field(..., description="Distinct lesson count with follow-ups")
    latest_follow_up_at: datetime | None = Field(
        default=None,
        description="Latest follow-up time for direct display",
    )


@register_schema_to_swagger
class DashboardCourseFollowUpItemDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up list row for a single course."""

    generated_block_bid: str = Field(..., description="Follow-up business identifier")
    progress_record_bid: str = Field(
        default="", description="Progress record identifier"
    )
    user_bid: str = Field(default="", description="Learner identifier")
    mobile: str = Field(default="", description="Learner mobile")
    email: str = Field(default="", description="Learner email")
    nickname: str = Field(default="", description="Learner nickname")
    chapter_title: str = Field(default="", description="Chapter title")
    lesson_title: str = Field(default="", description="Lesson title")
    follow_up_content: str = Field(default="", description="Follow-up content")
    has_source_output: bool = Field(
        default=False,
        description="Whether the original output source could be resolved",
    )
    turn_index: int = Field(default=0, description="Turn index")
    created_at: datetime | None = Field(
        default=None,
        description="Follow-up created time for direct display",
    )


@register_schema_to_swagger
class DashboardCourseFollowUpListDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up list response payload."""

    summary: DashboardCourseFollowUpSummaryDTO = Field(
        ..., description="Follow-up summary"
    )
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Page size")
    page_count: int = Field(..., description="Page count")
    total: int = Field(..., description="Total follow-up count")
    items: list[DashboardCourseFollowUpItemDTO] = Field(
        default_factory=list, description="Follow-up rows"
    )


@register_schema_to_swagger
class DashboardCourseFollowUpDetailBasicInfoDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up detail basic information."""

    generated_block_bid: str = Field(..., description="Follow-up business identifier")
    progress_record_bid: str = Field(
        default="", description="Progress record identifier"
    )
    user_bid: str = Field(default="", description="Learner identifier")
    mobile: str = Field(default="", description="Learner mobile")
    email: str = Field(default="", description="Learner email")
    nickname: str = Field(default="", description="Learner nickname")
    chapter_title: str = Field(default="", description="Chapter title")
    lesson_title: str = Field(default="", description="Lesson title")
    created_at: datetime | None = Field(
        default=None,
        description="Follow-up created time for direct display",
    )
    turn_index: int = Field(default=0, description="Turn index")


@register_schema_to_swagger
class DashboardCourseFollowUpCurrentRecordDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up current record detail."""

    follow_up_content: str = Field(default="", description="Current follow-up content")
    answer_content: str = Field(default="", description="Current answer content")


@register_schema_to_swagger
class DashboardCourseFollowUpTimelineItemDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up timeline row."""

    role: str = Field(..., description="Timeline role")
    content: str = Field(default="", description="Timeline content")
    created_at: datetime | None = Field(
        default=None,
        description="Timeline created time for direct display",
    )
    is_current: bool = Field(default=False, description="Current turn")


@register_schema_to_swagger
class DashboardCourseFollowUpDetailDTO(AutoJsonMixin, BaseModel):
    """Dashboard follow-up detail response payload."""

    basic_info: DashboardCourseFollowUpDetailBasicInfoDTO = Field(
        ..., description="Follow-up basic information"
    )
    current_record: DashboardCourseFollowUpCurrentRecordDTO = Field(
        ..., description="Current follow-up record"
    )
    timeline: list[DashboardCourseFollowUpTimelineItemDTO] = Field(
        default_factory=list, description="Follow-up timeline"
    )


@register_schema_to_swagger
class DashboardCourseRatingSummaryDTO(AutoJsonMixin, BaseModel):
    """Dashboard rating summary metrics for a single course."""

    average_score: str = Field(
        default="",
        description="Average rating score with 1 decimal place",
    )
    rating_count: int = Field(..., description="Rating count")
    user_count: int = Field(..., description="Distinct learner count with ratings")
    latest_rated_at: datetime | None = Field(
        default=None,
        description="Latest rating time for direct display",
    )


@register_schema_to_swagger
class DashboardCourseRatingItemDTO(AutoJsonMixin, BaseModel):
    """Dashboard rating list row for a single course."""

    lesson_feedback_bid: str = Field(..., description="Rating business identifier")
    progress_record_bid: str = Field(
        default="", description="Progress record identifier"
    )
    user_bid: str = Field(default="", description="Learner identifier")
    mobile: str = Field(default="", description="Learner mobile")
    email: str = Field(default="", description="Learner email")
    nickname: str = Field(default="", description="Learner nickname")
    chapter_title: str = Field(default="", description="Chapter title")
    lesson_title: str = Field(default="", description="Lesson title")
    score: int = Field(..., description="Rating score")
    comment: str = Field(default="", description="Rating comment")
    rated_at: datetime | None = Field(
        default=None,
        description="Rating time for direct display",
    )


@register_schema_to_swagger
class DashboardCourseRatingListDTO(AutoJsonMixin, BaseModel):
    """Dashboard rating list response payload."""

    summary: DashboardCourseRatingSummaryDTO = Field(..., description="Rating summary")
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Page size")
    page_count: int = Field(..., description="Page count")
    total: int = Field(..., description="Total rating count")
    items: list[DashboardCourseRatingItemDTO] = Field(
        default_factory=list, description="Rating rows"
    )

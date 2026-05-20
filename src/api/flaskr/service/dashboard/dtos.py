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
    course_status: str = Field(
        default="published",
        description="Course status for creator dashboard",
        required=False,
    )
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
            "course_status": self.course_status,
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

    def __json__(self) -> Dict[str, Any]:
        return {
            "order_count": int(self.order_count),
            "order_amount": self.order_amount,
            "new_learner_count_last_7_days": int(self.new_learner_count_last_7_days),
            "learning_learner_count": int(self.learning_learner_count),
            "completed_learner_count": int(self.completed_learner_count),
            "completion_rate": self.completion_rate,
            "active_learner_count_last_7_days": int(
                self.active_learner_count_last_7_days
            ),
            "total_follow_up_count": int(self.total_follow_up_count),
            "rating_score": self.rating_score,
        }


@register_schema_to_swagger
class DashboardCourseDetailLearnerItemDTO(BaseModel):
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
    last_learning_at: str = Field(
        default="",
        description="Last learning timestamp (ISO)",
        required=False,
    )
    last_learning_at_display: str = Field(
        default="",
        description="Last learning timestamp for direct display",
        required=False,
    )
    joined_at: str = Field(
        default="",
        description="Joined-at timestamp (ISO)",
        required=False,
    )
    joined_at_display: str = Field(
        default="",
        description="Joined-at timestamp for direct display",
        required=False,
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "user_bid": self.user_bid,
            "mobile": self.mobile,
            "email": self.email,
            "nickname": self.nickname,
            "learned_lesson_count": int(self.learned_lesson_count),
            "total_lesson_count": int(self.total_lesson_count),
            "learning_status": self.learning_status,
            "follow_up_count": int(self.follow_up_count),
            "last_learning_at": self.last_learning_at,
            "last_learning_at_display": self.last_learning_at_display,
            "joined_at": self.joined_at,
            "joined_at_display": self.joined_at_display,
        }


@register_schema_to_swagger
class DashboardCourseDetailLearnersDTO(BaseModel):
    """Dashboard detail learner list payload."""

    page: int = Field(..., description="Current page", required=False)
    page_size: int = Field(..., description="Page size", required=False)
    page_count: int = Field(..., description="Page count", required=False)
    total: int = Field(..., description="Total learner count", required=False)
    items: List[DashboardCourseDetailLearnerItemDTO] = Field(
        default_factory=list, description="Learner rows", required=False
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "page": int(self.page),
            "page_size": int(self.page_size),
            "page_count": int(self.page_count),
            "total": int(self.total),
            "items": [item.__json__() for item in self.items],
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

    def __json__(self) -> Dict[str, Any]:
        return {
            "basic_info": self.basic_info.__json__(),
            "metrics": self.metrics.__json__(),
        }


@register_schema_to_swagger
class DashboardCourseFollowUpSummaryDTO(BaseModel):
    """Dashboard follow-up summary metrics for a single course."""

    follow_up_count: int = Field(..., description="Follow-up count", required=False)
    user_count: int = Field(
        ..., description="Distinct learner count with follow-ups", required=False
    )
    lesson_count: int = Field(
        ..., description="Distinct lesson count with follow-ups", required=False
    )
    latest_follow_up_at: str = Field(
        default="",
        description="Latest follow-up time for direct display",
        required=False,
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "follow_up_count": int(self.follow_up_count),
            "user_count": int(self.user_count),
            "lesson_count": int(self.lesson_count),
            "latest_follow_up_at": self.latest_follow_up_at,
        }


@register_schema_to_swagger
class DashboardCourseFollowUpItemDTO(BaseModel):
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
    turn_index: int = Field(default=0, description="Turn index", required=False)
    created_at: str = Field(
        default="",
        description="Follow-up created time for direct display",
        required=False,
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "generated_block_bid": self.generated_block_bid,
            "progress_record_bid": self.progress_record_bid,
            "user_bid": self.user_bid,
            "mobile": self.mobile,
            "email": self.email,
            "nickname": self.nickname,
            "chapter_title": self.chapter_title,
            "lesson_title": self.lesson_title,
            "follow_up_content": self.follow_up_content,
            "turn_index": int(self.turn_index),
            "created_at": self.created_at,
        }


@register_schema_to_swagger
class DashboardCourseFollowUpListDTO(BaseModel):
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
class DashboardCourseFollowUpDetailBasicInfoDTO(BaseModel):
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
    created_at: str = Field(
        default="",
        description="Follow-up created time for direct display",
        required=False,
    )
    turn_index: int = Field(default=0, description="Turn index", required=False)

    def __json__(self) -> Dict[str, Any]:
        return {
            "generated_block_bid": self.generated_block_bid,
            "progress_record_bid": self.progress_record_bid,
            "user_bid": self.user_bid,
            "mobile": self.mobile,
            "email": self.email,
            "nickname": self.nickname,
            "chapter_title": self.chapter_title,
            "lesson_title": self.lesson_title,
            "created_at": self.created_at,
            "turn_index": int(self.turn_index),
        }


@register_schema_to_swagger
class DashboardCourseFollowUpCurrentRecordDTO(BaseModel):
    """Dashboard follow-up current record detail."""

    follow_up_content: str = Field(
        default="", description="Current follow-up content", required=False
    )
    answer_content: str = Field(
        default="", description="Current answer content", required=False
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "follow_up_content": self.follow_up_content,
            "answer_content": self.answer_content,
        }


@register_schema_to_swagger
class DashboardCourseFollowUpTimelineItemDTO(BaseModel):
    """Dashboard follow-up timeline row."""

    role: str = Field(..., description="Timeline role", required=False)
    content: str = Field(default="", description="Timeline content", required=False)
    created_at: str = Field(
        default="",
        description="Timeline created time for direct display",
        required=False,
    )
    is_current: bool = Field(default=False, description="Current turn", required=False)

    def __json__(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
            "is_current": bool(self.is_current),
        }


@register_schema_to_swagger
class DashboardCourseFollowUpDetailDTO(BaseModel):
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

    def __json__(self) -> Dict[str, Any]:
        return {
            "basic_info": self.basic_info.__json__(),
            "current_record": self.current_record.__json__(),
            "timeline": [item.__json__() for item in self.timeline],
        }


@register_schema_to_swagger
class DashboardCourseRatingSummaryDTO(BaseModel):
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
    latest_rated_at: str = Field(
        default="",
        description="Latest rating time for direct display",
        required=False,
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "average_score": self.average_score,
            "rating_count": int(self.rating_count),
            "user_count": int(self.user_count),
            "latest_rated_at": self.latest_rated_at,
        }


@register_schema_to_swagger
class DashboardCourseRatingItemDTO(BaseModel):
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
    rated_at: str = Field(
        default="",
        description="Rating time for direct display",
        required=False,
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "lesson_feedback_bid": self.lesson_feedback_bid,
            "progress_record_bid": self.progress_record_bid,
            "user_bid": self.user_bid,
            "mobile": self.mobile,
            "email": self.email,
            "nickname": self.nickname,
            "chapter_title": self.chapter_title,
            "lesson_title": self.lesson_title,
            "score": int(self.score),
            "comment": self.comment,
            "rated_at": self.rated_at,
        }


@register_schema_to_swagger
class DashboardCourseRatingListDTO(BaseModel):
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

    def __json__(self) -> Dict[str, Any]:
        return {
            "summary": self.summary.__json__(),
            "page": int(self.page),
            "page_size": int(self.page_size),
            "page_count": int(self.page_count),
            "total": int(self.total),
            "items": [item.__json__() for item in self.items],
        }

"""DTOs for operator course admin endpoints.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

from datetime import datetime

from flaskr.common.swagger import register_schema_to_swagger
from pydantic import BaseModel, ConfigDict, Field


@register_schema_to_swagger
class AdminOperationCourseSummaryDTO(BaseModel):
    """Course summary shown in the operator course list."""

    shifu_bid: str = Field(..., description="Course business identifier")
    course_name: str = Field(..., description="Course name")
    course_status: str = Field(..., description="Course status")
    price: str = Field(..., description="Course price")
    llm_model: str = Field(..., description="Effective configured course model index")
    tts_model: str = Field(..., description="Course TTS model")
    has_course_prompt: bool = Field(
        ...,
        description="Whether the course has a course-level system prompt",
    )
    creator_user_bid: str = Field(..., description="Creator user business identifier")
    creator_mobile: str = Field(..., description="Creator mobile")
    creator_email: str = Field(..., description="Creator email")
    creator_nickname: str = Field(..., description="Creator nickname")
    updater_user_bid: str = Field(..., description="Updater user business identifier")
    updater_mobile: str = Field(..., description="Updater mobile")
    updater_email: str = Field(..., description="Updater email")
    updater_nickname: str = Field(..., description="Updater nickname")
    created_at: datetime | None = Field(..., description="Created at")
    updated_at: datetime | None = Field(..., description="Updated at")

    def __init__(
        self,
        shifu_bid: str,
        course_name: str,
        course_status: str,
        price: str,
        llm_model: str,
        tts_model: str,
        has_course_prompt: bool,
        creator_user_bid: str,
        creator_mobile: str,
        creator_email: str,
        creator_nickname: str,
        updater_user_bid: str,
        updater_mobile: str,
        updater_email: str,
        updater_nickname: str,
        created_at: datetime | None,
        updated_at: datetime | None,
    ) -> None:
        """Build the admin operation course summary payload."""
        super().__init__(
            shifu_bid=shifu_bid,
            course_name=course_name,
            course_status=course_status,
            price=price,
            llm_model=llm_model,
            tts_model=tts_model,
            has_course_prompt=has_course_prompt,
            creator_user_bid=creator_user_bid,
            creator_mobile=creator_mobile,
            creator_email=creator_email,
            creator_nickname=creator_nickname,
            updater_user_bid=updater_user_bid,
            updater_mobile=updater_mobile,
            updater_email=updater_email,
            updater_nickname=updater_nickname,
            created_at=created_at,
            updated_at=updated_at,
        )

    def __json__(self) -> dict:
        """Return the operator course summary as JSON-compatible data."""
        return {
            "shifu_bid": self.shifu_bid,
            "course_name": self.course_name,
            "course_status": self.course_status,
            "price": self.price,
            "llm_model": self.llm_model,
            "tts_model": self.tts_model,
            "has_course_prompt": self.has_course_prompt,
            "creator_user_bid": self.creator_user_bid,
            "creator_mobile": self.creator_mobile,
            "creator_email": self.creator_email,
            "creator_nickname": self.creator_nickname,
            "updater_user_bid": self.updater_user_bid,
            "updater_mobile": self.updater_mobile,
            "updater_email": self.updater_email,
            "updater_nickname": self.updater_nickname,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@register_schema_to_swagger
class AdminOperationCourseOverviewDTO(BaseModel):
    """Overview metrics shown above the operator course list."""

    total_course_count: int = Field(
        default=0,
        description="Total visible course count",
    )
    draft_course_count: int = Field(
        default=0,
        description="Visible draft-only course count",
    )
    published_course_count: int = Field(
        default=0,
        description="Visible published course count",
    )
    created_last_7d_course_count: int = Field(
        default=0,
        description="Visible courses created in the last 7 days",
    )
    learning_active_30d_course_count: int = Field(
        default=0,
        description="Visible courses with learning records in the last 30 days",
    )
    paid_order_30d_course_count: int = Field(
        default=0,
        description="Visible courses with successful orders in the last 30 days",
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator course overview as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseListDTO(BaseModel):
    """Operator-facing paginated course list payload."""

    items: list[AdminOperationCourseSummaryDTO] = Field(
        default_factory=list,
        description="Paginated course rows",
    )
    page: int = Field(..., description="Page index")
    page_size: int = Field(..., description="Page size")
    total: int = Field(..., description="Total row count")
    page_count: int = Field(..., description="Page count")

    def __json__(self) -> dict[str, object]:
        """Return the operator course list as JSON-compatible data."""
        return {
            "items": [item.__json__() for item in self.items],
            "page": self.page,
            "page_size": self.page_size,
            "total": self.total,
            "page_count": self.page_count,
        }


@register_schema_to_swagger
class AdminOperationCourseDetailBasicInfoDTO(BaseModel):
    """Operator-facing course basic information."""

    shifu_bid: str = Field(..., description="Course business identifier")
    course_name: str = Field(..., description="Course name")
    course_status: str = Field(..., description="Course status")
    creator_user_bid: str = Field(..., description="Creator user business identifier")
    creator_mobile: str = Field(..., description="Creator mobile")
    creator_email: str = Field(..., description="Creator email")
    creator_nickname: str = Field(..., description="Creator nickname")
    created_at: datetime | None = Field(..., description="Created at")
    updated_at: datetime | None = Field(..., description="Updated at")

    def __json__(self) -> dict[str, object]:
        """Return operator course basic information as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseDetailMetricsDTO(BaseModel):
    """Operator-facing course metrics summary."""

    learner_count: int = Field(..., description="Distinct learner count")
    order_count: int = Field(..., description="Successful order count")
    order_amount: str = Field(
        ...,
        description="Collected amount for successful orders using paid price when paid_price > 0, otherwise payable price when payable_price > 0",
    )
    follow_up_count: int = Field(..., description="Follow-up question count")
    rating_score: str = Field(..., description="Average lesson rating score")
    credit_consumed_total: int | float = Field(
        default=0, description="Total consumed credits for this course"
    )
    credit_usage_count: int = Field(
        default=0,
        description="Distinct billed usage count for this course",
    )
    credit_user_count: int = Field(
        default=0, description="Distinct users with billed credit usage"
    )
    completed_credit_user_count: int = Field(
        default=0,
        description="Completed users with billed credit usage coverage",
    )
    completed_user_avg_credits: int | float | None = Field(
        default=None,
        description="Average consumed credits among completed users with credit usage",
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator course detail metrics as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationEstimatedCreditComponentDTO(BaseModel):
    """Estimated credit range for one billable component."""

    model_config = ConfigDict(protected_namespaces=())

    min: int | float = Field(..., description="Estimated minimum credits")
    max: int | float = Field(..., description="Estimated maximum credits")
    model: str = Field(default="", description="Raw model identifier")
    model_label: str = Field(default="", description="Display name from model options")
    multiplier: str | None = Field(default=None, description="Credit multiplier label")

    def __json__(self) -> dict[str, object]:
        """Return the operator estimated credit component as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationEstimatedCreditModeDTO(BaseModel):
    """Estimated full-course credit cost for one learning mode."""

    min: int | float = Field(..., description="Estimated minimum credits")
    max: int | float = Field(..., description="Estimated maximum credits")
    llm: AdminOperationEstimatedCreditComponentDTO = Field(
        ..., description="LLM credit estimate"
    )
    tts: AdminOperationEstimatedCreditComponentDTO | None = Field(
        default=None, description="TTS credit estimate"
    )
    enabled: bool | None = Field(
        default=None, description="Whether the course currently enables this mode"
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator estimated credit mode as JSON-compatible data."""
        payload = self.model_dump(exclude={"llm", "tts"})
        payload["llm"] = self.llm.__json__()
        payload["tts"] = self.tts.__json__() if self.tts is not None else None
        return payload


@register_schema_to_swagger
class AdminOperationEstimatedCreditAssumptionsDTO(BaseModel):
    """Inputs used to calculate estimated full-course credit cost."""

    visible_lesson_count: int = Field(
        default=0, description="Visible leaf lesson count"
    )
    prompt_char_count: int = Field(
        default=0, description="Prompt characters counted per lesson"
    )
    content_char_count: int = Field(
        default=0, description="MarkdownFlow content characters"
    )
    calculated_at: datetime | None = Field(
        default=None, description="Calculation timestamp"
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator estimated credit assumptions as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationEstimatedCreditCostDTO(BaseModel):
    """Estimated full-course credit cost by learning mode."""

    read: AdminOperationEstimatedCreditModeDTO = Field(
        ..., description="Read mode estimate"
    )
    listen: AdminOperationEstimatedCreditModeDTO = Field(
        ..., description="Listen mode estimate"
    )
    classroom: AdminOperationEstimatedCreditModeDTO = Field(
        ..., description="Classroom mode estimate"
    )
    assumptions: AdminOperationEstimatedCreditAssumptionsDTO = Field(
        ..., description="Estimation assumptions"
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator estimated credit cost as JSON-compatible data."""
        return {
            "read": self.read.__json__(),
            "listen": self.listen.__json__(),
            "classroom": self.classroom.__json__(),
            "assumptions": self.assumptions.__json__(),
        }


@register_schema_to_swagger
class AdminOperationCourseCompletionCreditEstimateDTO(BaseModel):
    """Calibrated standard-1x reading completion estimate for one learner."""

    status: str = Field(..., description="calibrated or uncalibrated")
    estimated_credits: int | float | None = Field(
        default=None, description="Whole-course median credit estimate"
    )
    recommended_credits: int | float | None = Field(
        default=None, description="Whole-course 80th percentile credit estimate"
    )
    version: str | None = Field(
        default=None, description="Validated calibration artifact version"
    )

    def __json__(self) -> dict[str, object]:
        """Return the completion estimate as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseDetailChapterDTO(BaseModel):
    """Operator-facing course chapter tree node."""

    outline_item_bid: str = Field(..., description="Outline item business identifier")
    title: str = Field(..., description="Outline item title")
    parent_bid: str = Field(..., description="Parent outline item bid")
    position: str = Field(..., description="Outline position")
    node_type: str = Field(..., description="chapter or lesson")
    learning_permission: str = Field(..., description="guest, free, or paid")
    is_visible: bool = Field(..., description="Visibility flag")
    content_status: str = Field(..., description="has or empty")
    follow_up_count: int = Field(..., description="Follow-up question count")
    rating_score: str = Field(
        ...,
        description="Lesson-level average rating score; empty for chapter nodes",
    )
    rating_count: int = Field(
        ...,
        description="Lesson-level rating record count; 0 for chapter nodes",
    )
    modifier_user_bid: str = Field(
        ..., description="Last modifier user business identifier"
    )
    modifier_mobile: str = Field(..., description="Last modifier mobile")
    modifier_email: str = Field(..., description="Last modifier email")
    modifier_nickname: str = Field(..., description="Last modifier nickname")
    updated_at: datetime | None = Field(..., description="Updated at")
    children: list[AdminOperationCourseDetailChapterDTO] = Field(
        default_factory=list,
        description="Nested children",
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator course detail chapter as JSON-compatible data."""
        payload = self.model_dump(exclude={"children"})
        payload["children"] = [child.__json__() for child in self.children]
        return payload


@register_schema_to_swagger
class AdminOperationCourseUserDTO(BaseModel):
    """Operator-facing course user row."""

    user_bid: str = Field(..., description="User business identifier")
    mobile: str = Field(..., description="User mobile")
    email: str = Field(..., description="User email")
    nickname: str = Field(..., description="User nickname")
    user_role: str = Field(..., description="Resolved user role")
    learned_lesson_count: int = Field(
        default=0,
        description="Distinct learned visible lesson count",
    )
    total_lesson_count: int = Field(
        default=0,
        description="Total visible lesson count",
    )
    learning_status: str = Field(..., description="not_started, learning, or completed")
    is_paid: bool = Field(..., description="Whether the user has paid")
    total_paid_amount: str = Field(default="0", description="Course-scoped paid amount")
    last_learning_at: datetime | None = Field(
        default=None, description="Latest learning timestamp"
    )
    joined_at: datetime | None = Field(
        default=None, description="Course join timestamp"
    )
    last_login_at: datetime | None = Field(
        default=None, description="Latest login timestamp"
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator course user as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCoursePromptDTO(BaseModel):
    """Operator-facing course prompt payload."""

    course_prompt: str = Field(..., description="Course-level system prompt")

    def __json__(self) -> dict[str, object]:
        """Return the operator course prompt as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseChapterDetailDTO(BaseModel):
    """Operator-facing chapter content detail payload."""

    outline_item_bid: str = Field(..., description="Outline item business identifier")
    title: str = Field(..., description="Outline item title")
    content: str = Field(..., description="MarkdownFlow content")
    llm_system_prompt: str = Field(..., description="Outline system prompt")
    llm_system_prompt_source: str = Field(
        ..., description="Resolved outline system prompt source"
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator course chapter detail as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseDetailDTO(BaseModel):
    """Operator-facing course detail payload."""

    basic_info: AdminOperationCourseDetailBasicInfoDTO = Field(
        ..., description="Basic course information"
    )
    metrics: AdminOperationCourseDetailMetricsDTO = Field(
        ..., description="Course metrics"
    )
    estimated_credit_cost: AdminOperationEstimatedCreditCostDTO = Field(
        ..., description="Estimated full-course credit cost"
    )
    completion_credit_estimate: AdminOperationCourseCompletionCreditEstimateDTO = Field(
        ..., description="Calibrated 1x reading completion credit estimate"
    )
    chapters: list[AdminOperationCourseDetailChapterDTO] = Field(
        default_factory=list,
        description="Course chapter tree",
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator course detail as JSON-compatible data."""
        return {
            "basic_info": self.basic_info.__json__(),
            "metrics": self.metrics.__json__(),
            "estimated_credit_cost": self.estimated_credit_cost.__json__(),
            "completion_credit_estimate": self.completion_credit_estimate.__json__(),
            "chapters": [chapter.__json__() for chapter in self.chapters],
        }


@register_schema_to_swagger
class AdminOperationCourseFollowUpSummaryDTO(BaseModel):
    """Operator-facing course follow-up summary."""

    follow_up_count: int = Field(
        default=0, description="Filtered follow-up record count"
    )
    user_count: int = Field(default=0, description="Distinct follow-up user count")
    lesson_count: int = Field(
        default=0, description="Distinct lesson count with follow-ups"
    )
    latest_follow_up_at: datetime | None = Field(
        default=None, description="Latest follow-up timestamp"
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator course follow-up summary as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseFollowUpItemDTO(BaseModel):
    """Operator-facing course follow-up row."""

    generated_block_bid: str = Field(
        ..., description="Follow-up generated block business identifier"
    )
    progress_record_bid: str = Field(
        ..., description="Progress record business identifier"
    )
    user_bid: str = Field(..., description="User business identifier")
    mobile: str = Field(..., description="User mobile")
    email: str = Field(..., description="User email")
    nickname: str = Field(..., description="User nickname")
    chapter_outline_item_bid: str = Field(
        default="",
        description="Chapter outline item business identifier",
    )
    chapter_title: str = Field(default="", description="Chapter title")
    lesson_outline_item_bid: str = Field(
        default="",
        description="Lesson outline item business identifier",
    )
    lesson_title: str = Field(default="", description="Lesson title")
    follow_up_content: str = Field(default="", description="Student follow-up content")
    has_source_output: bool = Field(
        default=False,
        description="Whether the original output source could be resolved",
    )
    turn_index: int = Field(default=0, description="1-based follow-up turn index")
    created_at: datetime | None = Field(default=None, description="Created at")

    def __json__(self) -> dict[str, object]:
        """Return the operator course follow-up item as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseFollowUpListDTO(BaseModel):
    """Operator-facing course follow-up list payload."""

    summary: AdminOperationCourseFollowUpSummaryDTO = Field(
        ..., description="Follow-up summary"
    )
    items: list[AdminOperationCourseFollowUpItemDTO] = Field(
        default_factory=list,
        description="Paginated follow-up rows",
    )
    page: int = Field(..., description="Page index")
    page_size: int = Field(..., description="Page size")
    total: int = Field(..., description="Total row count")
    page_count: int = Field(..., description="Page count")

    def __json__(self) -> dict[str, object]:
        """Return the operator course follow-up list as JSON-compatible data."""
        return {
            "summary": self.summary.__json__(),
            "items": [item.__json__() for item in self.items],
            "page": self.page,
            "page_size": self.page_size,
            "total": self.total,
            "page_count": self.page_count,
        }


@register_schema_to_swagger
class AdminOperationCourseRatingSummaryDTO(BaseModel):
    """Operator-facing course rating summary."""

    average_score: str = Field(default="", description="Filtered average rating score")
    rating_count: int = Field(default=0, description="Filtered rating record count")
    user_count: int = Field(default=0, description="Distinct rating user count")
    latest_rated_at: datetime | None = Field(
        default=None, description="Latest rating timestamp"
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator course rating summary as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseRatingItemDTO(BaseModel):
    """Operator-facing course rating row."""

    lesson_feedback_bid: str = Field(
        ..., description="Lesson feedback business identifier"
    )
    progress_record_bid: str = Field(
        ..., description="Progress record business identifier"
    )
    user_bid: str = Field(..., description="User business identifier")
    mobile: str = Field(..., description="User mobile")
    email: str = Field(..., description="User email")
    nickname: str = Field(..., description="User nickname")
    chapter_outline_item_bid: str = Field(
        default="",
        description="Chapter outline item business identifier",
    )
    chapter_title: str = Field(default="", description="Chapter title")
    lesson_outline_item_bid: str = Field(
        default="",
        description="Lesson outline item business identifier",
    )
    lesson_title: str = Field(default="", description="Lesson title")
    score: int = Field(default=0, description="Lesson rating score")
    comment: str = Field(default="", description="Lesson rating comment")
    mode: str = Field(default="", description="Rating mode")
    rated_at: datetime | None = Field(default=None, description="Rated at")

    def __json__(self) -> dict[str, object]:
        """Return the operator course rating item as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseRatingListDTO(BaseModel):
    """Operator-facing course rating list payload."""

    summary: AdminOperationCourseRatingSummaryDTO = Field(
        ..., description="Rating summary"
    )
    items: list[AdminOperationCourseRatingItemDTO] = Field(
        default_factory=list,
        description="Paginated rating rows",
    )
    page: int = Field(..., description="Page index")
    page_size: int = Field(..., description="Page size")
    total: int = Field(..., description="Total row count")
    page_count: int = Field(..., description="Page count")

    def __json__(self) -> dict[str, object]:
        """Return the operator course rating list as JSON-compatible data."""
        return {
            "summary": self.summary.__json__(),
            "items": [item.__json__() for item in self.items],
            "page": self.page,
            "page_size": self.page_size,
            "total": self.total,
            "page_count": self.page_count,
        }


@register_schema_to_swagger
class AdminOperationCourseCreditUsageItemDTO(BaseModel):
    """Operator-facing course credit usage row."""

    model_config = ConfigDict(protected_namespaces=())

    group_key: str = Field(
        default="",
        description="Grouped row business key or raw usage key",
    )
    usage_bid: str = Field(..., description="Usage business identifier")
    progress_record_bid: str = Field(
        default="",
        description="Progress record business identifier",
    )
    generated_block_bid: str = Field(
        default="",
        description="Generated block business identifier",
    )
    user_bid: str = Field(..., description="User business identifier")
    mobile: str = Field(..., description="User mobile")
    email: str = Field(..., description="User email")
    nickname: str = Field(..., description="User nickname")
    chapter_outline_item_bid: str = Field(
        default="",
        description="Chapter outline item business identifier",
    )
    chapter_title: str = Field(default="", description="Chapter title")
    lesson_outline_item_bid: str = Field(
        default="",
        description="Lesson outline item business identifier",
    )
    lesson_title: str = Field(default="", description="Lesson title")
    usage_scene: str = Field(
        default="",
        description="Credit usage scene: learning/preview/debug",
    )
    usage_mode: str = Field(
        default="",
        description="Credit usage mode: learn/listen/ask",
    )
    provider: str = Field(default="", description="Provider name")
    model: str = Field(default="", description="Provider model")
    model_label: str = Field(default="", description="Model display name")
    usage_count: int = Field(
        default=1,
        description="Grouped usage row count",
    )
    model_variant_count: int = Field(
        default=0,
        description="Distinct provider/model count inside the row",
    )
    consumed_credits: int | float = Field(
        default=0,
        description="Consumed credits",
    )
    created_at: datetime | None = Field(default=None, description="Created at")

    def __json__(self) -> dict[str, object]:
        """Return the operator course credit usage item as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseCreditUsageDetailItemDTO(BaseModel):
    """Operator-facing single credit usage detail row."""

    model_config = ConfigDict(protected_namespaces=())

    usage_bid: str = Field(..., description="Usage business identifier")
    consumed_credits: int | float = Field(
        default=0,
        description="Consumed credits",
    )
    input_tokens: int = Field(default=0, description="Input token count")
    output_tokens: int = Field(default=0, description="Output token count")
    provider: str = Field(default="", description="Provider name")
    model: str = Field(default="", description="Provider model")
    model_label: str = Field(default="", description="Model display name")
    word_count: int = Field(default=0, description="TTS word count")
    duration_ms: int = Field(
        default=0, description="TTS audio duration in milliseconds"
    )
    segment_count: int = Field(default=0, description="TTS synthesized segment count")
    output_summary: str = Field(default="", description="Generated output summary")
    created_at: datetime | None = Field(default=None, description="Created at")

    def __json__(self) -> dict[str, object]:
        """Return credit-usage detail as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseCreditUsageListDTO(BaseModel):
    """Operator-facing course credit usage list payload."""

    view: str = Field(
        default="grouped",
        description="Response view mode: grouped/raw",
    )
    items: list[AdminOperationCourseCreditUsageItemDTO] = Field(
        default_factory=list,
        description="Paginated credit usage rows",
    )
    page: int = Field(..., description="Page index")
    page_size: int = Field(..., description="Page size")
    total: int = Field(..., description="Total row count")
    page_count: int = Field(..., description="Page count")

    def __json__(self) -> dict[str, object]:
        """Return the operator course credit usage list as JSON-compatible data."""
        return {
            "view": self.view,
            "items": [item.__json__() for item in self.items],
            "page": self.page,
            "page_size": self.page_size,
            "total": self.total,
            "page_count": self.page_count,
        }


@register_schema_to_swagger
class AdminOperationCourseCreditUsageDetailListDTO(BaseModel):
    """Operator-facing paginated single credit usage details."""

    items: list[AdminOperationCourseCreditUsageDetailItemDTO] = Field(
        default_factory=list,
        description="Paginated credit usage detail rows",
    )
    page: int = Field(..., description="Page index")
    page_size: int = Field(..., description="Page size")
    total: int = Field(..., description="Total row count")
    page_count: int = Field(..., description="Page count")

    def __json__(self) -> dict[str, object]:
        """Return credit-usage details as JSON-compatible data."""
        return {
            "items": [item.__json__() for item in self.items],
            "page": self.page,
            "page_size": self.page_size,
            "total": self.total,
            "page_count": self.page_count,
        }


@register_schema_to_swagger
class AdminOperationCourseFollowUpDetailBasicInfoDTO(BaseModel):
    """Operator-facing course follow-up detail basic information."""

    generated_block_bid: str = Field(
        ..., description="Follow-up generated block business identifier"
    )
    progress_record_bid: str = Field(
        ..., description="Progress record business identifier"
    )
    user_bid: str = Field(..., description="User business identifier")
    mobile: str = Field(..., description="User mobile")
    email: str = Field(..., description="User email")
    nickname: str = Field(..., description="User nickname")
    course_name: str = Field(..., description="Course name")
    shifu_bid: str = Field(..., description="Course business identifier")
    chapter_title: str = Field(default="", description="Chapter title")
    lesson_title: str = Field(default="", description="Lesson title")
    created_at: datetime | None = Field(default=None, description="Created at")
    turn_index: int = Field(default=0, description="1-based follow-up turn index")

    def __json__(self) -> dict[str, object]:
        """Return basic follow-up information as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseFollowUpCurrentRecordDTO(BaseModel):
    """Operator-facing current follow-up record payload."""

    follow_up_content: str = Field(default="", description="Student follow-up content")
    answer_content: str = Field(default="", description="System answer content")
    source_output_content: str = Field(
        default="",
        description="Original output content being followed up",
    )
    source_output_type: str = Field(
        default="",
        description="Original output source type",
    )
    source_position: int = Field(
        default=0,
        description="Original output block position",
    )
    source_element_bid: str = Field(
        default="",
        description="Original output anchor element business identifier",
    )
    source_element_type: str = Field(
        default="",
        description="Original output anchor element type",
    )

    def __json__(self) -> dict[str, object]:
        """Return the current follow-up record as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseFollowUpTimelineItemDTO(BaseModel):
    """Operator-facing follow-up timeline item."""

    role: str = Field(..., description="student or teacher")
    content: str = Field(default="", description="Timeline content")
    created_at: datetime | None = Field(default=None, description="Created at")
    is_current: bool = Field(
        default=False,
        description="Whether the item belongs to the selected turn",
    )

    def __json__(self) -> dict[str, object]:
        """Return a follow-up timeline item as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseFollowUpDetailDTO(BaseModel):
    """Operator-facing course follow-up detail payload."""

    basic_info: AdminOperationCourseFollowUpDetailBasicInfoDTO = Field(
        ..., description="Follow-up basic info"
    )
    current_record: AdminOperationCourseFollowUpCurrentRecordDTO = Field(
        ..., description="Current follow-up record"
    )
    timeline: list[AdminOperationCourseFollowUpTimelineItemDTO] = Field(
        default_factory=list,
        description="Follow-up timeline",
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator course follow-up detail as JSON-compatible data."""
        return {
            "basic_info": self.basic_info.__json__(),
            "current_record": self.current_record.__json__(),
            "timeline": [item.__json__() for item in self.timeline],
        }

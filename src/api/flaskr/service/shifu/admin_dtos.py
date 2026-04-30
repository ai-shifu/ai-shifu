from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from flaskr.common.swagger import register_schema_to_swagger


@register_schema_to_swagger
class AdminOperationCourseSummaryDTO(BaseModel):
    """Course summary shown in the operator course list."""

    shifu_bid: str = Field(
        ..., description="Course business identifier", required=False
    )
    course_name: str = Field(..., description="Course name", required=False)
    course_status: str = Field(..., description="Course status", required=False)
    price: str = Field(..., description="Course price", required=False)
    course_model: str = Field(..., description="Course model", required=False)
    has_course_prompt: bool = Field(
        ...,
        description="Whether the course has a course-level system prompt",
        required=False,
    )
    creator_user_bid: str = Field(
        ..., description="Creator user business identifier", required=False
    )
    creator_mobile: str = Field(..., description="Creator mobile", required=False)
    creator_email: str = Field(..., description="Creator email", required=False)
    creator_nickname: str = Field(..., description="Creator nickname", required=False)
    updater_user_bid: str = Field(
        ..., description="Updater user business identifier", required=False
    )
    updater_mobile: str = Field(..., description="Updater mobile", required=False)
    updater_email: str = Field(..., description="Updater email", required=False)
    updater_nickname: str = Field(..., description="Updater nickname", required=False)
    created_at: str = Field(..., description="Created at", required=False)
    updated_at: str = Field(..., description="Updated at", required=False)

    def __init__(
        self,
        shifu_bid: str,
        course_name: str,
        course_status: str,
        price: str,
        course_model: str,
        has_course_prompt: bool,
        creator_user_bid: str,
        creator_mobile: str,
        creator_email: str,
        creator_nickname: str,
        updater_user_bid: str,
        updater_mobile: str,
        updater_email: str,
        updater_nickname: str,
        created_at: str,
        updated_at: str,
    ):
        super().__init__(
            shifu_bid=shifu_bid,
            course_name=course_name,
            course_status=course_status,
            price=price,
            course_model=course_model,
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

    def __json__(self):
        return {
            "shifu_bid": self.shifu_bid,
            "course_name": self.course_name,
            "course_status": self.course_status,
            "price": self.price,
            "course_model": self.course_model,
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
class AdminOperationUserCourseSummaryDTO(BaseModel):
    """Course summary shown in operator user-related course lists."""

    shifu_bid: str = Field(
        ..., description="Course business identifier", required=False
    )
    course_name: str = Field(..., description="Course name", required=False)
    course_status: str = Field(..., description="Course status", required=False)
    completed_lesson_count: int = Field(
        default=0,
        description="Completed visible lesson count for the learner",
        required=False,
    )
    total_lesson_count: int = Field(
        default=0,
        description="Total visible lesson count for the learner course",
        required=False,
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserSummaryDTO(BaseModel):
    """User summary shown in the operator user list."""

    user_bid: str = Field(..., description="User business identifier", required=False)
    mobile: str = Field(..., description="User mobile", required=False)
    email: str = Field(..., description="User email", required=False)
    nickname: str = Field(..., description="User nickname", required=False)
    user_status: str = Field(..., description="User status", required=False)
    user_role: str = Field(..., description="Resolved user role", required=False)
    user_roles: list[str] = Field(
        default_factory=list,
        description="Resolved user roles",
        required=False,
    )
    login_methods: list[str] = Field(
        default_factory=list,
        description="Resolved login methods",
        required=False,
    )
    registration_source: str = Field(
        default="unknown",
        description="Resolved registration source",
        required=False,
    )
    language: str = Field(..., description="User language", required=False)
    learning_courses: list[AdminOperationUserCourseSummaryDTO] = Field(
        default_factory=list,
        description="Courses the user learned via successful orders",
        required=False,
    )
    created_courses: list[AdminOperationUserCourseSummaryDTO] = Field(
        default_factory=list,
        description="Courses created by the user",
        required=False,
    )
    total_paid_amount: str = Field(
        default="0",
        description="Total successful paid order amount",
        required=False,
    )
    available_credits: str = Field(
        default="",
        description="Current active total creator credits",
        required=False,
    )
    subscription_credits: str = Field(
        default="",
        description="Current active subscription creator credits",
        required=False,
    )
    topup_credits: str = Field(
        default="",
        description="Current active top-up creator credits",
        required=False,
    )
    credits_expire_at: str = Field(
        default="",
        description="Earliest active creator credit expiry",
        required=False,
    )
    has_active_subscription: bool = Field(
        default=False,
        description="Whether the user currently has an active subscription",
        required=False,
    )
    last_login_at: str = Field(
        default="",
        description="Latest login timestamp",
        required=False,
    )
    last_learning_at: str = Field(
        default="",
        description="Latest learning timestamp",
        required=False,
    )
    created_at: str = Field(..., description="Created at", required=False)
    updated_at: str = Field(..., description="Updated at", required=False)

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserCreditSummaryDTO(BaseModel):
    """Credits summary shown in the operator user detail."""

    available_credits: str = Field(
        default="",
        description="Current active total creator credits",
        required=False,
    )
    subscription_credits: str = Field(
        default="",
        description="Current active subscription creator credits",
        required=False,
    )
    topup_credits: str = Field(
        default="",
        description="Current active top-up creator credits",
        required=False,
    )
    credits_expire_at: str = Field(
        default="",
        description="Earliest active creator credit expiry",
        required=False,
    )
    has_active_subscription: bool = Field(
        default=False,
        description="Whether the user currently has an active subscription",
        required=False,
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserCreditGrantRequestDTO(BaseModel):
    """Operator credits grant request payload."""

    request_id: str = Field(
        ...,
        description="Client request identifier for idempotent credit grants",
        required=False,
    )
    amount: str = Field(..., description="Granted credits amount", required=False)
    grant_source: str = Field(
        ..., description="Grant source: reward or compensation", required=False
    )
    validity_preset: str = Field(
        ..., description="Grant validity preset", required=False
    )
    note: str = Field(default="", description="Optional operator note", required=False)

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserCreditGrantResultDTO(BaseModel):
    """Operator credits grant response payload."""

    user_bid: str = Field(..., description="Target user business identifier")
    amount: str = Field(..., description="Granted credits amount", required=False)
    grant_source: str = Field(
        ..., description="Grant source: reward or compensation", required=False
    )
    validity_preset: str = Field(
        ..., description="Applied validity preset", required=False
    )
    expires_at: str = Field(
        default="", description="Resolved expiry timestamp", required=False
    )
    wallet_bucket_bid: str = Field(
        ..., description="Created wallet bucket identifier", required=False
    )
    ledger_bid: str = Field(
        ..., description="Created ledger identifier", required=False
    )
    summary: AdminOperationUserCreditSummaryDTO = Field(
        ..., description="Refreshed credits summary", required=False
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserCreditLedgerItemDTO(BaseModel):
    """Operator-facing user credit ledger row."""

    ledger_bid: str = Field(
        ..., description="Ledger business identifier", required=False
    )
    created_at: str = Field(..., description="Created at", required=False)
    entry_type: str = Field(..., description="Ledger entry type", required=False)
    source_type: str = Field(..., description="Ledger source type", required=False)
    display_entry_type: str = Field(
        default="",
        description="Operator-facing ledger entry type",
        required=False,
    )
    display_source_type: str = Field(
        default="",
        description="Operator-facing ledger source type",
        required=False,
    )
    amount: str = Field(..., description="Ledger amount", required=False)
    balance_after: str = Field(..., description="Balance after entry", required=False)
    expires_at: str = Field(default="", description="Entry expires at", required=False)
    consumable_from: str = Field(
        default="",
        description="Entry consumable from",
        required=False,
    )
    note: str = Field(default="", description="Ledger note", required=False)
    note_code: str = Field(
        default="",
        description="Operator-facing note code",
        required=False,
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserCreditLedgerPageDTO(BaseModel):
    """Paginated operator-facing user credit ledger response."""

    summary: AdminOperationUserCreditSummaryDTO = Field(
        ..., description="Credits summary", required=False
    )
    items: list[AdminOperationUserCreditLedgerItemDTO] = Field(
        default_factory=list,
        description="Credit ledger items",
        required=False,
    )
    page: int = Field(..., description="Page index", required=False)
    page_size: int = Field(..., description="Page size", required=False)
    total: int = Field(..., description="Total count", required=False)
    page_count: int = Field(..., description="Page count", required=False)

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseDetailBasicInfoDTO(BaseModel):
    """Operator-facing course basic information."""

    shifu_bid: str = Field(
        ..., description="Course business identifier", required=False
    )
    course_name: str = Field(..., description="Course name", required=False)
    course_status: str = Field(..., description="Course status", required=False)
    creator_user_bid: str = Field(
        ..., description="Creator user business identifier", required=False
    )
    creator_mobile: str = Field(..., description="Creator mobile", required=False)
    creator_email: str = Field(..., description="Creator email", required=False)
    creator_nickname: str = Field(..., description="Creator nickname", required=False)
    created_at: str = Field(..., description="Created at", required=False)
    updated_at: str = Field(..., description="Updated at", required=False)

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseDetailMetricsDTO(BaseModel):
    """Operator-facing course metrics summary."""

    visit_count_30d: int = Field(
        ...,
        description="Distinct logged-in course visitors in the last 30 days",
        required=False,
    )
    learner_count: int = Field(
        ..., description="Distinct learner count", required=False
    )
    order_count: int = Field(..., description="Successful order count", required=False)
    order_amount: str = Field(
        ...,
        description="Collected amount for successful orders using paid price when paid_price > 0, otherwise payable price when payable_price > 0",
        required=False,
    )
    follow_up_count: int = Field(
        ..., description="Follow-up question count", required=False
    )
    rating_score: str = Field(
        ..., description="Average lesson rating score", required=False
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseDetailChapterDTO(BaseModel):
    """Operator-facing course chapter tree node."""

    outline_item_bid: str = Field(
        ..., description="Outline item business identifier", required=False
    )
    title: str = Field(..., description="Outline item title", required=False)
    parent_bid: str = Field(..., description="Parent outline item bid", required=False)
    position: str = Field(..., description="Outline position", required=False)
    node_type: str = Field(..., description="chapter or lesson", required=False)
    learning_permission: str = Field(
        ..., description="guest, free, or paid", required=False
    )
    is_visible: bool = Field(..., description="Visibility flag", required=False)
    content_status: str = Field(..., description="has or empty", required=False)
    follow_up_count: int = Field(
        ..., description="Follow-up question count", required=False
    )
    rating_score: str = Field(
        ...,
        description="Lesson-level average rating score; empty for chapter nodes",
        required=False,
    )
    rating_count: int = Field(
        ...,
        description="Lesson-level rating record count; 0 for chapter nodes",
        required=False,
    )
    modifier_user_bid: str = Field(
        ..., description="Last modifier user business identifier", required=False
    )
    modifier_mobile: str = Field(
        ..., description="Last modifier mobile", required=False
    )
    modifier_email: str = Field(..., description="Last modifier email", required=False)
    modifier_nickname: str = Field(
        ..., description="Last modifier nickname", required=False
    )
    updated_at: str = Field(..., description="Updated at", required=False)
    children: list["AdminOperationCourseDetailChapterDTO"] = Field(
        default_factory=list,
        description="Nested children",
        required=False,
    )

    def __json__(self) -> dict[str, Any]:
        payload = self.model_dump(exclude={"children"})
        payload["children"] = [child.__json__() for child in self.children]
        return payload


@register_schema_to_swagger
class AdminOperationCourseUserDTO(BaseModel):
    """Operator-facing course user row."""

    user_bid: str = Field(..., description="User business identifier", required=False)
    mobile: str = Field(..., description="User mobile", required=False)
    email: str = Field(..., description="User email", required=False)
    nickname: str = Field(..., description="User nickname", required=False)
    user_role: str = Field(..., description="Resolved user role", required=False)
    learned_lesson_count: int = Field(
        default=0,
        description="Distinct learned visible lesson count",
        required=False,
    )
    total_lesson_count: int = Field(
        default=0,
        description="Total visible lesson count",
        required=False,
    )
    learning_status: str = Field(
        ..., description="not_started, learning, or completed", required=False
    )
    is_paid: bool = Field(..., description="Whether the user has paid", required=False)
    total_paid_amount: str = Field(
        default="0", description="Course-scoped paid amount", required=False
    )
    last_learning_at: str = Field(
        default="", description="Latest learning timestamp", required=False
    )
    joined_at: str = Field(
        default="", description="Course join timestamp", required=False
    )
    last_login_at: str = Field(
        default="", description="Latest login timestamp", required=False
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCoursePromptDTO(BaseModel):
    """Operator-facing course prompt payload."""

    course_prompt: str = Field(
        ..., description="Course-level system prompt", required=False
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseChapterDetailDTO(BaseModel):
    """Operator-facing chapter content detail payload."""

    outline_item_bid: str = Field(
        ..., description="Outline item business identifier", required=False
    )
    title: str = Field(..., description="Outline item title", required=False)
    content: str = Field(..., description="MarkdownFlow content", required=False)
    llm_system_prompt: str = Field(
        ..., description="Outline system prompt", required=False
    )
    llm_system_prompt_source: str = Field(
        ..., description="Resolved outline system prompt source", required=False
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseDetailDTO(BaseModel):
    """Operator-facing course detail payload."""

    basic_info: AdminOperationCourseDetailBasicInfoDTO = Field(
        ..., description="Basic course information", required=False
    )
    metrics: AdminOperationCourseDetailMetricsDTO = Field(
        ..., description="Course metrics", required=False
    )
    chapters: list[AdminOperationCourseDetailChapterDTO] = Field(
        default_factory=list,
        description="Course chapter tree",
        required=False,
    )

    def __json__(self) -> dict[str, Any]:
        return {
            "basic_info": self.basic_info.__json__(),
            "metrics": self.metrics.__json__(),
            "chapters": [chapter.__json__() for chapter in self.chapters],
        }


@register_schema_to_swagger
class AdminOperationCourseFollowUpSummaryDTO(BaseModel):
    """Operator-facing course follow-up summary."""

    follow_up_count: int = Field(
        default=0, description="Filtered follow-up record count", required=False
    )
    user_count: int = Field(
        default=0, description="Distinct follow-up user count", required=False
    )
    lesson_count: int = Field(
        default=0, description="Distinct lesson count with follow-ups", required=False
    )
    latest_follow_up_at: str = Field(
        default="", description="Latest follow-up timestamp", required=False
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseFollowUpItemDTO(BaseModel):
    """Operator-facing course follow-up row."""

    generated_block_bid: str = Field(
        ..., description="Follow-up generated block business identifier", required=False
    )
    progress_record_bid: str = Field(
        ..., description="Progress record business identifier", required=False
    )
    user_bid: str = Field(..., description="User business identifier", required=False)
    mobile: str = Field(..., description="User mobile", required=False)
    email: str = Field(..., description="User email", required=False)
    nickname: str = Field(..., description="User nickname", required=False)
    chapter_outline_item_bid: str = Field(
        default="",
        description="Chapter outline item business identifier",
        required=False,
    )
    chapter_title: str = Field(default="", description="Chapter title", required=False)
    lesson_outline_item_bid: str = Field(
        default="",
        description="Lesson outline item business identifier",
        required=False,
    )
    lesson_title: str = Field(default="", description="Lesson title", required=False)
    follow_up_content: str = Field(
        default="", description="Student follow-up content", required=False
    )
    turn_index: int = Field(
        default=0, description="1-based follow-up turn index", required=False
    )
    created_at: str = Field(default="", description="Created at", required=False)

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseFollowUpListDTO(BaseModel):
    """Operator-facing course follow-up list payload."""

    summary: AdminOperationCourseFollowUpSummaryDTO = Field(
        ..., description="Follow-up summary", required=False
    )
    items: list[AdminOperationCourseFollowUpItemDTO] = Field(
        default_factory=list,
        description="Paginated follow-up rows",
        required=False,
    )
    page: int = Field(..., description="Page index", required=False)
    page_size: int = Field(..., description="Page size", required=False)
    total: int = Field(..., description="Total row count", required=False)
    page_count: int = Field(..., description="Page count", required=False)

    def __json__(self) -> dict[str, Any]:
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

    average_score: str = Field(
        default="", description="Filtered average rating score", required=False
    )
    rating_count: int = Field(
        default=0, description="Filtered rating record count", required=False
    )
    user_count: int = Field(
        default=0, description="Distinct rating user count", required=False
    )
    latest_rated_at: str = Field(
        default="", description="Latest rating timestamp", required=False
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseRatingItemDTO(BaseModel):
    """Operator-facing course rating row."""

    lesson_feedback_bid: str = Field(
        ..., description="Lesson feedback business identifier", required=False
    )
    progress_record_bid: str = Field(
        ..., description="Progress record business identifier", required=False
    )
    user_bid: str = Field(..., description="User business identifier", required=False)
    mobile: str = Field(..., description="User mobile", required=False)
    email: str = Field(..., description="User email", required=False)
    nickname: str = Field(..., description="User nickname", required=False)
    chapter_outline_item_bid: str = Field(
        default="",
        description="Chapter outline item business identifier",
        required=False,
    )
    chapter_title: str = Field(default="", description="Chapter title", required=False)
    lesson_outline_item_bid: str = Field(
        default="",
        description="Lesson outline item business identifier",
        required=False,
    )
    lesson_title: str = Field(default="", description="Lesson title", required=False)
    score: int = Field(default=0, description="Lesson rating score", required=False)
    comment: str = Field(
        default="", description="Lesson rating comment", required=False
    )
    mode: str = Field(default="", description="Rating mode", required=False)
    rated_at: str = Field(default="", description="Rated at", required=False)

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseRatingListDTO(BaseModel):
    """Operator-facing course rating list payload."""

    summary: AdminOperationCourseRatingSummaryDTO = Field(
        ..., description="Rating summary", required=False
    )
    items: list[AdminOperationCourseRatingItemDTO] = Field(
        default_factory=list,
        description="Paginated rating rows",
        required=False,
    )
    page: int = Field(..., description="Page index", required=False)
    page_size: int = Field(..., description="Page size", required=False)
    total: int = Field(..., description="Total row count", required=False)
    page_count: int = Field(..., description="Page count", required=False)

    def __json__(self) -> dict[str, Any]:
        return {
            "summary": self.summary.__json__(),
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
        ..., description="Follow-up generated block business identifier", required=False
    )
    progress_record_bid: str = Field(
        ..., description="Progress record business identifier", required=False
    )
    user_bid: str = Field(..., description="User business identifier", required=False)
    mobile: str = Field(..., description="User mobile", required=False)
    email: str = Field(..., description="User email", required=False)
    nickname: str = Field(..., description="User nickname", required=False)
    course_name: str = Field(..., description="Course name", required=False)
    shifu_bid: str = Field(
        ..., description="Course business identifier", required=False
    )
    chapter_title: str = Field(default="", description="Chapter title", required=False)
    lesson_title: str = Field(default="", description="Lesson title", required=False)
    created_at: str = Field(default="", description="Created at", required=False)
    turn_index: int = Field(
        default=0, description="1-based follow-up turn index", required=False
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseFollowUpCurrentRecordDTO(BaseModel):
    """Operator-facing current follow-up record payload."""

    follow_up_content: str = Field(
        default="", description="Student follow-up content", required=False
    )
    answer_content: str = Field(
        default="", description="System answer content", required=False
    )
    source_output_content: str = Field(
        default="",
        description="Original output content being followed up",
        required=False,
    )
    source_output_type: str = Field(
        default="",
        description="Original output source type",
        required=False,
    )
    source_position: int = Field(
        default=0,
        description="Original output block position",
        required=False,
    )
    source_element_bid: str = Field(
        default="",
        description="Original output anchor element business identifier",
        required=False,
    )
    source_element_type: str = Field(
        default="",
        description="Original output anchor element type",
        required=False,
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseFollowUpTimelineItemDTO(BaseModel):
    """Operator-facing follow-up timeline item."""

    role: str = Field(..., description="student or teacher", required=False)
    content: str = Field(default="", description="Timeline content", required=False)
    created_at: str = Field(default="", description="Created at", required=False)
    is_current: bool = Field(
        default=False,
        description="Whether the item belongs to the selected turn",
        required=False,
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationCourseFollowUpDetailDTO(BaseModel):
    """Operator-facing course follow-up detail payload."""

    basic_info: AdminOperationCourseFollowUpDetailBasicInfoDTO = Field(
        ..., description="Follow-up basic info", required=False
    )
    current_record: AdminOperationCourseFollowUpCurrentRecordDTO = Field(
        ..., description="Current follow-up record", required=False
    )
    timeline: list[AdminOperationCourseFollowUpTimelineItemDTO] = Field(
        default_factory=list,
        description="Follow-up timeline",
        required=False,
    )

    def __json__(self) -> dict[str, Any]:
        return {
            "basic_info": self.basic_info.__json__(),
            "current_record": self.current_record.__json__(),
            "timeline": [item.__json__() for item in self.timeline],
        }

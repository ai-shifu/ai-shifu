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

    learner_count: int = Field(
        ..., description="Distinct learner count", required=False
    )
    order_count: int = Field(..., description="Paid order count", required=False)
    order_amount: str = Field(..., description="Paid order amount", required=False)
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

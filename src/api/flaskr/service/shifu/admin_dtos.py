from __future__ import annotations

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

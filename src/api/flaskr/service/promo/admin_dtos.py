from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from flaskr.common.swagger import register_schema_to_swagger


class _DTOBase(BaseModel):
    def __json__(self):
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()


@register_schema_to_swagger
class AdminPromotionSummaryDTO(_DTOBase):
    total: int = Field(..., description="Total item count", required=False)
    active: int = Field(..., description="Active item count", required=False)
    usage_count: int = Field(..., description="Usage count", required=False)
    latest_usage_at: str = Field(..., description="Latest usage time", required=False)
    covered_courses: int = Field(
        ..., description="Covered course count", required=False
    )
    discount_amount: str = Field(..., description="Discount amount", required=False)


@register_schema_to_swagger
class AdminPromotionCouponItemDTO(_DTOBase):
    coupon_bid: str = Field(..., description="Coupon batch identifier", required=False)
    name: str = Field(..., description="Coupon batch name", required=False)
    code: str = Field(..., description="Generic coupon code", required=False)
    usage_type: int = Field(..., description="Coupon usage type", required=False)
    usage_type_key: str = Field(
        ..., description="Coupon usage type i18n key", required=False
    )
    discount_type: int = Field(..., description="Discount type", required=False)
    discount_type_key: str = Field(
        ..., description="Discount type i18n key", required=False
    )
    value: str = Field(..., description="Discount value", required=False)
    scope_type: str = Field(..., description="Coupon scope type", required=False)
    shifu_bid: str = Field(..., description="Course identifier", required=False)
    course_name: str = Field(..., description="Course name", required=False)
    start_at: str = Field(..., description="Coupon start time", required=False)
    end_at: str = Field(..., description="Coupon end time", required=False)
    total_count: int = Field(..., description="Total count", required=False)
    used_count: int = Field(..., description="Used count", required=False)
    computed_status: str = Field(..., description="Computed status", required=False)
    computed_status_key: str = Field(
        ..., description="Computed status i18n key", required=False
    )
    created_at: str = Field(..., description="Created time", required=False)
    updated_at: str = Field(..., description="Updated time", required=False)


@register_schema_to_swagger
class AdminPromotionCampaignItemDTO(_DTOBase):
    promo_bid: str = Field(..., description="Promotion identifier", required=False)
    name: str = Field(..., description="Promotion name", required=False)
    shifu_bid: str = Field(..., description="Course identifier", required=False)
    course_name: str = Field(..., description="Course name", required=False)
    apply_type: int = Field(..., description="Grant type", required=False)
    discount_type: int = Field(..., description="Discount type", required=False)
    discount_type_key: str = Field(
        ..., description="Discount type i18n key", required=False
    )
    value: str = Field(..., description="Discount value", required=False)
    channel: str = Field(..., description="Channel", required=False)
    start_at: str = Field(..., description="Start time", required=False)
    end_at: str = Field(..., description="End time", required=False)
    computed_status: str = Field(..., description="Computed status", required=False)
    computed_status_key: str = Field(
        ..., description="Computed status i18n key", required=False
    )
    applied_order_count: int = Field(
        ..., description="Applied order count", required=False
    )
    has_redemptions: bool = Field(
        ..., description="Whether any redemption exists", required=False
    )
    total_discount_amount: str = Field(
        ..., description="Total discount amount", required=False
    )
    created_at: str = Field(..., description="Created time", required=False)
    updated_at: str = Field(..., description="Updated time", required=False)


@register_schema_to_swagger
class AdminPromotionCouponUsageDTO(_DTOBase):
    coupon_usage_bid: str = Field(
        ..., description="Coupon usage identifier", required=False
    )
    code: str = Field(..., description="Coupon code", required=False)
    status: int = Field(..., description="Coupon usage status", required=False)
    status_key: str = Field(
        ..., description="Coupon usage status i18n key", required=False
    )
    user_bid: str = Field(..., description="User identifier", required=False)
    user_mobile: str = Field(..., description="User mobile", required=False)
    user_email: str = Field(..., description="User email", required=False)
    user_nickname: str = Field(..., description="User nickname", required=False)
    shifu_bid: str = Field(..., description="Course identifier", required=False)
    course_name: str = Field(..., description="Course name", required=False)
    order_bid: str = Field(..., description="Order identifier", required=False)
    order_status: int = Field(..., description="Order status", required=False)
    order_status_key: str = Field(
        ..., description="Order status i18n key", required=False
    )
    payable_price: str = Field(..., description="Payable price", required=False)
    discount_amount: str = Field(..., description="Discount amount", required=False)
    paid_price: str = Field(..., description="Paid price", required=False)
    used_at: str = Field(..., description="Used time", required=False)
    updated_at: str = Field(..., description="Updated time", required=False)


@register_schema_to_swagger
class AdminPromotionCouponCodeDTO(_DTOBase):
    coupon_usage_bid: str = Field(
        ..., description="Coupon usage identifier", required=False
    )
    code: str = Field(..., description="Coupon code", required=False)
    status: int = Field(..., description="Coupon usage status", required=False)
    status_key: str = Field(
        ..., description="Coupon usage status i18n key", required=False
    )
    user_bid: str = Field(..., description="User identifier", required=False)
    user_mobile: str = Field(..., description="User mobile", required=False)
    user_email: str = Field(..., description="User email", required=False)
    user_nickname: str = Field(..., description="User nickname", required=False)
    order_bid: str = Field(..., description="Order identifier", required=False)
    used_at: str = Field(..., description="Used time", required=False)
    updated_at: str = Field(..., description="Updated time", required=False)


@register_schema_to_swagger
class AdminPromotionCampaignRedemptionDTO(_DTOBase):
    redemption_bid: str = Field(
        ..., description="Promotion redemption identifier", required=False
    )
    user_bid: str = Field(..., description="User identifier", required=False)
    user_mobile: str = Field(..., description="User mobile", required=False)
    user_email: str = Field(..., description="User email", required=False)
    user_nickname: str = Field(..., description="User nickname", required=False)
    order_bid: str = Field(..., description="Order identifier", required=False)
    order_status: int = Field(..., description="Order status", required=False)
    order_status_key: str = Field(
        ..., description="Order status i18n key", required=False
    )
    payable_price: str = Field(..., description="Payable price", required=False)
    discount_amount: str = Field(..., description="Discount amount", required=False)
    paid_price: str = Field(..., description="Paid price", required=False)
    status: int = Field(..., description="Redemption status", required=False)
    status_key: str = Field(
        ..., description="Redemption status i18n key", required=False
    )
    applied_at: str = Field(..., description="Applied time", required=False)
    updated_at: str = Field(..., description="Updated time", required=False)


@register_schema_to_swagger
class AdminPromotionCouponDetailDTO(_DTOBase):
    coupon: AdminPromotionCouponItemDTO = Field(
        ..., description="Coupon detail", required=False
    )
    created_user_bid: str = Field(
        ..., description="Creator user identifier", required=False
    )
    created_user_name: str = Field(..., description="Creator user name", required=False)
    updated_user_bid: str = Field(
        ..., description="Updater user identifier", required=False
    )
    updated_user_name: str = Field(..., description="Updater user name", required=False)
    remaining_count: int = Field(
        ..., description="Remaining code count", required=False
    )
    latest_used_at: str = Field(..., description="Latest used time", required=False)


@register_schema_to_swagger
class AdminPromotionCampaignDetailDTO(_DTOBase):
    campaign: AdminPromotionCampaignItemDTO = Field(
        ..., description="Campaign detail", required=False
    )
    description: str = Field(..., description="Campaign description", required=False)
    created_user_bid: str = Field(
        ..., description="Creator user identifier", required=False
    )
    created_user_name: str = Field(..., description="Creator user name", required=False)
    updated_user_bid: str = Field(
        ..., description="Updater user identifier", required=False
    )
    updated_user_name: str = Field(..., description="Updater user name", required=False)
    latest_applied_at: str = Field(
        ..., description="Latest applied time", required=False
    )


@register_schema_to_swagger
class AdminPromotionListResponseDTO(_DTOBase):
    summary: AdminPromotionSummaryDTO = Field(
        ..., description="Summary payload", required=False
    )
    page: int = Field(..., description="Current page", required=False)
    page_size: int = Field(..., description="Page size", required=False)
    total: int = Field(..., description="Total count", required=False)
    page_count: int = Field(..., description="Page count", required=False)
    items: List[dict] = Field(..., description="List items", required=False)

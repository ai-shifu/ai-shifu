"""Define administration DTOs for promotions."""

from __future__ import annotations

from datetime import datetime
from typing import Union, get_args, get_origin

from flaskr.common.swagger import register_schema_to_swagger
from pydantic import BaseModel, Field, ValidationInfo, field_validator

_EMPTY_DATETIME_VALUES = {"", "0000-00-00", "0000-00-00 00:00:00"}

# Cache the set of datetime-typed field names per DTO subclass. The membership
# test below only runs for the rare dirty-data value, but a list endpoint can
# repeat it once per empty cell across up to ~100 rows, so resolving the field
# annotations once per class avoids the repeated get_args/get_origin walk.
_DATETIME_FIELDS_CACHE: dict[type, frozenset[str]] = {}


def _allows_datetime(annotation: object) -> bool:
    if annotation is datetime:
        return True
    origin = get_origin(annotation)
    if origin is Union or getattr(origin, "__name__", "") == "UnionType":
        return any(_allows_datetime(arg) for arg in get_args(annotation))
    return False


def _datetime_fields_for(cls: object) -> frozenset[str]:
    cached = _DATETIME_FIELDS_CACHE.get(cls)
    if cached is None:
        cached = frozenset(
            name
            for name, field in cls.model_fields.items()
            if field.annotation is not None and _allows_datetime(field.annotation)
        )
        _DATETIME_FIELDS_CACHE[cls] = cached
    return cached


class _DTOBase(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _coerce_empty_datetime(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str) or value.strip() not in _EMPTY_DATETIME_VALUES:
            return value
        if info.field_name in _datetime_fields_for(cls):
            return None
        return value

    def __json__(self) -> dict:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()


@register_schema_to_swagger
class AdminPromotionSummaryDTO(_DTOBase):
    """Represent the admin promotion summary API payload."""

    total: int = Field(..., description="Total item count")
    active: int = Field(..., description="Active item count")
    usage_count: int = Field(..., description="Usage count")
    latest_usage_at: datetime | None = Field(..., description="Latest usage time")
    covered_courses: int = Field(..., description="Covered course count")
    discount_amount: str = Field(..., description="Discount amount")


@register_schema_to_swagger
class AdminPromotionCouponItemDTO(_DTOBase):
    """Represent the admin promotion coupon item API payload."""

    coupon_bid: str = Field(..., description="Coupon batch identifier")
    name: str = Field(..., description="Coupon batch name")
    code: str = Field(..., description="Generic coupon code")
    usage_type: int = Field(..., description="Coupon usage type")
    usage_type_key: str = Field(..., description="Coupon usage type i18n key")
    discount_type: int = Field(..., description="Discount type")
    discount_type_key: str = Field(..., description="Discount type i18n key")
    value: str = Field(..., description="Discount value")
    scope_type: str = Field(..., description="Coupon scope type")
    shifu_bid: str = Field(..., description="Course identifier")
    course_name: str = Field(..., description="Course name")
    start_at: datetime | None = Field(..., description="Coupon start time")
    end_at: datetime | None = Field(..., description="Coupon end time")
    total_count: int = Field(..., description="Total count")
    used_count: int = Field(..., description="Used count")
    ops_states: list[str] = Field(..., description="Operator-facing operational states")
    computed_status: str = Field(..., description="Computed status")
    computed_status_key: str = Field(..., description="Computed status i18n key")
    created_user_bid: str = Field(..., description="Creator user identifier")
    created_user_name: str = Field(..., description="Creator user name")
    created_at: datetime | None = Field(..., description="Created time")
    updated_at: datetime | None = Field(..., description="Updated time")


@register_schema_to_swagger
class AdminPromotionCampaignItemDTO(_DTOBase):
    """Represent the admin promotion campaign item API payload."""

    promo_bid: str = Field(..., description="Promotion identifier")
    name: str = Field(..., description="Promotion name")
    shifu_bid: str = Field(..., description="Course identifier")
    course_name: str = Field(..., description="Course name")
    apply_type: int = Field(..., description="Grant type")
    discount_type: int = Field(..., description="Discount type")
    discount_type_key: str = Field(..., description="Discount type i18n key")
    value: str = Field(..., description="Discount value")
    channel: str = Field(..., description="Channel")
    start_at: datetime | None = Field(..., description="Start time")
    end_at: datetime | None = Field(..., description="End time")
    computed_status: str = Field(..., description="Computed status")
    computed_status_key: str = Field(..., description="Computed status i18n key")
    applied_order_count: int = Field(..., description="Applied order count")
    has_redemptions: bool = Field(..., description="Whether any redemption exists")
    total_discount_amount: str = Field(..., description="Total discount amount")
    created_user_bid: str = Field(..., description="Creator user identifier")
    created_user_name: str = Field(..., description="Creator user name")
    created_at: datetime | None = Field(..., description="Created time")
    updated_at: datetime | None = Field(..., description="Updated time")


@register_schema_to_swagger
class AdminPromotionCouponUsageDTO(_DTOBase):
    """Represent the admin promotion coupon usage API payload."""

    coupon_usage_bid: str = Field(..., description="Coupon usage identifier")
    code: str = Field(..., description="Coupon code")
    status: int = Field(..., description="Coupon usage status")
    status_key: str = Field(..., description="Coupon usage status i18n key")
    user_bid: str = Field(..., description="User identifier")
    user_mobile: str = Field(..., description="User mobile")
    user_email: str = Field(..., description="User email")
    user_nickname: str = Field(..., description="User nickname")
    shifu_bid: str = Field(..., description="Course identifier")
    course_name: str = Field(..., description="Course name")
    order_bid: str = Field(..., description="Order identifier")
    order_status: int = Field(..., description="Order status")
    order_status_key: str = Field(..., description="Order status i18n key")
    payable_price: str = Field(..., description="Payable price")
    discount_amount: str = Field(..., description="Discount amount")
    paid_price: str = Field(..., description="Paid price")
    used_at: datetime | None = Field(..., description="Used time")
    updated_at: datetime | None = Field(..., description="Updated time")


@register_schema_to_swagger
class AdminPromotionCouponCodeDTO(_DTOBase):
    """Represent the admin promotion coupon code API payload."""

    coupon_usage_bid: str = Field(..., description="Coupon usage identifier")
    code: str = Field(..., description="Coupon code")
    status: int = Field(..., description="Coupon usage status")
    status_key: str = Field(..., description="Coupon usage status i18n key")
    user_bid: str = Field(..., description="User identifier")
    user_mobile: str = Field(..., description="User mobile")
    user_email: str = Field(..., description="User email")
    user_nickname: str = Field(..., description="User nickname")
    order_bid: str = Field(..., description="Order identifier")
    used_at: datetime | None = Field(..., description="Used time")
    updated_at: datetime | None = Field(..., description="Updated time")


@register_schema_to_swagger
class AdminPromotionCampaignRedemptionDTO(_DTOBase):
    """Represent the admin promotion campaign redemption API payload."""

    redemption_bid: str = Field(..., description="Promotion redemption identifier")
    user_bid: str = Field(..., description="User identifier")
    user_mobile: str = Field(..., description="User mobile")
    user_email: str = Field(..., description="User email")
    user_nickname: str = Field(..., description="User nickname")
    order_bid: str = Field(..., description="Order identifier")
    order_status: int = Field(..., description="Order status")
    order_status_key: str = Field(..., description="Order status i18n key")
    payable_price: str = Field(..., description="Payable price")
    discount_amount: str = Field(..., description="Discount amount")
    paid_price: str = Field(..., description="Paid price")
    status: int = Field(..., description="Redemption status")
    status_key: str = Field(..., description="Redemption status i18n key")
    applied_at: datetime | None = Field(..., description="Applied time")
    updated_at: datetime | None = Field(..., description="Updated time")


@register_schema_to_swagger
class AdminPromotionCouponDetailDTO(_DTOBase):
    """Represent the admin promotion coupon detail API payload."""

    coupon: AdminPromotionCouponItemDTO = Field(..., description="Coupon detail")
    created_user_bid: str = Field(..., description="Creator user identifier")
    created_user_name: str = Field(..., description="Creator user name")
    updated_user_bid: str = Field(..., description="Updater user identifier")
    updated_user_name: str = Field(..., description="Updater user name")
    remaining_count: int = Field(..., description="Remaining code count")
    latest_used_at: datetime | None = Field(..., description="Latest used time")


@register_schema_to_swagger
class AdminPromotionCampaignDetailDTO(_DTOBase):
    """Represent the admin promotion campaign detail API payload."""

    campaign: AdminPromotionCampaignItemDTO = Field(..., description="Campaign detail")
    description: str = Field(..., description="Campaign description")
    created_user_bid: str = Field(..., description="Creator user identifier")
    created_user_name: str = Field(..., description="Creator user name")
    updated_user_bid: str = Field(..., description="Updater user identifier")
    updated_user_name: str = Field(..., description="Updater user name")
    latest_applied_at: datetime | None = Field(..., description="Latest applied time")


@register_schema_to_swagger
class AdminPromotionListResponseDTO(_DTOBase):
    """Represent the admin promotion list response API payload."""

    summary: AdminPromotionSummaryDTO = Field(..., description="Summary payload")
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Page size")
    total: int = Field(..., description="Total count")
    page_count: int = Field(..., description="Page count")
    items: list[dict] = Field(..., description="List items")

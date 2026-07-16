"""DTOs for operator user admin endpoints.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any
from pydantic import BaseModel, Field
from flaskr.common.swagger import register_schema_to_swagger
from flaskr.service.billing.dtos import BillingPlanDTO


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
    learning_course_count: int = Field(
        default=0,
        description="Count of courses the user learned",
        required=False,
    )
    created_courses: list[AdminOperationUserCourseSummaryDTO] = Field(
        default_factory=list,
        description="Courses created by the user",
        required=False,
    )
    created_course_count: int = Field(
        default=0,
        description="Count of courses created by the user",
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
    credits_expire_at: datetime | None = Field(
        default=None,
        description="Earliest active creator credit expiry",
        required=False,
    )
    has_active_subscription: bool = Field(
        default=False,
        description="Whether the user currently has an active subscription",
        required=False,
    )
    last_login_at: datetime | None = Field(
        default=None,
        description="Latest login timestamp",
        required=False,
    )
    last_learning_at: datetime | None = Field(
        default=None,
        description="Latest learning timestamp",
        required=False,
    )
    created_at: datetime | None = Field(..., description="Created at", required=False)
    updated_at: datetime | None = Field(..., description="Updated at", required=False)

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserOverviewDTO(BaseModel):
    """Overview metrics shown in the operator user list."""

    total_user_count: int = Field(default=0, description="Total users", required=False)
    registered_user_count: int = Field(
        default=0,
        description="Users whose current status is registered, trial, or paid",
        required=False,
    )
    creator_user_count: int = Field(
        default=0, description="Users with creator identity", required=False
    )
    learner_user_count: int = Field(
        default=0,
        description="Users with learner identity or learning access",
        required=False,
    )
    paid_user_count: int = Field(
        default=0, description="Users whose status is paid", required=False
    )
    created_last_30d_user_count: int = Field(
        default=0,
        description="Users created in the last 30 calendar days",
        required=False,
    )
    registered_last_30d_user_count: int = Field(
        default=0,
        description="Users who completed registration in the last 30 calendar days",
        required=False,
    )
    learning_active_30d_user_count: int = Field(
        default=0,
        description="Distinct users with learning activity in the last 30 days",
        required=False,
    )
    paid_last_30d_user_count: int = Field(
        default=0,
        description="Distinct users with successful payments in the last 30 days",
        required=False,
    )
    guest_user_count: int = Field(
        default=0, description="Users whose status is unregistered", required=False
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserListDTO(BaseModel):
    """Paginated operator user list."""

    page: int = Field(..., description="page", required=False)
    page_size: int = Field(..., description="page_size", required=False)
    total: int = Field(..., description="total", required=False)
    page_count: int = Field(..., description="page_count", required=False)
    data: list[AdminOperationUserSummaryDTO] = Field(
        default_factory=list, description="data", required=False
    )

    def __init__(
        self,
        page: int,
        page_size: int,
        total: int,
        data: list[AdminOperationUserSummaryDTO],
    ) -> None:
        safe_page_size = int(page_size or 0)
        super().__init__(
            page=page,
            page_size=page_size,
            total=total,
            page_count=math.ceil(total / safe_page_size if safe_page_size > 0 else 0),
            data=data,
        )

    def __json__(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total": self.total,
            "page_count": self.page_count,
            "items": [item.__json__() for item in self.data],
        }


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
    credits_expire_at: datetime | None = Field(
        default=None,
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
        required=True,
    )
    amount: str = Field(..., description="Granted credits amount", required=True)
    grant_type: str = Field(
        default="manual_credit",
        description="Grant type: manual_credit or referral_reward",
        required=False,
    )
    grant_source: str = Field(
        ..., description="Grant source: reward or compensation", required=True
    )
    validity_preset: str = Field(
        ..., description="Grant validity preset", required=True
    )
    display_name: str = Field(
        default="",
        description="Optional user-visible grant display name",
        required=False,
    )
    note: str = Field(default="", description="Optional operator note", required=False)

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserCreditGrantResultDTO(BaseModel):
    """Operator credits grant response payload."""

    status: str = Field(default="granted", description="Grant result status")
    user_bid: str = Field(..., description="Target user business identifier")
    amount: str = Field(..., description="Granted credits amount", required=False)
    grant_type: str = Field(
        default="manual_credit",
        description="Grant type: manual_credit or referral_reward",
        required=False,
    )
    grant_source: str = Field(
        ..., description="Grant source: reward or compensation", required=False
    )
    validity_preset: str = Field(
        ..., description="Applied validity preset", required=False
    )
    expires_at: datetime | None = Field(
        default=None, description="Resolved expiry timestamp", required=False
    )
    display_name: str = Field(
        default="",
        description="User-visible grant display name",
        required=False,
    )
    note: str = Field(
        default="",
        description="User-visible grant note",
        required=False,
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
class AdminOperationUserReferralRewardSummaryDTO(BaseModel):
    """Current referral reward pool shown in the operator grant dialog."""

    available_credits: str = Field(
        default="0",
        description="Current active referral reward credits",
        required=False,
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Current active referral reward expiry timestamp",
        required=False,
    )
    wallet_bucket_bid: str = Field(
        default="",
        description="Current active referral reward wallet bucket identifier",
        required=False,
    )
    grant_count: int = Field(
        default=0,
        description="Successful referral reward grant count",
        required=False,
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserGrantBootstrapDTO(BaseModel):
    """Operator grant dialog bootstrap payload."""

    plans: list[BillingPlanDTO] = Field(
        default_factory=list,
        description="Grantable billing plans",
        required=False,
    )
    current_subscription_product_display_name_i18n_key: str = Field(
        default="",
        description="Current active subscription product display name i18n key",
        required=False,
    )
    notification_status: str = Field(
        default="template_pending",
        description="Current admin package notification template status",
        required=False,
    )
    server_time: datetime | None = Field(
        default=None,
        description="Server timestamp used for grant previews",
        required=False,
    )
    referral_reward_summary: AdminOperationUserReferralRewardSummaryDTO = Field(
        default_factory=AdminOperationUserReferralRewardSummaryDTO,
        description="Current referral reward pool summary",
        required=False,
    )

    def __json__(self) -> dict[str, Any]:
        return {
            "plans": [item.__json__() for item in self.plans],
            "current_subscription_product_display_name_i18n_key": (
                self.current_subscription_product_display_name_i18n_key
            ),
            "notification_status": self.notification_status,
            "server_time": self.server_time,
            "referral_reward_summary": self.referral_reward_summary.__json__(),
        }


@register_schema_to_swagger
class AdminOperationUserPackageGrantRequestDTO(BaseModel):
    """Operator package grant request payload."""

    request_id: str = Field(
        ...,
        description="Client request identifier for idempotent package grants",
        required=True,
    )
    product_bid: str = Field(
        ...,
        description="Granted billing plan product identifier",
        required=True,
    )
    note: str = Field(default="", description="Optional operator note", required=False)

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserPackageGrantResultDTO(BaseModel):
    """Operator package grant response payload."""

    user_bid: str = Field(..., description="Target user business identifier")
    product_bid: str = Field(..., description="Granted billing plan identifier")
    subscription_bid: str = Field(
        ..., description="Active subscription identifier", required=False
    )
    bill_order_bid: str = Field(
        ..., description="Created billing order identifier", required=False
    )
    current_period_start_at: datetime | None = Field(
        default=None,
        description="Resolved subscription effective start timestamp",
        required=False,
    )
    current_period_end_at: datetime | None = Field(
        default=None,
        description="Resolved subscription effective end timestamp",
        required=False,
    )
    notification_status: str = Field(
        default="template_pending",
        description="Admin package notification template status",
        required=False,
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
    created_at: datetime | None = Field(..., description="Created at", required=False)
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
    expires_at: datetime | None = Field(
        default=None, description="Entry expires at", required=False
    )
    consumable_from: datetime | None = Field(
        default=None,
        description="Entry consumable from",
        required=False,
    )
    note: str = Field(default="", description="Ledger note", required=False)
    note_code: str = Field(
        default="",
        description="Operator-facing note code",
        required=False,
    )
    usage_bid: str = Field(
        default="",
        description="Related bill usage business identifier",
        required=False,
    )
    course_bid: str = Field(
        default="",
        description="Related course business identifier for usage entries",
        required=False,
    )
    course_name: str = Field(
        default="",
        description="Related course name for usage entries",
        required=False,
    )
    chapter_title: str = Field(
        default="",
        description="Related chapter title for usage entries",
        required=False,
    )
    lesson_title: str = Field(
        default="",
        description="Related lesson title for usage entries",
        required=False,
    )
    usage_scene: str = Field(
        default="",
        description="Usage scene: debug/preview/learning",
        required=False,
    )
    usage_mode: str = Field(
        default="",
        description="Usage mode: learn/listen/ask",
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
class AdminOperationUserCreditUsageDetailItemDTO(BaseModel):
    """Operator-facing user credit usage content-level row."""

    usage_bid: str = Field(..., description="Usage business identifier")
    created_at: datetime | None = Field(..., description="Usage created at")
    content: str = Field(default="", description="Generated output text")
    consumed_credits: str = Field(default="", description="Consumed credits")
    usage_units: int = Field(default=0, description="Metered usage units")
    input_tokens: int = Field(default=0, description="LLM input tokens")
    output_tokens: int = Field(default=0, description="LLM output tokens")
    word_count: int = Field(default=0, description="TTS word count")
    duration_ms: int = Field(default=0, description="TTS duration in milliseconds")
    segment_count: int = Field(default=0, description="TTS segment count")

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserCreditUsageDetailDTO(BaseModel):
    """Operator-facing user credit usage content-level detail."""

    usage_bid: str = Field(..., description="Usage business identifier")
    course_bid: str = Field(default="", description="Related course identifier")
    course_name: str = Field(default="", description="Related course name")
    chapter_title: str = Field(default="", description="Related chapter title")
    lesson_title: str = Field(default="", description="Related lesson title")
    usage_scene: str = Field(default="", description="Usage scene")
    usage_mode: str = Field(default="", description="Usage mode")
    total_consumed_credits: str = Field(
        default="", description="Total consumed credits"
    )
    items: list[AdminOperationUserCreditUsageDetailItemDTO] = Field(
        default_factory=list,
        description="Content-level usage rows",
        required=False,
    )

    def __json__(self) -> dict[str, Any]:
        return self.model_dump()

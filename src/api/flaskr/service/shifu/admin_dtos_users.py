"""DTOs for operator user admin endpoints.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

import math
from datetime import datetime

from flaskr.common.swagger import register_schema_to_swagger
from flaskr.service.billing.dtos import BillingPlanDTO
from pydantic import BaseModel, Field


@register_schema_to_swagger
class AdminOperationUserCourseSummaryDTO(BaseModel):
    """Course summary shown in operator user-related course lists."""

    shifu_bid: str = Field(..., description="Course business identifier")
    course_name: str = Field(..., description="Course name")
    course_status: str = Field(..., description="Course status")
    completed_lesson_count: int = Field(
        default=0,
        description="Completed visible lesson count for the learner",
    )
    total_lesson_count: int = Field(
        default=0,
        description="Total visible lesson count for the learner course",
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator user course summary as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserSummaryDTO(BaseModel):
    """User summary shown in the operator user list."""

    user_bid: str = Field(..., description="User business identifier")
    mobile: str = Field(..., description="User mobile")
    email: str = Field(..., description="User email")
    nickname: str = Field(..., description="User nickname")
    user_status: str = Field(..., description="User status")
    user_role: str = Field(..., description="Resolved user role")
    user_roles: list[str] = Field(
        default_factory=list,
        description="Resolved user roles",
    )
    login_methods: list[str] = Field(
        default_factory=list,
        description="Resolved login methods",
    )
    registration_source: str = Field(
        default="unknown",
        description="Resolved registration source",
    )
    language: str = Field(..., description="User language")
    learning_courses: list[AdminOperationUserCourseSummaryDTO] = Field(
        default_factory=list,
        description="Courses the user learned via successful orders",
    )
    learning_course_count: int = Field(
        default=0,
        description="Count of courses the user learned",
    )
    created_courses: list[AdminOperationUserCourseSummaryDTO] = Field(
        default_factory=list,
        description="Courses created by the user",
    )
    created_course_count: int = Field(
        default=0,
        description="Count of courses created by the user",
    )
    total_paid_amount: str = Field(
        default="0",
        description="Total successful paid order amount",
    )
    available_credits: str = Field(
        default="",
        description="Current active total creator credits",
    )
    subscription_credits: str = Field(
        default="",
        description="Current active subscription creator credits",
    )
    topup_credits: str = Field(
        default="",
        description="Current active top-up creator credits",
    )
    credits_expire_at: datetime | None = Field(
        default=None,
        description="Earliest active creator credit expiry",
    )
    has_active_subscription: bool = Field(
        default=False,
        description="Whether the user currently has an active subscription",
    )
    last_login_at: datetime | None = Field(
        default=None,
        description="Latest login timestamp",
    )
    last_learning_at: datetime | None = Field(
        default=None,
        description="Latest learning timestamp",
    )
    created_at: datetime | None = Field(..., description="Created at")
    updated_at: datetime | None = Field(..., description="Updated at")
    cancelled_at: datetime | None = Field(
        default=None, description="Account cancellation time"
    )
    cancellation_operator_user_bid: str = Field(
        default="", description="Operator who cancelled the account"
    )
    cancellation_operator_mobile: str = Field(
        default="", description="Cancellation operator mobile"
    )
    cancellation_operator_nickname: str = Field(
        default="", description="Cancellation operator nickname"
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator user summary as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserDetailDTO(AdminOperationUserSummaryDTO):
    """User detail including restricted cancellation audit text."""

    cancellation_reason: str = Field(
        default="", description="Operator-provided cancellation reason"
    )


@register_schema_to_swagger
class AdminOperationUserOverviewDTO(BaseModel):
    """Overview metrics shown in the operator user list."""

    total_user_count: int = Field(default=0, description="Total users")
    registered_user_count: int = Field(
        default=0,
        description="Users whose current status is registered, trial, or paid",
    )
    creator_user_count: int = Field(
        default=0, description="Users with creator identity"
    )
    learner_user_count: int = Field(
        default=0,
        description="Users with learner identity or learning access",
    )
    paid_user_count: int = Field(default=0, description="Users whose status is paid")
    created_last_30d_user_count: int = Field(
        default=0,
        description="Users created in the last 30 calendar days",
    )
    registered_last_30d_user_count: int = Field(
        default=0,
        description="Users who completed registration in the last 30 calendar days",
    )
    learning_active_30d_user_count: int = Field(
        default=0,
        description="Distinct users with learning activity in the last 30 days",
    )
    paid_last_30d_user_count: int = Field(
        default=0,
        description="Distinct users with successful payments in the last 30 days",
    )
    guest_user_count: int = Field(
        default=0, description="Users whose status is unregistered"
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator user overview as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserListDTO(BaseModel):
    """Paginated operator user list."""

    page: int = Field(..., description="page")
    page_size: int = Field(..., description="page_size")
    total: int = Field(..., description="total")
    page_count: int = Field(..., description="page_count")
    data: list[AdminOperationUserSummaryDTO] = Field(
        default_factory=list, description="data"
    )

    def __init__(
        self,
        page: int,
        page_size: int,
        total: int,
        data: list[AdminOperationUserSummaryDTO],
    ) -> None:
        """Build the admin operation user list payload."""
        safe_page_size = int(page_size or 0)
        super().__init__(
            page=page,
            page_size=page_size,
            total=total,
            page_count=math.ceil(total / safe_page_size if safe_page_size > 0 else 0),
            data=data,
        )

    def __json__(self) -> dict[str, object]:
        """Return the operator user list as JSON-compatible data."""
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
    )
    subscription_credits: str = Field(
        default="",
        description="Current active subscription creator credits",
    )
    topup_credits: str = Field(
        default="",
        description="Current active top-up creator credits",
    )
    credits_expire_at: datetime | None = Field(
        default=None,
        description="Earliest active creator credit expiry",
    )
    has_active_subscription: bool = Field(
        default=False,
        description="Whether the user currently has an active subscription",
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator user credit summary as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserCreditGrantRequestDTO(BaseModel):
    """Operator credits grant request payload."""

    request_id: str = Field(
        ...,
        description="Client request identifier for idempotent credit grants",
    )
    amount: str = Field(..., description="Granted credits amount")
    grant_type: str = Field(
        default="manual_credit",
        description="Grant type: manual_credit or referral_reward",
    )
    grant_source: str = Field(..., description="Grant source: reward or compensation")
    validity_preset: str = Field(..., description="Grant validity preset")
    display_name: str = Field(
        default="",
        description="Optional user-visible grant display name",
    )
    note: str = Field(default="", description="Optional operator note")

    def __json__(self) -> dict[str, object]:
        """Return the operator user credit grant request as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserCreditGrantResultDTO(BaseModel):
    """Operator credits grant response payload."""

    status: str = Field(default="granted", description="Grant result status")
    user_bid: str = Field(..., description="Target user business identifier")
    amount: str = Field(..., description="Granted credits amount")
    grant_type: str = Field(
        default="manual_credit",
        description="Grant type: manual_credit or referral_reward",
    )
    grant_source: str = Field(..., description="Grant source: reward or compensation")
    validity_preset: str = Field(..., description="Applied validity preset")
    expires_at: datetime | None = Field(
        default=None, description="Resolved expiry timestamp"
    )
    display_name: str = Field(
        default="",
        description="User-visible grant display name",
    )
    note: str = Field(
        default="",
        description="User-visible grant note",
    )
    wallet_bucket_bid: str = Field(..., description="Created wallet bucket identifier")
    ledger_bid: str = Field(..., description="Created ledger identifier")
    summary: AdminOperationUserCreditSummaryDTO = Field(
        ..., description="Refreshed credits summary"
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator user credit grant result as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserReferralRewardSummaryDTO(BaseModel):
    """Current referral reward pool shown in the operator grant dialog."""

    available_credits: str = Field(
        default="0",
        description="Current active referral reward credits",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Current active referral reward expiry timestamp",
    )
    wallet_bucket_bid: str = Field(
        default="",
        description="Current active referral reward wallet bucket identifier",
    )
    grant_count: int = Field(
        default=0,
        description="Successful referral reward grant count",
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator user referral reward summary as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserGrantBootstrapDTO(BaseModel):
    """Operator grant dialog bootstrap payload."""

    plans: list[BillingPlanDTO] = Field(
        default_factory=list,
        description="Grantable billing plans",
    )
    current_subscription_product_display_name_i18n_key: str = Field(
        default="",
        description="Current active subscription product display name i18n key",
    )
    notification_status: str = Field(
        default="template_pending",
        description="Current admin package notification template status",
    )
    server_time: datetime | None = Field(
        default=None,
        description="Server timestamp used for grant previews",
    )
    referral_reward_summary: AdminOperationUserReferralRewardSummaryDTO = Field(
        default_factory=AdminOperationUserReferralRewardSummaryDTO,
        description="Current referral reward pool summary",
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator user grant bootstrap as JSON-compatible data."""
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
    )
    product_bid: str = Field(
        ...,
        description="Granted billing plan product identifier",
    )
    note: str = Field(default="", description="Optional operator note")

    def __json__(self) -> dict[str, object]:
        """Return the operator user package grant request as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserPackageGrantResultDTO(BaseModel):
    """Operator package grant response payload."""

    user_bid: str = Field(..., description="Target user business identifier")
    product_bid: str = Field(..., description="Granted billing plan identifier")
    subscription_bid: str = Field(..., description="Active subscription identifier")
    bill_order_bid: str = Field(..., description="Created billing order identifier")
    current_period_start_at: datetime | None = Field(
        default=None,
        description="Resolved subscription effective start timestamp",
    )
    current_period_end_at: datetime | None = Field(
        default=None,
        description="Resolved subscription effective end timestamp",
    )
    notification_status: str = Field(
        default="template_pending",
        description="Admin package notification template status",
    )
    summary: AdminOperationUserCreditSummaryDTO = Field(
        ..., description="Refreshed credits summary"
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator user package grant result as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserCreditLedgerItemDTO(BaseModel):
    """Operator-facing user credit ledger row."""

    ledger_bid: str = Field(..., description="Ledger business identifier")
    created_at: datetime | None = Field(..., description="Created at")
    entry_type: str = Field(..., description="Ledger entry type")
    source_type: str = Field(..., description="Ledger source type")
    display_entry_type: str = Field(
        default="",
        description="Operator-facing ledger entry type",
    )
    display_source_type: str = Field(
        default="",
        description="Operator-facing ledger source type",
    )
    amount: str = Field(..., description="Ledger amount")
    balance_after: str = Field(..., description="Balance after entry")
    expires_at: datetime | None = Field(default=None, description="Entry expires at")
    consumable_from: datetime | None = Field(
        default=None,
        description="Entry consumable from",
    )
    note: str = Field(default="", description="Ledger note")
    note_code: str = Field(
        default="",
        description="Operator-facing note code",
    )
    usage_bid: str = Field(
        default="",
        description="Related bill usage business identifier",
    )
    course_bid: str = Field(
        default="",
        description="Related course business identifier for usage entries",
    )
    course_name: str = Field(
        default="",
        description="Related course name for usage entries",
    )
    chapter_title: str = Field(
        default="",
        description="Related chapter title for usage entries",
    )
    lesson_title: str = Field(
        default="",
        description="Related lesson title for usage entries",
    )
    usage_scene: str = Field(
        default="",
        description="Usage scene: debug/preview/learning",
    )
    usage_mode: str = Field(
        default="",
        description="Usage mode: learn/listen/ask",
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator user credit ledger item as JSON-compatible data."""
        return self.model_dump()


@register_schema_to_swagger
class AdminOperationUserCreditLedgerPageDTO(BaseModel):
    """Paginated operator-facing user credit ledger response."""

    summary: AdminOperationUserCreditSummaryDTO = Field(
        ..., description="Credits summary"
    )
    items: list[AdminOperationUserCreditLedgerItemDTO] = Field(
        default_factory=list,
        description="Credit ledger items",
    )
    page: int = Field(..., description="Page index")
    page_size: int = Field(..., description="Page size")
    total: int = Field(..., description="Total count")
    page_count: int = Field(..., description="Page count")

    def __json__(self) -> dict[str, object]:
        """Return the operator user credit ledger page as JSON-compatible data."""
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

    def __json__(self) -> dict[str, object]:
        """Return the operator user credit usage detail item as JSON-compatible data."""
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
    )

    def __json__(self) -> dict[str, object]:
        """Return the operator user credit usage detail as JSON-compatible data."""
        return self.model_dump()

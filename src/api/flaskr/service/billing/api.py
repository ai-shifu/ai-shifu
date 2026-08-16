from __future__ import annotations

from flaskr.service.billing.admission import CreatorUsageAdmission, admit_creator_usage
from flaskr.service.billing.ownership import resolve_shifu_creator_bid
from flaskr.service.common.models import raise_error
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW
from flaskr.service.billing.manual_credit_grants import grant_manual_credits_to_user
from flaskr.service.billing.referral_reward_grants import (
    grant_referral_reward_credits_to_user,
    load_referral_reward_summary,
)
from flaskr.service.billing.manual_plan_grants import grant_manual_plan_to_user
from flaskr.service.billing.referral_plan_rewards import (
    ReferralPlanRewardRequest,
    grant_referral_plan_reward,
)
from flaskr.service.billing.credit_notifications import (
    assert_creator_debug_allowed,
    dry_run_credit_notifications,
    get_credit_notification_detail,
    get_operator_credit_notification_overview,
    list_credit_notification_templates,
    list_credit_notifications,
    load_credit_notification_policy,
    load_credit_notification_policy_for_operator,
    requeue_credit_notification,
    resolve_creator_limit_state,
    save_credit_notification_policy,
    sync_credit_notification_template,
)
from flaskr.service.billing.read_models import (
    build_billing_catalog,
    build_operator_credit_orders_overview,
    build_operator_credit_orders_page,
    get_operator_credit_order_detail,
)
from flaskr.service.billing.domains import (
    resolve_creator_bid_by_host,
    resolve_effective_custom_origin,
)
from flaskr.service.billing.customization import (
    build_provider_config_overrides,
    resolve_creator_public_integrations,
    resolve_payment_integration_for_new_order,
    resolve_provider_credential_context,
)
from flaskr.service.billing.operation_credits import (
    OperationCreditCaptureResult,
    OperationCreditEstimate,
    OperationCreditReleaseResult,
    OperationCreditReservationResult,
    capture_reserved_operation_credits,
    estimate_voice_clone_operation_credits,
    release_reserved_operation_credits,
    reserve_operation_credits,
)
from flaskr.service.billing.charges import (
    build_metric_charge,
    resolve_credit_multiplier_label,
)
from flaskr.service.billing import primitives as billing_primitives


def is_billing_enabled(*, default: bool = False) -> bool:
    try:
        return billing_primitives.is_billing_enabled(default=default)
    except TypeError:
        return billing_primitives.is_billing_enabled()


def quantize_credit_amount(value, *, precision: int | None = None):
    return billing_primitives.quantize_credit_amount(value, precision=precision)


def credit_decimal_to_number(value, *, precision: int | None = None):
    return billing_primitives.credit_decimal_to_number(value, precision=precision)


def to_decimal(value):
    return billing_primitives.to_decimal(value)


def admit_creator_preview_usage(
    app,
    *,
    shifu_bid: str,
) -> CreatorUsageAdmission:
    """Admit preview usage against the course owner's debug limits and wallet."""

    creator_bid = str(resolve_shifu_creator_bid(app, shifu_bid) or "").strip()
    if not creator_bid:
        raise_error("server.shifu.shifuNotFound")
    assert_creator_debug_allowed(app, creator_bid)
    return admit_creator_usage(
        app,
        creator_bid=creator_bid,
        shifu_bid=shifu_bid,
        usage_scene=BILL_USAGE_SCENE_PREVIEW,
    )


__all__ = [
    "CreatorUsageAdmission",
    "OperationCreditCaptureResult",
    "OperationCreditEstimate",
    "OperationCreditReleaseResult",
    "OperationCreditReservationResult",
    "admit_creator_usage",
    "admit_creator_preview_usage",
    "build_billing_catalog",
    "build_metric_charge",
    "build_provider_config_overrides",
    "capture_reserved_operation_credits",
    "credit_decimal_to_number",
    "estimate_voice_clone_operation_credits",
    "resolve_creator_bid_by_host",
    "resolve_creator_public_integrations",
    "resolve_effective_custom_origin",
    "resolve_payment_integration_for_new_order",
    "resolve_provider_credential_context",
    "build_operator_credit_orders_overview",
    "build_operator_credit_orders_page",
    "dry_run_credit_notifications",
    "assert_creator_debug_allowed",
    "grant_manual_credits_to_user",
    "grant_referral_reward_credits_to_user",
    "ReferralPlanRewardRequest",
    "grant_referral_plan_reward",
    "grant_manual_plan_to_user",
    "get_operator_credit_order_detail",
    "get_credit_notification_detail",
    "get_operator_credit_notification_overview",
    "is_billing_enabled",
    "list_credit_notification_templates",
    "list_credit_notifications",
    "load_credit_notification_policy",
    "load_credit_notification_policy_for_operator",
    "load_referral_reward_summary",
    "quantize_credit_amount",
    "requeue_credit_notification",
    "resolve_creator_limit_state",
    "resolve_credit_multiplier_label",
    "release_reserved_operation_credits",
    "reserve_operation_credits",
    "save_credit_notification_policy",
    "sync_credit_notification_template",
    "to_decimal",
]

"""Grant one-month plan bonus to teachers missed by the cache compensation list."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from billing_cache_compensation_common import (
    DEFAULT_CAMPAIGN_ID,
    DEFAULT_OPERATOR_USER_BID,
    dump_json,
    ensure_api_root_on_path,
)
from grant_cache_overcharge_bonus_plan import (
    DEFAULT_EXPECTED_PRICE_AMOUNT,
    DEFAULT_PRODUCT_CODE,
    _compare_existing_bonus_order,
    _load_existing_bonus_order,
    _load_target_product,
    _persist_bonus_order,
    _resolve_order_shape,
    _resume_existing_subscription_sms,
    _send_bonus_subscription_sms,
    _validate_product,
)

ensure_api_root_on_path()
os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")

from app import create_app  # noqa: E402
from flaskr.dao import db  # noqa: E402
from flaskr.service.billing.models import BillingOrder  # noqa: E402
from flaskr.service.billing.notifications import (  # noqa: E402
    stage_subscription_purchase_sms_for_paid_order,
)
from flaskr.service.billing.subscriptions import grant_paid_order_credits  # noqa: E402
from flaskr.service.user.models import UserInfo  # noqa: E402
from flaskr.util.datetime import now_utc  # noqa: E402

DEFAULT_TEACHER_CAMPAIGN_ID = "llm-cache-overcharge-teacher-bonus-20260826"
_PREVIOUS_BONUS_CHECKOUT_TYPE = "cache_overcharge_bonus_plan"
_MANUAL_PROVIDER_NAME = "manual"
_TEACHER_ROLE = 1


@dataclass(slots=True, frozen=True)
class TeacherBonusTarget:
    """One teacher selected for the follow-up bonus plan grant."""

    user_bid: str
    identify: str
    nickname: str
    state: int


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or apply the one-month plan bonus to teacher accounts that "
            "were not included in the original cache overcharge compensation list."
        ),
    )
    parser.add_argument(
        "--user-bid",
        action="append",
        default=[],
        help="Limit to one user bid. Can be passed multiple times.",
    )
    parser.add_argument(
        "--campaign-id",
        default=DEFAULT_TEACHER_CAMPAIGN_ID,
        help="Stable idempotency namespace for this teacher follow-up batch.",
    )
    parser.add_argument(
        "--previous-campaign-id",
        default=DEFAULT_CAMPAIGN_ID,
        help="Original compensation campaign id that must not be granted again.",
    )
    parser.add_argument("--product-bid", default="", help="Target plan product bid")
    parser.add_argument(
        "--product-code",
        default=DEFAULT_PRODUCT_CODE,
        help="Target plan product code when --product-bid is omitted.",
    )
    parser.add_argument(
        "--expected-price-amount",
        type=int,
        default=DEFAULT_EXPECTED_PRICE_AMOUNT,
        help="Safety check for the target plan price amount in minor units.",
    )
    parser.add_argument(
        "--operator-user-bid",
        default=DEFAULT_OPERATOR_USER_BID,
        help="Operator user bid written to audit metadata.",
    )
    parser.add_argument(
        "--subscription-sms-template-code",
        required=True,
        help="Aliyun SMS template code for this compensation bonus plan.",
    )
    parser.add_argument(
        "--subscription-sms-product-name",
        required=True,
        help="Product name used by the compensation SMS template.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist grants. Defaults to dry-run.",
    )
    return parser


def main() -> int:
    """Run the follow-up teacher one-month plan bonus script."""
    args = _build_parser().parse_args()
    if not str(args.subscription_sms_product_name or "").strip():
        message = "--subscription-sms-product-name is required."
        raise RuntimeError(message)

    app = create_app()
    results: list[dict[str, object]] = []

    with app.app_context():
        targets = _load_teacher_targets(args.user_bid)
        previous_bonus_creator_bids = _load_previous_bonus_creator_bids(
            args.previous_campaign_id
        )
        product = _load_target_product(
            product_bid=args.product_bid,
            product_code=args.product_code,
        )
        _validate_product(product, expected_price_amount=args.expected_price_amount)
        product_bid = str(product.product_bid or "").strip()
        product_code = str(product.product_code or "").strip()
        now = now_utc()

        for target in targets:
            base = _target_to_payload(target)
            if target.user_bid in previous_bonus_creator_bids:
                results.append(
                    {
                        **base,
                        "status": "skipped",
                        "reason": "already_in_original_bonus_batch",
                    }
                )
                continue

            request_id = f"{args.campaign_id}:bonus-plan:{target.user_bid}"
            existing_order = _load_existing_bonus_order(
                user_bid=target.user_bid,
                request_id=request_id,
            )
            if existing_order is not None:
                mismatch = _compare_existing_bonus_order(
                    existing_order,
                    user_bid=target.user_bid,
                    product=product,
                    campaign_id=args.campaign_id,
                    request_id=request_id,
                )
                if mismatch:
                    results.append(
                        {
                            **base,
                            "status": "existing_mismatch",
                            "request_id": request_id,
                            "bill_order_bid": existing_order.bill_order_bid,
                            "subscription_bid": existing_order.subscription_bid,
                            "mismatch": mismatch,
                        }
                    )
                    continue
                subscription_sms_result = {"status": "not_attempted_dry_run"}
                if args.apply:
                    subscription_sms_result = _resume_existing_subscription_sms(
                        app,
                        order=existing_order,
                        template_code=args.subscription_sms_template_code,
                        product_name=args.subscription_sms_product_name,
                    )
                results.append(
                    {
                        **base,
                        "status": "existing_match",
                        "request_id": request_id,
                        "bill_order_bid": existing_order.bill_order_bid,
                        "subscription_bid": existing_order.subscription_bid,
                        "subscription_sms_result": _sanitize_sms_result(
                            subscription_sms_result
                        ),
                    }
                )
                continue

            shape = _resolve_order_shape(
                app=app,
                user_bid=target.user_bid,
                product=product,
                now=now,
            )
            if args.subscription_sms_product_name:
                shape["metadata"]["bonus_product_name"] = str(
                    args.subscription_sms_product_name
                ).strip()
            if not args.apply:
                results.append(
                    {
                        **base,
                        "status": "eligible",
                        "request_id": request_id,
                        "product_bid": product_bid,
                        "product_code": product_code,
                        "subscription_purchase_sms": True,
                        **shape["preview"],
                    }
                )
                continue

            order = _persist_bonus_order(
                app=app,
                user_bid=target.user_bid,
                product=product,
                request_id=request_id,
                campaign_id=args.campaign_id,
                operator_user_bid=args.operator_user_bid,
                shape=shape,
            )
            granted = grant_paid_order_credits(app, order)
            should_enqueue_subscription_sms = (
                stage_subscription_purchase_sms_for_paid_order(
                    order,
                    previous_status=None,
                )
            )
            bill_order_bid = str(order.bill_order_bid or "").strip()
            subscription_bid = str(order.subscription_bid or "").strip()
            db.session.commit()
            subscription_sms_result: dict[str, object] = {"status": "not_staged"}
            if should_enqueue_subscription_sms:
                subscription_sms_result = _send_bonus_subscription_sms(
                    app,
                    bill_order_bid=bill_order_bid,
                    template_code=args.subscription_sms_template_code,
                )

            results.append(
                {
                    **base,
                    "status": "granted" if granted else "noop_existing",
                    "request_id": request_id,
                    "bill_order_bid": bill_order_bid,
                    "subscription_bid": subscription_bid,
                    "credit_notification_status": "skipped_bonus_plan",
                    "subscription_purchase_sms": bool(should_enqueue_subscription_sms),
                    "subscription_sms_result": _sanitize_sms_result(
                        subscription_sms_result
                    ),
                    **shape["preview"],
                }
            )

    dump_json(
        {
            "status": "applied" if args.apply else "dry_run",
            "dry_run": not args.apply,
            "campaign_id": args.campaign_id,
            "previous_campaign_id": args.previous_campaign_id,
            "product_bid": product_bid,
            "product_code": product_code,
            "candidate_teacher_count": len(targets),
            "excluded_original_bonus_count": sum(
                1
                for item in results
                if item["status"] == "skipped"
                and item.get("reason") == "already_in_original_bonus_batch"
            ),
            "eligible_count": sum(
                1 for item in results if item["status"] == "eligible"
            ),
            "applied_count": sum(
                1 for item in results if item["status"] in {"granted", "noop_existing"}
            ),
            "existing_count": sum(
                1 for item in results if item["status"] == "existing_match"
            ),
            "mismatch_count": sum(
                1 for item in results if item["status"] == "existing_mismatch"
            ),
            "skipped_count": sum(1 for item in results if item["status"] == "skipped"),
            "results": results,
        }
    )
    if any(item["status"] == "existing_mismatch" for item in results):
        return 2
    return 0


def _load_teacher_targets(user_bids: list[str]) -> list[TeacherBonusTarget]:
    normalized = {str(user_bid or "").strip() for user_bid in user_bids}
    normalized.discard("")

    query = UserInfo.query.filter(
        UserInfo.deleted == 0,
        UserInfo.is_creator == _TEACHER_ROLE,
        UserInfo.user_bid != "",
    )
    if normalized:
        query = query.filter(UserInfo.user_bid.in_(normalized))

    rows = query.order_by(UserInfo.id.asc()).all()
    return [
        TeacherBonusTarget(
            user_bid=str(row.user_bid or "").strip(),
            identify=str(row.user_identify or "").strip(),
            nickname=str(row.nickname or "").strip(),
            state=int(row.state or 0),
        )
        for row in rows
        if str(row.user_bid or "").strip()
    ]


def _load_previous_bonus_creator_bids(previous_campaign_id: str) -> set[str]:
    provider_reference_prefix = (
        f"{_PREVIOUS_BONUS_CHECKOUT_TYPE}:{previous_campaign_id}:bonus-plan:"
    )
    rows = (
        BillingOrder.query.with_entities(BillingOrder.creator_bid)
        .filter(
            BillingOrder.deleted == 0,
            BillingOrder.payment_provider == _MANUAL_PROVIDER_NAME,
            BillingOrder.provider_reference_id.like(f"{provider_reference_prefix}%"),
        )
        .all()
    )
    return {str(row.creator_bid or "").strip() for row in rows if row.creator_bid}


def _target_to_payload(target: TeacherBonusTarget) -> dict[str, object]:
    return {
        "user_bid": target.user_bid,
        "identify": _mask_identifier(target.identify),
        "nickname_present": bool(str(target.nickname or "").strip()),
        "state": target.state,
    }


def _mask_identifier(identifier: str) -> str:
    normalized = str(identifier or "").strip()
    if len(normalized) >= 11 and normalized.isdigit():
        return f"{normalized[:3]}****{normalized[-4:]}"
    if "@" in normalized:
        name, _, domain = normalized.partition("@")
        if not name or not domain:
            return "email"
        return f"{name[:2]}***@{domain}"
    return "non_mobile" if normalized else ""


def _sanitize_sms_result(payload: dict[str, object]) -> dict[str, object]:
    result = dict(payload)
    if "mobile" in result:
        result["mobile"] = _mask_identifier(str(result["mobile"] or ""))
    return result


if __name__ == "__main__":
    raise SystemExit(main())

"""Grant the one-month plan bonus for the LLM cache overcharge incident."""

from __future__ import annotations

import argparse
import os

from billing_cache_compensation_common import (
    DEFAULT_CAMPAIGN_ID,
    DEFAULT_INPUT_PATH,
    DEFAULT_OPERATOR_USER_BID,
    DEFAULT_SHEET_NAME,
    dump_json,
    ensure_api_root_on_path,
    filter_rows_by_user_bid,
    load_reference_rows,
    row_to_payload,
)

ensure_api_root_on_path()
os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")

from app import create_app  # noqa: E402
from flaskr.api.sms.aliyun import send_sms_ali  # noqa: E402
from flaskr.dao import db  # noqa: E402
from flaskr.service.billing.consts import (  # noqa: E402
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
)
from flaskr.service.billing.models import (  # noqa: E402
    BillingOrder,
    BillingProduct,
    BillingSubscription,
)
from flaskr.service.billing.notifications import (  # noqa: E402
    enqueue_subscription_purchase_sms,
    load_creator_mobile_snapshot,
    stage_subscription_purchase_sms_for_paid_order,
)
from flaskr.service.billing.queries import (  # noqa: E402
    calculate_self_managed_billing_cycle_end,
    calculate_self_managed_billing_cycle_end_after_boundary,
    extract_order_metadata_datetime,
    load_primary_active_subscription,
)
from flaskr.service.billing.subscriptions import grant_paid_order_credits  # noqa: E402
from flaskr.service.user.repository import load_user_aggregate  # noqa: E402
from flaskr.util.datetime import now_utc, to_utc_iso  # noqa: E402
from flaskr.util.timezone import format_with_app_timezone  # noqa: E402
from flaskr.util.uuid import generate_id  # noqa: E402

DEFAULT_PRODUCT_CODE = "creator-plan-monthly-pro"
DEFAULT_EXPECTED_PRICE_AMOUNT = 19900
_MANUAL_PROVIDER_NAME = "manual"
_CHECKOUT_TYPE = "cache_overcharge_bonus_plan"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or apply the one-month plan bonus for users listed in "
            "the LLM cache overcharge reference sheet."
        ),
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH, help="xlsx/csv input")
    parser.add_argument("--sheet", default=DEFAULT_SHEET_NAME, help="xlsx sheet name")
    parser.add_argument(
        "--user-bid",
        action="append",
        default=[],
        help="Limit to one user bid. Can be passed multiple times.",
    )
    parser.add_argument(
        "--campaign-id",
        default=DEFAULT_CAMPAIGN_ID,
        help="Stable idempotency namespace for this compensation batch.",
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
        default="",
        help=(
            "Optional Aliyun SMS template code for this compensation bonus "
            "plan only. Defaults to the global subscription purchase template."
        ),
    )
    parser.add_argument(
        "--subscription-sms-product-name",
        default="",
        help=(
            "Product name used by --subscription-sms-template-code. "
            "Required when the custom template expects a product variable."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist grants. Defaults to dry-run.",
    )
    return parser


def main() -> int:
    """Run the one-month plan bonus script."""
    args = _build_parser().parse_args()
    rows = filter_rows_by_user_bid(
        load_reference_rows(args.input, sheet_name=args.sheet),
        args.user_bid,
    )
    app = create_app()
    results: list[dict[str, object]] = []

    with app.app_context():
        product = _load_target_product(
            product_bid=args.product_bid,
            product_code=args.product_code,
        )
        _validate_product(product, expected_price_amount=args.expected_price_amount)
        product_bid = str(product.product_bid or "").strip()
        product_code = str(product.product_code or "").strip()
        now = now_utc()
        for row in rows:
            base = row_to_payload(row)
            aggregate = load_user_aggregate(row.user_bid)
            if aggregate is None:
                results.append(
                    {**base, "status": "skipped", "reason": "user_not_found"}
                )
                continue

            request_id = f"{args.campaign_id}:bonus-plan:{row.user_bid}"
            existing_order = _load_existing_bonus_order(
                user_bid=row.user_bid,
                request_id=request_id,
            )
            if existing_order is not None:
                results.append(
                    {
                        **base,
                        "status": "existing",
                        "request_id": request_id,
                        "bill_order_bid": existing_order.bill_order_bid,
                        "subscription_bid": existing_order.subscription_bid,
                    }
                )
                continue

            shape = _resolve_order_shape(
                app=app,
                user_bid=row.user_bid,
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
                user_bid=row.user_bid,
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
                if args.subscription_sms_template_code:
                    subscription_sms_result = _send_bonus_subscription_sms(
                        app,
                        bill_order_bid=bill_order_bid,
                        template_code=args.subscription_sms_template_code,
                    )
                else:
                    subscription_sms_result = enqueue_subscription_purchase_sms(
                        app,
                        bill_order_bid=bill_order_bid,
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
                    "subscription_sms_result": subscription_sms_result,
                    **shape["preview"],
                }
            )

    dump_json(
        {
            "status": "applied" if args.apply else "dry_run",
            "dry_run": not args.apply,
            "input": args.input,
            "sheet": args.sheet,
            "product_bid": product_bid,
            "product_code": product_code,
            "candidate_count": len(rows),
            "eligible_count": sum(
                1 for item in results if item["status"] == "eligible"
            ),
            "applied_count": sum(
                1 for item in results if item["status"] in {"granted", "noop_existing"}
            ),
            "existing_count": sum(
                1 for item in results if item["status"] == "existing"
            ),
            "skipped_count": sum(1 for item in results if item["status"] == "skipped"),
            "results": results,
        }
    )
    return 0


def _load_target_product(*, product_bid: str, product_code: str) -> BillingProduct:
    query = BillingProduct.query.filter(
        BillingProduct.deleted == 0,
        BillingProduct.product_type == BILLING_PRODUCT_TYPE_PLAN,
        BillingProduct.status == BILLING_PRODUCT_STATUS_ACTIVE,
    )
    normalized_product_bid = str(product_bid or "").strip()
    if normalized_product_bid:
        query = query.filter(BillingProduct.product_bid == normalized_product_bid)
    else:
        query = query.filter(
            BillingProduct.product_code == str(product_code or "").strip()
        )
    product = query.order_by(BillingProduct.id.desc()).first()
    if product is None:
        message = "Target active billing plan product was not found."
        raise RuntimeError(message)
    return product


def _validate_product(
    product: BillingProduct,
    *,
    expected_price_amount: int,
) -> None:
    if (
        expected_price_amount > 0
        and int(product.price_amount or 0) != expected_price_amount
    ):
        message = (
            "Target product price safety check failed: "
            f"expected {expected_price_amount}, got {int(product.price_amount or 0)}."
        )
        raise RuntimeError(message)


def _load_existing_bonus_order(
    *,
    user_bid: str,
    request_id: str,
) -> BillingOrder | None:
    return (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == user_bid,
            BillingOrder.payment_provider == _MANUAL_PROVIDER_NAME,
            BillingOrder.provider_reference_id == _provider_reference(request_id),
            BillingOrder.status == BILLING_ORDER_STATUS_PAID,
        )
        .order_by(BillingOrder.id.desc())
        .first()
    )


def _provider_reference(request_id: str) -> str:
    return f"{_CHECKOUT_TYPE}:{request_id}"


def _send_bonus_subscription_sms(
    app: object,
    *,
    bill_order_bid: str,
    template_code: str,
) -> dict[str, object]:
    order = BillingOrder.query.filter(
        BillingOrder.deleted == 0,
        BillingOrder.bill_order_bid == bill_order_bid,
    ).first()
    if order is None:
        return {"status": "not_found", "bill_order_bid": bill_order_bid}

    mobile = load_creator_mobile_snapshot(order.creator_bid)
    if not mobile:
        _write_subscription_sms_status(
            order,
            status="skipped_no_mobile",
            error_code="missing_mobile",
            error_message="Creator mobile is empty.",
        )
        db.session.add(order)
        db.session.commit()
        return {"status": "skipped_no_mobile", "bill_order_bid": bill_order_bid}

    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    product = str(metadata.get("bonus_product_name") or order.product_bid or "").strip()
    date_text = str(metadata.get("bonus_cycle_end_at") or "").strip()
    if not date_text:
        date_text = str(metadata.get("applied_cycle_end_at") or "").strip()
    if not date_text:
        _write_subscription_sms_status(
            order,
            status="failed_missing_date",
            error_code="missing_date",
            error_message="Subscription expiry date could not be resolved.",
        )
        db.session.add(order)
        db.session.commit()
        return {"status": "failed_missing_date", "bill_order_bid": bill_order_bid}

    _write_subscription_sms_status(
        order, status="processing", template_code=template_code
    )
    db.session.add(order)
    db.session.commit()

    response = send_sms_ali(
        app,
        mobile,
        template_code=template_code,
        template_params={"product": product, "date": date_text},
    )
    body = getattr(response, "body", None)
    if response is not None:
        _write_subscription_sms_status(
            order,
            status="sent",
            template_code=template_code,
            provider_response={
                "code": str(getattr(body, "code", "") or ""),
                "message": str(getattr(body, "message", "") or ""),
                "request_id": str(getattr(body, "request_id", "") or ""),
                "biz_id": str(getattr(body, "biz_id", "") or ""),
            },
        )
        db.session.add(order)
        db.session.commit()
        return {
            "status": "sent",
            "bill_order_bid": bill_order_bid,
            "mobile": mobile,
            "template_code": template_code,
        }

    _write_subscription_sms_status(
        order,
        status="failed_provider",
        template_code=template_code,
        error_code="provider_failed",
        error_message="Aliyun SMS provider returned no response.",
    )
    db.session.add(order)
    db.session.commit()
    return {
        "status": "failed_provider",
        "bill_order_bid": bill_order_bid,
        "mobile": mobile,
        "template_code": template_code,
    }


def _write_subscription_sms_status(
    order: BillingOrder,
    *,
    status: str,
    template_code: str = "",
    error_code: str = "",
    error_message: str = "",
    provider_response: dict[str, object] | None = None,
) -> None:
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    notifications = metadata.get("notifications")
    if not isinstance(notifications, dict):
        notifications = {}
    payload = notifications.get("subscription_purchase_sms")
    if not isinstance(payload, dict):
        payload = {}
    now = to_utc_iso(now_utc())
    payload["status"] = status
    payload["updated_at"] = now
    if status == "processing":
        payload["attempted_at"] = now
    if status in {
        "sent",
        "failed_provider",
        "skipped_no_mobile",
        "failed_missing_date",
    }:
        payload["processed_at"] = now
    if status == "sent":
        payload["sent_at"] = now
    if template_code:
        payload["template_code"] = template_code
    if error_code:
        payload["error_code"] = error_code
    else:
        payload.pop("error_code", None)
    if error_message:
        payload["error_message"] = error_message
    else:
        payload.pop("error_message", None)
    if provider_response is not None:
        payload["provider_response"] = dict(provider_response)
    notifications["subscription_purchase_sms"] = payload
    metadata["notifications"] = notifications
    order.metadata_json = metadata


def _resolve_order_shape(
    *,
    app: object,
    user_bid: str,
    product: BillingProduct,
    now: object,
) -> dict[str, object]:
    active_subscription = load_primary_active_subscription(user_bid, as_of=now)
    if active_subscription is None:
        cycle_start_at = now
        cycle_end_at = calculate_self_managed_billing_cycle_end(
            product,
            cycle_start_at=cycle_start_at,
        )
        if cycle_end_at is None or cycle_end_at <= cycle_start_at:
            message = "Target product does not support one-cycle manual activation."
            raise RuntimeError(message)
        subscription = BillingSubscription(
            subscription_bid=generate_id(app),
            creator_bid=user_bid,
            product_bid=product.product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_DRAFT,
            billing_provider=_MANUAL_PROVIDER_NAME,
            provider_subscription_id="",
            provider_customer_id="",
            billing_anchor_at=cycle_start_at,
            current_period_start_at=cycle_start_at,
            current_period_end_at=cycle_end_at,
            grace_period_end_at=None,
            cancel_at_period_end=0,
            next_product_bid="",
            last_renewed_at=None,
            last_failed_at=None,
            metadata_json={_CHECKOUT_TYPE: True},
        )
        metadata = {
            "checkout_type": _CHECKOUT_TYPE,
            _CHECKOUT_TYPE: True,
            "applied_cycle_start_at": cycle_start_at.isoformat(),
            "applied_cycle_end_at": cycle_end_at.isoformat(),
            "bonus_cycle_end_at": format_with_app_timezone(
                app,
                cycle_end_at,
                "%Y-%m-%d %H:%M:%S",
            ),
        }
        return {
            "subscription": subscription,
            "order_type": BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            "metadata": metadata,
            "preview": {
                "effect": "immediate",
                "cycle_start_at": cycle_start_at,
                "cycle_end_at": cycle_end_at,
                "active_subscription_bid": "",
            },
        }

    cycle_start_at = _resolve_deferred_cycle_start_at(
        user_bid=user_bid,
        subscription_bid=active_subscription.subscription_bid,
        boundary_at=active_subscription.current_period_end_at or now,
    )
    cycle_end_at = calculate_self_managed_billing_cycle_end_after_boundary(
        product,
        cycle_boundary_at=cycle_start_at,
    )
    if cycle_end_at is None or cycle_end_at <= cycle_start_at:
        message = "Target product does not support one-cycle deferred activation."
        raise RuntimeError(message)
    metadata = {
        "checkout_type": _CHECKOUT_TYPE,
        _CHECKOUT_TYPE: True,
        "renewal_cycle_start_at": cycle_start_at.isoformat(),
        "renewal_cycle_end_at": cycle_end_at.isoformat(),
        "bonus_cycle_end_at": format_with_app_timezone(
            app,
            cycle_end_at,
            "%Y-%m-%d %H:%M:%S",
        ),
        "deferred_after_subscription_bid": active_subscription.subscription_bid,
        "deferred_after_product_bid": active_subscription.product_bid,
    }
    return {
        "subscription": active_subscription,
        "order_type": BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        "metadata": metadata,
        "preview": {
            "effect": "deferred",
            "cycle_start_at": cycle_start_at,
            "cycle_end_at": cycle_end_at,
            "active_subscription_bid": active_subscription.subscription_bid,
            "active_product_bid": active_subscription.product_bid,
            "active_period_end_at": active_subscription.current_period_end_at,
        },
    }


def _resolve_deferred_cycle_start_at(
    *,
    user_bid: str,
    subscription_bid: str,
    boundary_at: object,
) -> object:
    rows = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == user_bid,
            BillingOrder.subscription_bid == subscription_bid,
            BillingOrder.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            BillingOrder.status == BILLING_ORDER_STATUS_PAID,
        )
        .order_by(BillingOrder.id.asc())
        .all()
    )
    latest_cycle_end_at = boundary_at
    for row in rows:
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        cycle_end_at = extract_order_metadata_datetime(metadata, "renewal_cycle_end_at")
        if cycle_end_at is not None and cycle_end_at > latest_cycle_end_at:
            latest_cycle_end_at = cycle_end_at
    return latest_cycle_end_at


def _persist_bonus_order(
    *,
    app: object,
    user_bid: str,
    product: BillingProduct,
    request_id: str,
    campaign_id: str,
    operator_user_bid: str,
    shape: dict[str, object],
) -> BillingOrder:
    subscription = shape["subscription"]
    metadata = {
        **shape["metadata"],
        "campaign_id": campaign_id,
        "request_id": request_id,
        "operator_user_bid": operator_user_bid,
    }
    db.session.add(subscription)
    db.session.flush()
    order = BillingOrder(
        bill_order_bid=generate_id(app),
        creator_bid=user_bid,
        order_type=shape["order_type"],
        product_bid=product.product_bid,
        subscription_bid=subscription.subscription_bid,
        currency=product.currency,
        payable_amount=0,
        paid_amount=0,
        payment_provider=_MANUAL_PROVIDER_NAME,
        channel=_MANUAL_PROVIDER_NAME,
        provider_reference_id=_provider_reference(request_id),
        status=BILLING_ORDER_STATUS_PAID,
        paid_at=now_utc(),
        metadata_json=metadata,
    )
    db.session.add(order)
    db.session.flush()
    return order


if __name__ == "__main__":
    raise SystemExit(main())

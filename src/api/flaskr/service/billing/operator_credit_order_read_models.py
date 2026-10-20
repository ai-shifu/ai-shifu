"""Operator credit order list, overview and detail read models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.pagination import (
    DEFAULT_PAGE_INDEX,
    DEFAULT_PAGE_SIZE,
    normalize_pagination,
)
from sqlalchemy import case, select

from .consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
)
from .dtos import (
    OperatorCreditOrderDetailDTO,
    OperatorCreditOrderOverviewDTO,
    OperatorCreditOrdersPageDTO,
)
from .models import (
    BillingOrder,
    BillingProduct,
    CreditWallet,
    CreditWalletBucket,
)
from .primitives import credit_decimal_to_number
from .primitives import normalize_bid as _normalize_bid
from .queries import (
    build_page_payload as _build_page_payload,
)
from .queries import (
    resolve_order_status_filter as _resolve_order_status_filter,
)
from .read_model_lookups import (
    _load_credit_order_grant_map,
    _load_credit_order_product_map,
    _load_matching_creator_bids_for_keyword,
    _load_matching_credit_order_product_bids,
    _load_operator_creator_map,
)
from .serializers import (
    serialize_operator_credit_order as _serialize_operator_credit_order,
)

if TYPE_CHECKING:
    from flask import Flask


def _resolve_credit_order_kind_filter(kind: str) -> int | None:
    normalized_kind = str(kind or "").strip().lower()
    if not normalized_kind:
        return None
    if normalized_kind == "plan":
        return BILLING_PRODUCT_TYPE_PLAN
    if normalized_kind == "topup":
        return BILLING_PRODUCT_TYPE_TOPUP
    raise_param_error("credit_order_kind")
    return None


def build_operator_credit_orders_page(
    app: Flask,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    creator_keyword: str = "",
    product_keyword: str = "",
    bill_order_bid: str = "",
    credit_order_kind: str = "",
    status: str = "",
    has_available_credits: bool = False,
    payment_provider: str = "",
    start_time: object = "",
    end_time: object = "",
) -> OperatorCreditOrdersPageDTO:
    """Return paginated operator-facing creator credit orders."""
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_bill_order_bid = _normalize_bid(bill_order_bid)
    normalized_payment_provider = str(payment_provider or "").strip()
    status_code = _resolve_order_status_filter(status)
    product_type_filter = _resolve_credit_order_kind_filter(credit_order_kind)

    with app.app_context():
        query = BillingOrder.query.outerjoin(
            BillingProduct,
            BillingProduct.product_bid == BillingOrder.product_bid,
        ).filter(
            BillingOrder.deleted == 0,
        )

        if normalized_bill_order_bid:
            query = query.filter(
                BillingOrder.bill_order_bid == normalized_bill_order_bid
            )

        normalized_creator_keyword = str(creator_keyword or "").strip()
        if normalized_creator_keyword:
            matched_creator_bids = _load_matching_creator_bids_for_keyword(
                normalized_creator_keyword
            )
            if matched_creator_bids:
                query = query.filter(BillingOrder.creator_bid.in_(matched_creator_bids))
            else:
                query = query.filter(
                    BillingOrder.creator_bid == normalized_creator_keyword
                )

        normalized_product_keyword = str(product_keyword or "").strip()
        if normalized_product_keyword:
            matched_product_bids = _load_matching_credit_order_product_bids(
                normalized_product_keyword
            )
            if matched_product_bids:
                query = query.filter(BillingOrder.product_bid.in_(matched_product_bids))
            else:
                query = query.filter(BillingOrder.id == -1)

        if product_type_filter is not None:
            query = query.filter(BillingProduct.product_type == product_type_filter)

        if status_code is not None:
            query = query.filter(BillingOrder.status == status_code)

        if has_available_credits:
            query = query.filter(
                select(CreditWalletBucket.id)
                .where(
                    CreditWalletBucket.deleted == 0,
                    CreditWalletBucket.source_bid == BillingOrder.bill_order_bid,
                    CreditWalletBucket.available_credits > 0,
                )
                .exists()
            )

        if normalized_payment_provider:
            query = query.filter(
                BillingOrder.payment_provider == normalized_payment_provider
            )

        if start_time:
            query = query.filter(BillingOrder.created_at >= start_time)
        if end_time:
            query = query.filter(BillingOrder.created_at <= end_time)

        query = query.order_by(
            BillingOrder.created_at.desc(),
            BillingOrder.id.desc(),
        )

        payload = _build_page_payload(
            query,
            page_index=safe_page_index,
            page_size=safe_page_size,
            serializer=lambda row: row,
        )
        rows = list(payload.items)
        creator_map = _load_operator_creator_map(
            [str(row.creator_bid or "").strip() for row in rows]
        )
        product_map = _load_credit_order_product_map(
            [str(row.product_bid or "").strip() for row in rows]
        )
        grant_map = _load_credit_order_grant_map(
            app,
            [str(row.bill_order_bid or "").strip() for row in rows],
        )

        items = [
            _serialize_operator_credit_order(
                app,
                row,
                product=product_map.get(str(row.product_bid or "").strip()),
                creator=creator_map.get(str(row.creator_bid or "").strip(), {}),
                grant=grant_map.get(str(row.bill_order_bid or "").strip()),
            )
            for row in rows
        ]
        return OperatorCreditOrdersPageDTO(
            items=items,
            page=payload.page,
            page_count=payload.page_count,
            page_size=payload.page_size,
            total=payload.total,
        )


def build_operator_credit_orders_overview(
    app: Flask,
) -> OperatorCreditOrderOverviewDTO:
    """Return aggregate metrics for operator creator credit orders."""
    with app.app_context():
        summary = (
            BillingOrder.query.with_entities(
                db.func.count(BillingOrder.id).label("total_order_count"),
                db.func.coalesce(
                    db.func.sum(
                        case(
                            (BillingOrder.status == BILLING_ORDER_STATUS_PAID, 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("paid_order_count"),
                db.func.coalesce(
                    db.func.sum(
                        case(
                            (BillingOrder.status == BILLING_ORDER_STATUS_PENDING, 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("pending_order_count"),
                db.func.coalesce(
                    db.func.sum(
                        case(
                            (BillingOrder.status == BILLING_ORDER_STATUS_REFUNDED, 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("refunded_order_count"),
                db.func.coalesce(
                    db.func.sum(
                        case(
                            (BillingOrder.status == BILLING_ORDER_STATUS_TIMEOUT, 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("closed_order_count"),
                db.func.coalesce(
                    db.func.sum(
                        case(
                            (BillingOrder.status == BILLING_ORDER_STATUS_CANCELED, 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("canceled_order_count"),
            )
            .filter(BillingOrder.deleted == 0)
            .one()
        )
        available_credit_total = db.session.execute(
            select(
                db.func.coalesce(
                    db.func.sum(CreditWallet.available_credits),
                    0,
                )
            ).where(CreditWallet.deleted == 0)
        ).scalar()
        paid_amount_rows = db.session.execute(
            select(
                BillingOrder.currency.label("currency"),
                db.func.coalesce(
                    db.func.sum(BillingOrder.paid_amount),
                    0,
                ).label("paid_amount_total"),
            )
            .where(
                BillingOrder.deleted == 0,
                BillingOrder.status == BILLING_ORDER_STATUS_PAID,
            )
            .group_by(BillingOrder.currency)
        ).all()
        paid_amount_totals_by_currency = {
            str(row.currency or "CNY"): int(row.paid_amount_total or 0)
            for row in paid_amount_rows
        }
        if len(paid_amount_totals_by_currency) == 1:
            currency, paid_amount_total = next(
                iter(paid_amount_totals_by_currency.items())
            )
        elif len(paid_amount_totals_by_currency) == 0:
            currency, paid_amount_total = "CNY", 0
        else:
            currency, paid_amount_total = "", 0

        return OperatorCreditOrderOverviewDTO(
            total_order_count=int(summary.total_order_count or 0),
            paid_order_count=int(summary.paid_order_count or 0),
            pending_order_count=int(summary.pending_order_count or 0),
            refunded_order_count=int(summary.refunded_order_count or 0),
            closed_order_count=int(summary.closed_order_count or 0),
            canceled_order_count=int(summary.canceled_order_count or 0),
            available_credit_total=credit_decimal_to_number(available_credit_total),
            paid_amount_total=paid_amount_total,
            currency=str(currency or ""),
            paid_amount_totals_by_currency=paid_amount_totals_by_currency,
        )


def get_operator_credit_order_detail(
    app: Flask,
    *,
    bill_order_bid: str,
) -> OperatorCreditOrderDetailDTO:
    """Return operator-facing creator credit order detail."""
    normalized_bill_order_bid = _normalize_bid(bill_order_bid)
    if not normalized_bill_order_bid:
        raise_param_error("bill_order_bid")

    with app.app_context():
        row = (
            BillingOrder.query.filter(
                BillingOrder.deleted == 0,
                BillingOrder.bill_order_bid == normalized_bill_order_bid,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
        if row is None:
            raise_error("server.order.orderNotFound")

        creator_map = _load_operator_creator_map([str(row.creator_bid or "").strip()])
        product_map = _load_credit_order_product_map(
            [str(row.product_bid or "").strip()]
        )
        grant_map = _load_credit_order_grant_map(
            app,
            [normalized_bill_order_bid],
        )
        order = _serialize_operator_credit_order(
            app,
            row,
            product=product_map.get(str(row.product_bid or "").strip()),
            creator=creator_map.get(str(row.creator_bid or "").strip(), {}),
            grant=grant_map.get(normalized_bill_order_bid),
        )
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else None
        return OperatorCreditOrderDetailDTO(
            order=order,
            metadata=metadata,
            grant=grant_map.get(normalized_bill_order_bid),
        )

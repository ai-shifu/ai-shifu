from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from flask import Flask
from sqlalchemy import and_, or_
from sqlalchemy.orm import aliased

from flaskr.dao import db
from flaskr.util.datetime import now_utc
from flaskr.service.billing.api import (
    build_billing_catalog,
    grant_manual_credits_to_user,
    grant_manual_plan_to_user,
    grant_referral_reward_credits_to_user,
    load_referral_reward_summary,
)
from flaskr.service.billing.consts import (
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.models import BillingOrder, CreditLedgerEntry
from flaskr.service.common.models import raise_param_error
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu.admin import (
    COURSE_CREDIT_USAGE_MODE_ASK,
    COURSE_CREDIT_USAGE_MODE_LEARN,
    COURSE_CREDIT_USAGE_MODE_LISTEN,
    COURSE_CREDIT_USAGE_SCENE_DEBUG,
    COURSE_CREDIT_USAGE_SCENE_LEARNING,
    COURSE_CREDIT_USAGE_SCENE_PREVIEW,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_ALL,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_MANUAL,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TOPUP,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TRIAL_SUBSCRIPTION,
    OPERATOR_USER_CREDIT_GRANT_SOURCE_REWARD,
    OPERATOR_USER_CREDIT_GRANT_SOURCES,
    OPERATOR_USER_CREDIT_GRANT_TYPE_MANUAL,
    OPERATOR_USER_CREDIT_GRANT_TYPE_REFERRAL_REWARD,
    OPERATOR_USER_CREDIT_GRANT_TYPES,
    OPERATOR_USER_CREDIT_TYPE_CONSUME,
    OPERATOR_USER_CREDIT_TYPE_GRANT,
    OPERATOR_USER_CREDIT_TYPE_OTHER,
    OPERATOR_USER_CREDIT_VALIDITY_1M,
    OPERATOR_USER_CREDIT_VALIDITY_PRESETS,
    OPERATOR_USER_LIST_MAX_PAGE_SIZE,
    _allocate_usage_detail_credits,
    _assert_operator_user_grant_target_supported,
    _build_course_credit_usage_ask_filter,
    _build_course_credit_usage_learn_filter,
    _build_latest_bill_usage_record_subquery,
    _build_latest_billing_order_subquery,
    _build_operator_course_query_filter,
    _build_operator_user_credit_ledger_item,
    _build_operator_user_credit_summary,
    _collect_operator_user_credit_order_source_bids,
    _format_decimal,
    _load_active_subscription_product_display_name_i18n_key,
    _load_billing_order_map,
    _load_generated_block_content_map,
    _load_listen_segment_content_map,
    _load_operator_user_credit_summary_map,
    _load_operator_user_credit_usage_context_map,
    _load_operator_user_credit_usage_main_row,
    _load_operator_user_credit_usage_owner_ledger_rows,
    _load_operator_user_credit_usage_segment_rows,
    _load_operator_user_or_raise,
    _normalize_metadata_json,
    _quantize_credit_amount,
    _resolve_course_credit_usage_mode_filter,
    _resolve_course_credit_usage_scene_filter,
    _resolve_operator_credit_grant_type,
    _resolve_operator_user_credit_grant_source_filter,
    _resolve_operator_user_credit_type_filter,
    _resolve_operator_user_credit_usage_context,
    _resolve_usage_detail_item_content,
)
from flaskr.service.shifu.admin_dtos import (
    AdminOperationUserCreditGrantRequestDTO,
    AdminOperationUserCreditGrantResultDTO,
    AdminOperationUserCreditLedgerPageDTO,
    AdminOperationUserCreditUsageDetailDTO,
    AdminOperationUserCreditUsageDetailItemDTO,
    AdminOperationUserGrantBootstrapDTO,
    AdminOperationUserPackageGrantRequestDTO,
    AdminOperationUserPackageGrantResultDTO,
    AdminOperationUserReferralRewardSummaryDTO,
)


def grant_operator_user_credits(
    app: Flask,
    *,
    user_bid: str,
    operator_user_bid: str,
    payload: AdminOperationUserCreditGrantRequestDTO,
) -> AdminOperationUserCreditGrantResultDTO:
    with app.app_context():
        normalized_user_bid = str(user_bid or "").strip()
        normalized_operator_user_bid = str(operator_user_bid or "").strip()
        if not normalized_operator_user_bid:
            raise_param_error("operator_user_bid")

        user = _load_operator_user_or_raise(normalized_user_bid)
        _assert_operator_user_grant_target_supported(user)
        raw_grant_type = str(payload.grant_type or "").strip()
        normalized_grant_type = (
            OPERATOR_USER_CREDIT_GRANT_TYPE_MANUAL
            if not raw_grant_type
            else _resolve_operator_credit_grant_type(raw_grant_type, fallback="")
        )
        if normalized_grant_type not in OPERATOR_USER_CREDIT_GRANT_TYPES:
            raise_param_error("grant_type")
        normalized_grant_source = str(payload.grant_source or "").strip().lower()
        if normalized_grant_source not in OPERATOR_USER_CREDIT_GRANT_SOURCES:
            raise_param_error("grant_source")

        normalized_validity_preset = str(payload.validity_preset or "").strip().lower()
        if normalized_validity_preset not in OPERATOR_USER_CREDIT_VALIDITY_PRESETS:
            raise_param_error("validity_preset")

        normalized_request_id = str(payload.request_id or "").strip()
        if not normalized_request_id:
            raise_param_error("request_id")
        normalized_display_name = str(payload.display_name or "").strip()
        normalized_note = str(payload.note or "").strip()
        if normalized_grant_type == OPERATOR_USER_CREDIT_GRANT_TYPE_REFERRAL_REWARD:
            if normalized_grant_source != OPERATOR_USER_CREDIT_GRANT_SOURCE_REWARD:
                raise_param_error("grant_source")
            if normalized_validity_preset != OPERATOR_USER_CREDIT_VALIDITY_1M:
                raise_param_error("validity_preset")
            grant_result = grant_referral_reward_credits_to_user(
                app,
                user_bid=normalized_user_bid,
                operator_user_bid=normalized_operator_user_bid,
                request_id=normalized_request_id,
                amount=payload.amount,
                note=normalized_note,
            )
        else:
            grant_result = grant_manual_credits_to_user(
                app,
                user_bid=normalized_user_bid,
                operator_user_bid=normalized_operator_user_bid,
                request_id=normalized_request_id,
                amount=payload.amount,
                grant_source=normalized_grant_source,
                validity_preset=normalized_validity_preset,
                display_name=normalized_display_name,
                note=normalized_note,
            )

        persisted_metadata = _normalize_metadata_json(grant_result.metadata_json)
        resolved_grant_type = _resolve_operator_credit_grant_type(
            str(persisted_metadata.get("grant_type") or "").strip(),
            fallback=normalized_grant_type,
        )
        resolved_grant_source = str(
            persisted_metadata.get("grant_source") or normalized_grant_source
        ).strip()
        resolved_validity_preset = str(
            persisted_metadata.get("validity_preset") or normalized_validity_preset
        ).strip()
        resolved_amount = _format_decimal(
            _quantize_credit_amount(Decimal(str(grant_result.amount or 0)))
        )
        credit_summary_map = _load_operator_user_credit_summary_map(
            [normalized_user_bid]
        )
        summary = _build_operator_user_credit_summary(
            user=user,
            credit_summary_map=credit_summary_map,
        )
        return AdminOperationUserCreditGrantResultDTO(
            status=str(grant_result.status or "granted"),
            user_bid=normalized_user_bid,
            amount=resolved_amount,
            grant_type=resolved_grant_type,
            grant_source=resolved_grant_source,
            validity_preset=resolved_validity_preset,
            expires_at=grant_result.expires_at,
            display_name=str(persisted_metadata.get("display_name") or "").strip(),
            note=str(persisted_metadata.get("note") or "").strip(),
            wallet_bucket_bid=str(grant_result.wallet_bucket_bid or "").strip(),
            ledger_bid=str(grant_result.ledger_bid or "").strip(),
            summary=summary,
        )


def get_operator_user_grant_bootstrap(
    app: Flask,
    *,
    user_bid: str,
) -> AdminOperationUserGrantBootstrapDTO:
    with app.app_context():
        normalized_user_bid = str(user_bid or "").strip()
        user = _load_operator_user_or_raise(normalized_user_bid)
        _assert_operator_user_grant_target_supported(user)
        catalog = build_billing_catalog(app)
        server_time = now_utc()
        current_subscription_product_display_name_i18n_key = (
            _load_active_subscription_product_display_name_i18n_key(
                normalized_user_bid,
                as_of=server_time,
            )
        )
        referral_summary = load_referral_reward_summary(
            app,
            creator_bid=normalized_user_bid,
            as_of=server_time,
        )
        return AdminOperationUserGrantBootstrapDTO(
            plans=catalog.plans,
            current_subscription_product_display_name_i18n_key=(
                current_subscription_product_display_name_i18n_key
            ),
            notification_status="template_pending",
            server_time=server_time,
            referral_reward_summary=AdminOperationUserReferralRewardSummaryDTO(
                available_credits=_format_decimal(
                    _quantize_credit_amount(
                        Decimal(str(referral_summary.available_credits or 0))
                    )
                ),
                expires_at=referral_summary.expires_at,
                wallet_bucket_bid=str(referral_summary.wallet_bucket_bid or ""),
                grant_count=int(referral_summary.grant_count or 0),
            ),
        )


def grant_operator_user_package(
    app: Flask,
    *,
    user_bid: str,
    operator_user_bid: str,
    payload: AdminOperationUserPackageGrantRequestDTO,
) -> AdminOperationUserPackageGrantResultDTO:
    with app.app_context():
        normalized_user_bid = str(user_bid or "").strip()
        normalized_operator_user_bid = str(operator_user_bid or "").strip()
        if not normalized_operator_user_bid:
            raise_param_error("operator_user_bid")

        user = _load_operator_user_or_raise(normalized_user_bid)
        _assert_operator_user_grant_target_supported(user)

        grant_result = grant_manual_plan_to_user(
            app,
            user_bid=normalized_user_bid,
            product_bid=str(payload.product_bid or "").strip(),
            operator_user_bid=normalized_operator_user_bid,
            request_id=str(payload.request_id or "").strip(),
            note=str(payload.note or "").strip(),
            grant_channel="operator_user_management",
        )

        credit_summary_map = _load_operator_user_credit_summary_map(
            [normalized_user_bid]
        )
        summary = _build_operator_user_credit_summary(
            user=user,
            credit_summary_map=credit_summary_map,
        )
        return AdminOperationUserPackageGrantResultDTO(
            user_bid=normalized_user_bid,
            product_bid=grant_result.product_bid,
            subscription_bid=grant_result.subscription_bid,
            bill_order_bid=grant_result.bill_order_bid,
            current_period_start_at=grant_result.current_period_start_at,
            current_period_end_at=grant_result.current_period_end_at,
            notification_status=grant_result.notification_status,
            summary=summary,
        )


def get_operator_user_credits(
    app: Flask,
    *,
    user_bid: str,
    page_index: int,
    page_size: int,
    filters: Optional[Dict[str, Any]] = None,
) -> AdminOperationUserCreditLedgerPageDTO:
    with app.app_context():
        normalized_user_bid = str(user_bid or "").strip()
        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            OPERATOR_USER_LIST_MAX_PAGE_SIZE,
        )
        filters = filters or {}

        user = _load_operator_user_or_raise(normalized_user_bid)
        credit_summary_map = _load_operator_user_credit_summary_map(
            [normalized_user_bid]
        )
        summary = _build_operator_user_credit_summary(
            user=user,
            credit_summary_map=credit_summary_map,
        )

        credit_type = _resolve_operator_user_credit_type_filter(
            str(filters.get("credit_type", "") or "")
        )
        grant_source = _resolve_operator_user_credit_grant_source_filter(
            str(filters.get("grant_source", "") or "")
        )
        course_query = str(filters.get("course_query", "") or "").strip()
        course_id = str(filters.get("course_id", "") or "").strip()
        course_name = str(filters.get("course_name", "") or "").strip()
        resolved_course_query = course_query or course_id or course_name
        usage_mode = _resolve_course_credit_usage_mode_filter(
            str(filters.get("usage_mode", "") or "")
        )
        usage_scene = _resolve_course_credit_usage_scene_filter(
            str(filters.get("usage_scene", "") or "")
        )
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")

        if str(filters.get("credit_type", "") or "").strip() and not credit_type:
            raise_param_error("credit_type")
        if str(filters.get("grant_source", "") or "").strip() and not grant_source:
            raise_param_error("grant_source")
        if str(filters.get("usage_scene", "") or "").strip() and not usage_scene:
            raise_param_error("usage_scene")
        if str(filters.get("usage_mode", "") or "").strip() and not usage_mode:
            raise_param_error("usage_mode")

        query = CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == normalized_user_bid,
        )

        if start_time:
            query = query.filter(CreditLedgerEntry.created_at >= start_time)
        if end_time:
            query = query.filter(CreditLedgerEntry.created_at <= end_time)

        if credit_type == OPERATOR_USER_CREDIT_TYPE_CONSUME:
            query = query.filter(
                CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
                CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_USAGE,
            )
        elif credit_type == OPERATOR_USER_CREDIT_TYPE_GRANT:
            query = query.filter(
                or_(
                    CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                    and_(
                        CreditLedgerEntry.entry_type
                        == CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
                        CreditLedgerEntry.amount > 0,
                    ),
                )
            )
        elif credit_type == OPERATOR_USER_CREDIT_TYPE_OTHER:
            query = query.filter(
                or_(
                    CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
                    CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_REFUND,
                    and_(
                        CreditLedgerEntry.entry_type
                        == CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
                        CreditLedgerEntry.amount < 0,
                    ),
                )
            )

        has_grant_source_filter = (
            credit_type == OPERATOR_USER_CREDIT_TYPE_GRANT
            and grant_source != OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_ALL
        )
        has_consume_scene_filter = usage_scene not in {"", "all"}
        has_consume_usage_filter = usage_mode not in {"", "all"}
        has_consume_sub_filter = credit_type == OPERATOR_USER_CREDIT_TYPE_CONSUME and (
            bool(resolved_course_query)
            or has_consume_scene_filter
            or has_consume_usage_filter
        )
        consume_source_bids: list[str] = []
        if has_consume_sub_filter:
            consume_source_bids = [
                row[0]
                for row in query.with_entities(CreditLedgerEntry.source_bid)
                .filter(CreditLedgerEntry.source_bid != "")
                .distinct()
                .yield_per(100)
                if str(row[0] or "").strip()
            ]

        if has_grant_source_filter:
            if grant_source == OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TOPUP:
                query = query.filter(
                    CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_TOPUP
                )
            elif grant_source == OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_MANUAL:
                query = query.filter(
                    CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_MANUAL
                )
            else:
                latest_order_subquery = _build_latest_billing_order_subquery(
                    creator_bid=normalized_user_bid
                )
                latest_order = aliased(BillingOrder)
                checkout_type_expr = db.func.lower(
                    db.func.coalesce(
                        CreditLedgerEntry.metadata_json["checkout_type"].as_string(),
                        latest_order.metadata_json["checkout_type"].as_string(),
                        "",
                    )
                )
                query = (
                    query.outerjoin(
                        latest_order_subquery,
                        latest_order_subquery.c.bill_order_bid
                        == CreditLedgerEntry.source_bid,
                    )
                    .outerjoin(
                        latest_order,
                        latest_order.id == latest_order_subquery.c.max_id,
                    )
                    .filter(
                        CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION
                    )
                )
                if (
                    grant_source
                    == OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TRIAL_SUBSCRIPTION
                ):
                    query = query.filter(checkout_type_expr == "trial_bootstrap")
                else:
                    query = query.filter(checkout_type_expr != "trial_bootstrap")
        elif has_consume_sub_filter:
            latest_usage_subquery = _build_latest_bill_usage_record_subquery(
                usage_bids=consume_source_bids
            )
            usage_row = aliased(BillUsageRecord)
            query = query.join(
                latest_usage_subquery,
                latest_usage_subquery.c.usage_bid == CreditLedgerEntry.source_bid,
            ).join(usage_row, usage_row.id == latest_usage_subquery.c.max_id)
            if resolved_course_query:
                course_query_filter = _build_operator_course_query_filter(
                    usage_row.shifu_bid,
                    resolved_course_query,
                )
                if course_query_filter is not None:
                    query = query.filter(course_query_filter)

            if usage_scene == COURSE_CREDIT_USAGE_SCENE_LEARNING:
                query = query.filter(usage_row.usage_scene == BILL_USAGE_SCENE_PROD)
            elif usage_scene == COURSE_CREDIT_USAGE_SCENE_PREVIEW:
                query = query.filter(usage_row.usage_scene == BILL_USAGE_SCENE_PREVIEW)
            elif usage_scene == COURSE_CREDIT_USAGE_SCENE_DEBUG:
                query = query.filter(usage_row.usage_scene == BILL_USAGE_SCENE_DEBUG)

            generation_name_expr = db.func.lower(
                usage_row.extra["generation_name"].as_string()
            )
            if usage_mode == COURSE_CREDIT_USAGE_MODE_LISTEN:
                query = query.filter(usage_row.usage_type == BILL_USAGE_TYPE_TTS)
            elif usage_mode == COURSE_CREDIT_USAGE_MODE_ASK:
                query = query.filter(
                    usage_row.usage_type != BILL_USAGE_TYPE_TTS,
                    _build_course_credit_usage_ask_filter(generation_name_expr),
                )
            elif usage_mode == COURSE_CREDIT_USAGE_MODE_LEARN:
                query = query.filter(
                    usage_row.usage_type != BILL_USAGE_TYPE_TTS,
                    _build_course_credit_usage_learn_filter(generation_name_expr),
                )

        order_by_query = query.order_by(
            CreditLedgerEntry.created_at.desc(), CreditLedgerEntry.id.desc()
        )
        total = query.count()
        page_offset = (safe_page_index - 1) * safe_page_size
        paged_rows = order_by_query.offset(page_offset).limit(safe_page_size).all()
        order_map = _load_billing_order_map(
            _collect_operator_user_credit_order_source_bids(paged_rows)
        )
        usage_context_map = _load_operator_user_credit_usage_context_map(
            paged_rows,
        )
        items = [
            _build_operator_user_credit_ledger_item(
                row,
                order_map=order_map,
                usage_context_map=usage_context_map,
            )
            for row in paged_rows
        ]
        return AdminOperationUserCreditLedgerPageDTO(
            summary=summary,
            items=items,
            page=safe_page_index,
            page_size=safe_page_size,
            total=total,
            page_count=((total + safe_page_size - 1) // safe_page_size) if total else 0,
        )


def get_operator_user_credit_usage_detail(
    app: Flask,
    *,
    user_bid: str,
    usage_bid: str,
) -> AdminOperationUserCreditUsageDetailDTO:
    with app.app_context():
        normalized_user_bid = str(user_bid or "").strip()
        normalized_usage_bid = str(usage_bid or "").strip()
        if not normalized_user_bid:
            raise_param_error("user_bid is required")
        if not normalized_usage_bid:
            raise_param_error("usage_bid is required")

        _load_operator_user_or_raise(normalized_user_bid)
        owner_ledger_rows = _load_operator_user_credit_usage_owner_ledger_rows(
            user_bid=normalized_user_bid,
            usage_bid=normalized_usage_bid,
        )
        if not owner_ledger_rows:
            raise_param_error("usage_bid")

        main_usage_row = _load_operator_user_credit_usage_main_row(normalized_usage_bid)
        if main_usage_row is None:
            raise_param_error("usage_bid")

        total_consumed_credits = sum(
            (abs(Decimal(row.amount or 0)) for row in owner_ledger_rows),
            Decimal("0"),
        )
        context = _resolve_operator_user_credit_usage_context(main_usage_row)
        segment_rows = _load_operator_user_credit_usage_segment_rows(
            normalized_usage_bid
        )
        detail_rows = segment_rows or [main_usage_row]
        total_segment_count = max(
            int(getattr(main_usage_row, "segment_count", 0) or 0),
            len(segment_rows),
        )
        generated_block_bids = [
            str(getattr(row, "generated_block_bid", "") or "").strip()
            for row in detail_rows + [main_usage_row]
        ]
        block_content_map = _load_generated_block_content_map(generated_block_bids)
        fallback_content = block_content_map.get(
            str(getattr(main_usage_row, "generated_block_bid", "") or "").strip(),
            "",
        )
        listen_content_map = (
            _load_listen_segment_content_map(
                progress_record_bid=str(
                    getattr(main_usage_row, "progress_record_bid", "") or ""
                ),
                generated_block_bid=str(
                    getattr(main_usage_row, "generated_block_bid", "") or ""
                ),
            )
            if int(getattr(main_usage_row, "usage_type", 0) or 0) == BILL_USAGE_TYPE_TTS
            else {}
        )
        allocated_credit_map = _allocate_usage_detail_credits(
            rows=detail_rows,
            total_consumed_credits=total_consumed_credits,
        )
        items = [
            AdminOperationUserCreditUsageDetailItemDTO(
                usage_bid=str(getattr(row, "usage_bid", "") or "").strip(),
                created_at=getattr(row, "created_at", None),
                content=_resolve_usage_detail_item_content(
                    row,
                    block_content_map=block_content_map,
                    listen_content_map=listen_content_map,
                    fallback_content=fallback_content,
                ),
                consumed_credits=_format_decimal(
                    allocated_credit_map.get(
                        str(getattr(row, "usage_bid", "") or "").strip(),
                        Decimal("0"),
                    )
                ),
                usage_units=int(getattr(row, "total", 0) or 0),
                input_tokens=int(getattr(row, "input", 0) or 0),
                output_tokens=int(getattr(row, "output", 0) or 0),
                word_count=int(getattr(row, "word_count", 0) or 0),
                duration_ms=int(getattr(row, "duration_ms", 0) or 0),
                segment_count=(
                    total_segment_count
                    if int(getattr(row, "usage_type", 0) or 0) == BILL_USAGE_TYPE_TTS
                    else int(getattr(row, "segment_count", 0) or 0)
                ),
            )
            for row in detail_rows
        ]

        return AdminOperationUserCreditUsageDetailDTO(
            usage_bid=normalized_usage_bid,
            course_bid=str(context.get("course_bid", "") or ""),
            course_name=str(context.get("course_name", "") or ""),
            chapter_title=str(context.get("chapter_title", "") or ""),
            lesson_title=str(context.get("lesson_title", "") or ""),
            usage_scene=str(context.get("usage_scene", "") or ""),
            usage_mode=str(context.get("usage_mode", "") or ""),
            total_consumed_credits=_format_decimal(total_consumed_credits),
            items=items,
        )

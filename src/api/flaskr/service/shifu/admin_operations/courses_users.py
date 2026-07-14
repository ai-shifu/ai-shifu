"""Operator course user listing and per-user learning maps.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Sequence, Set
from flask import Flask
from flaskr.dao import db
from flaskr.service.learn.const import (
    LEARN_STATUS_RESET,
)
from flaskr.service.learn.models import (
    LearnProgressRecord,
)
from flaskr.service.common.dtos import PageNationDTO
from flaskr.service.common.models import (
    raise_param_error,
)
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu.admin_dtos_courses import (
    AdminOperationCourseUserDTO,
)
from flaskr.service.shifu.models import (
    AiCourseAuth,
)
from flaskr.service.user.models import (
    UserInfo as UserEntity,
)

from flaskr.service.shifu.admin_operations.courses_shared import (
    COURSE_USER_LIST_MAX_PAGE_SIZE,
    _build_course_order_amount_expr,
    _coerce_operator_datetime,
    _format_decimal,
    _load_course_user_contact_map,
    _load_operator_course_outline_items,
    _load_operator_user_last_login_map,
    _resolve_course_user_learning_status,
    _resolve_course_user_role,
    _resolve_visible_leaf_outline_bids,
)


def _load_course_related_user_bids(
    shifu_bid: str,
    *,
    creator_user_bid: str,
) -> tuple[Set[str], Set[str]]:
    order_user_bids = {
        str(user_bid or "").strip()
        for (user_bid,) in db.session.query(Order.user_bid)
        .filter(
            Order.shifu_bid == shifu_bid,
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
            Order.user_bid != "",
        )
        .all()
        if str(user_bid or "").strip()
    }
    permission_user_bids = {
        str(user_bid or "").strip()
        for (user_bid,) in db.session.query(AiCourseAuth.user_id)
        .filter(
            AiCourseAuth.course_id == shifu_bid,
            AiCourseAuth.status == 1,
            AiCourseAuth.user_id != "",
        )
        .all()
        if str(user_bid or "").strip()
    }
    learning_user_bids = {
        str(user_bid or "").strip()
        for (user_bid,) in db.session.query(LearnProgressRecord.user_bid)
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.user_bid != "",
        )
        .distinct()
        .all()
        if str(user_bid or "").strip()
    }

    learner_user_bids = order_user_bids | permission_user_bids | learning_user_bids
    related_user_bids = set(learner_user_bids)
    normalized_creator_user_bid = str(creator_user_bid or "").strip()
    if normalized_creator_user_bid:
        related_user_bids.add(normalized_creator_user_bid)
    return related_user_bids, learner_user_bids


def _load_course_user_paid_amount_map(
    shifu_bid: str,
    user_bids: Sequence[str],
) -> Dict[str, Decimal]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_user_bids:
        return {}

    counted_order_amount_expr = _build_course_order_amount_expr()
    rows = (
        db.session.query(
            Order.user_bid,
            db.func.coalesce(db.func.sum(counted_order_amount_expr), 0).label(
                "total_paid_amount"
            ),
        )
        .filter(
            Order.shifu_bid == shifu_bid,
            Order.user_bid.in_(normalized_user_bids),
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
        )
        .group_by(Order.user_bid)
        .all()
    )
    return {
        str(user_bid or "").strip(): Decimal(str(total_paid_amount or 0))
        for user_bid, total_paid_amount in rows
        if str(user_bid or "").strip()
    }


def _load_course_user_last_learning_map(
    shifu_bid: str,
    user_bids: Sequence[str],
) -> Dict[str, datetime]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_user_bids:
        return {}

    rows = (
        db.session.query(
            LearnProgressRecord.user_bid,
            db.func.max(LearnProgressRecord.updated_at).label("last_learning_at"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.user_bid.in_(normalized_user_bids),
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .group_by(LearnProgressRecord.user_bid)
        .all()
    )
    return {
        str(user_bid or "").strip(): last_learning_at
        for user_bid, last_learning_at in rows
        if str(user_bid or "").strip() and last_learning_at
    }


def _load_course_user_joined_at_map(
    shifu_bid: str,
    user_bids: Sequence[str],
    *,
    creator_user_bid: str,
    course_created_at: Optional[datetime],
) -> Dict[str, datetime]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_user_bids:
        return {}

    joined_at_map: Dict[str, datetime] = {}

    def _merge_rows(rows: Sequence[tuple[str, Any]]) -> None:
        for user_bid, joined_at in rows:
            normalized_user_bid = str(user_bid or "").strip()
            normalized_joined_at = _coerce_operator_datetime(joined_at)
            if not normalized_user_bid or normalized_joined_at is None:
                continue
            current = joined_at_map.get(normalized_user_bid)
            if current is None or normalized_joined_at < current:
                joined_at_map[normalized_user_bid] = normalized_joined_at

    _merge_rows(
        db.session.query(
            Order.user_bid,
            db.func.min(Order.created_at).label("joined_at"),
        )
        .filter(
            Order.shifu_bid == shifu_bid,
            Order.user_bid.in_(normalized_user_bids),
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
        )
        .group_by(Order.user_bid)
        .all()
    )
    _merge_rows(
        db.session.query(
            AiCourseAuth.user_id,
            db.func.min(
                db.func.coalesce(AiCourseAuth.updated_at, AiCourseAuth.created_at)
            ).label("joined_at"),
        )
        .filter(
            AiCourseAuth.course_id == shifu_bid,
            AiCourseAuth.user_id.in_(normalized_user_bids),
            AiCourseAuth.status == 1,
        )
        .group_by(AiCourseAuth.user_id)
        .all()
    )
    _merge_rows(
        db.session.query(
            LearnProgressRecord.user_bid,
            db.func.min(LearnProgressRecord.created_at).label("joined_at"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.user_bid.in_(normalized_user_bids),
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .group_by(LearnProgressRecord.user_bid)
        .all()
    )

    normalized_creator_user_bid = str(creator_user_bid or "").strip()
    normalized_course_created_at = _coerce_operator_datetime(course_created_at)
    if normalized_creator_user_bid and normalized_course_created_at:
        current = joined_at_map.get(normalized_creator_user_bid)
        if current is None or normalized_course_created_at < current:
            joined_at_map[normalized_creator_user_bid] = normalized_course_created_at

    return joined_at_map


def _load_course_user_learned_lesson_count_map(
    shifu_bid: str,
    user_bids: Sequence[str],
    leaf_outline_bids: Sequence[str],
) -> Dict[str, int]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    normalized_leaf_outline_bids = [
        str(outline_item_bid or "").strip()
        for outline_item_bid in leaf_outline_bids
        if str(outline_item_bid or "").strip()
    ]
    if not normalized_user_bids or not normalized_leaf_outline_bids:
        return {}

    rows = (
        db.session.query(
            LearnProgressRecord.user_bid,
            db.func.count(db.func.distinct(LearnProgressRecord.outline_item_bid)).label(
                "learned_lesson_count"
            ),
        )
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.user_bid.in_(normalized_user_bids),
            LearnProgressRecord.outline_item_bid.in_(normalized_leaf_outline_bids),
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .group_by(LearnProgressRecord.user_bid)
        .all()
    )
    return {
        str(user_bid or "").strip(): int(learned_lesson_count or 0)
        for user_bid, learned_lesson_count in rows
        if str(user_bid or "").strip()
    }


def get_operator_course_users(
    app: Flask,
    *,
    shifu_bid: str,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
) -> PageNationDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            COURSE_USER_LIST_MAX_PAGE_SIZE,
        )
        filters = filters or {}

        detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        course = detail_source["course"]
        creator_user_bid = str(course.created_user_bid or "").strip()
        related_user_bids, learner_user_bids = _load_course_related_user_bids(
            normalized_shifu_bid,
            creator_user_bid=creator_user_bid,
        )
        if not related_user_bids:
            return PageNationDTO(safe_page_index, safe_page_size, 0, [])

        ordered_user_bids = sorted(related_user_bids)
        users = (
            UserEntity.query.filter(
                UserEntity.user_bid.in_(ordered_user_bids),
                UserEntity.deleted == 0,
            )
            .order_by(UserEntity.created_at.desc(), UserEntity.id.desc())
            .all()
        )
        if not users:
            return PageNationDTO(safe_page_index, safe_page_size, 0, [])

        user_bids = [
            str(user.user_bid or "").strip() for user in users if user.user_bid
        ]
        contact_map = _load_course_user_contact_map(user_bids)
        last_login_map = _load_operator_user_last_login_map(user_bids)
        paid_amount_map = _load_course_user_paid_amount_map(
            normalized_shifu_bid, user_bids
        )
        last_learning_map = _load_course_user_last_learning_map(
            normalized_shifu_bid, user_bids
        )
        joined_at_map = _load_course_user_joined_at_map(
            normalized_shifu_bid,
            user_bids,
            creator_user_bid=creator_user_bid,
            course_created_at=getattr(course, "created_at", None),
        )
        visible_leaf_outline_bids = _resolve_visible_leaf_outline_bids(outline_items)
        total_lesson_count = len(visible_leaf_outline_bids)
        learned_lesson_count_map = _load_course_user_learned_lesson_count_map(
            normalized_shifu_bid,
            user_bids,
            visible_leaf_outline_bids,
        )

        keyword = str(filters.get("keyword", "") or "").strip().lower()
        user_role_filter = str(filters.get("user_role", "") or "").strip().lower()
        learning_status_filter = (
            str(filters.get("learning_status", "") or "").strip().lower()
        )
        payment_status_filter = (
            str(filters.get("payment_status", "") or "").strip().lower()
        )

        items_with_sort_keys: list[
            tuple[
                tuple[datetime, datetime, datetime, datetime, str],
                AdminOperationCourseUserDTO,
            ]
        ] = []
        for user in users:
            user_bid = str(user.user_bid or "").strip()
            if not user_bid:
                continue
            contact = contact_map.get(user_bid, {})
            learned_lesson_count = int(learned_lesson_count_map.get(user_bid, 0) or 0)
            learning_status = _resolve_course_user_learning_status(
                learned_lesson_count=learned_lesson_count,
                total_lesson_count=total_lesson_count,
            )
            total_paid_amount = paid_amount_map.get(user_bid)
            is_paid = bool(total_paid_amount and total_paid_amount > 0)
            user_role = _resolve_course_user_role(
                is_creator=bool(user.is_creator),
                is_operator=bool(user.is_operator),
                is_student=user_bid in learner_user_bids,
            )

            if keyword:
                haystack = [
                    user_bid.lower(),
                    str(contact.get("mobile", "") or "").lower(),
                    str(contact.get("email", "") or "").lower(),
                    str(user.nickname or "").lower(),
                ]
                if not any(keyword in value for value in haystack if value):
                    continue

            if (
                user_role_filter
                and user_role_filter != "all"
                and user_role != user_role_filter
            ):
                continue
            if (
                learning_status_filter
                and learning_status_filter != "all"
                and learning_status != learning_status_filter
            ):
                continue
            if payment_status_filter == "paid" and not is_paid:
                continue
            if payment_status_filter == "unpaid" and is_paid:
                continue

            last_learning_at = last_learning_map.get(user_bid)
            joined_at = joined_at_map.get(user_bid)
            last_login_at = last_login_map.get(user_bid)
            dto = AdminOperationCourseUserDTO(
                user_bid=user_bid,
                mobile=str(contact.get("mobile", "") or ""),
                email=str(contact.get("email", "") or ""),
                nickname=user.nickname or "",
                user_role=user_role,
                learned_lesson_count=learned_lesson_count,
                total_lesson_count=total_lesson_count,
                learning_status=learning_status,
                is_paid=is_paid,
                total_paid_amount=_format_decimal(total_paid_amount),
                last_learning_at=last_learning_at,
                joined_at=joined_at,
                last_login_at=last_login_at,
            )
            items_with_sort_keys.append(
                (
                    (
                        last_learning_at or datetime.min,
                        joined_at or datetime.min,
                        last_login_at or datetime.min,
                        getattr(user, "created_at", None) or datetime.min,
                        user_bid,
                    ),
                    dto,
                )
            )

        items_with_sort_keys.sort(key=lambda item: item[0], reverse=True)
        items = [item for _, item in items_with_sort_keys]
        total = len(items)
        start = (safe_page_index - 1) * safe_page_size
        end = start + safe_page_size
        paged_items = items[start:end]
        return PageNationDTO(safe_page_index, safe_page_size, total, paged_items)

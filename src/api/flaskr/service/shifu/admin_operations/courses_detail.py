"""Operator course detail, prompt, and chapter detail views.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, Optional, Sequence
from flask import Flask
from flaskr.common.umami_client import get_course_visit_count_30d
from flaskr.dao import db
from flaskr.service.learn.const import (
    LEARN_STATUS_RESET,
    ROLE_STUDENT,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnLessonFeedback,
    LearnProgressRecord,
)
from flaskr.service.common.models import (
    raise_error,
    raise_param_error,
)
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu.admin_dtos_courses import (
    AdminOperationCourseChapterDetailDTO,
    AdminOperationCourseDetailBasicInfoDTO,
    AdminOperationCourseDetailChapterDTO,
    AdminOperationCourseDetailDTO,
    AdminOperationCourseDetailMetricsDTO,
    AdminOperationCoursePromptDTO,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDASK_VALUE,
    UNIT_TYPE_VALUE_GUEST,
    UNIT_TYPE_VALUE_NORMAL,
    UNIT_TYPE_VALUE_TRIAL,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    PublishedOutlineItem,
)

from flaskr.service.shifu.admin_operations.courses_credit_usage import (
    _build_operator_course_credit_metrics,
)
from flaskr.service.shifu.admin_operations.courses_shared import (
    PROMPT_SOURCE_CHAPTER,
    PROMPT_SOURCE_COURSE,
    PROMPT_SOURCE_LESSON,
    _build_course_order_amount_expr,
    _format_average_score,
    _format_decimal,
    _get_legacy_admin_symbol,
    _load_operator_course_detail_source,
    _load_operator_course_outline_items,
    _load_user_map,
    _resolve_visible_leaf_outline_bids,
)


def _resolve_learning_permission(item_type: Optional[int]) -> str:
    if item_type == UNIT_TYPE_VALUE_GUEST:
        return "guest"
    if item_type == UNIT_TYPE_VALUE_TRIAL:
        return "free"
    if item_type == UNIT_TYPE_VALUE_NORMAL:
        return "paid"
    return "unknown"


def _resolve_content_status(item) -> str:
    if str(getattr(item, "content", "") or "").strip():
        return "has"
    return "empty"


def _resolve_outline_prompt_source(item) -> str:
    parent_bid = str(getattr(item, "parent_bid", "") or "").strip()
    if parent_bid:
        return PROMPT_SOURCE_LESSON
    return PROMPT_SOURCE_CHAPTER


def _resolve_prompt_with_fallback(
    *,
    outline_item,
    outline_item_map: Dict[str, DraftOutlineItem | PublishedOutlineItem],
    course,
    field_name: str,
) -> tuple[str, str]:
    current_item = outline_item
    visited_bids: set[str] = set()

    while current_item is not None:
        prompt_value = str(getattr(current_item, field_name, "") or "").strip()
        if prompt_value:
            return prompt_value, _resolve_outline_prompt_source(current_item)

        parent_bid = str(getattr(current_item, "parent_bid", "") or "").strip()
        if not parent_bid or parent_bid in visited_bids:
            break
        visited_bids.add(parent_bid)
        current_item = outline_item_map.get(parent_bid)

    course_prompt_value = str(getattr(course, field_name, "") or "").strip()
    if course_prompt_value:
        return course_prompt_value, PROMPT_SOURCE_COURSE

    return "", ""


def _build_chapter_tree(
    items,
    user_map: Dict[str, Dict[str, str]],
    *,
    follow_up_count_map: Dict[str, int],
    rating_count_map: Dict[str, int],
    rating_score_map: Dict[str, str],
) -> list[AdminOperationCourseDetailChapterDTO]:
    node_map: Dict[str, AdminOperationCourseDetailChapterDTO] = {}
    ordered_nodes: list[AdminOperationCourseDetailChapterDTO] = []
    for item in items:
        bid = str(item.outline_item_bid or "").strip()
        if not bid:
            continue
        modifier_user_bid = str(getattr(item, "updated_user_bid", "") or "").strip()
        modifier = user_map.get(modifier_user_bid, {})
        node = AdminOperationCourseDetailChapterDTO(
            outline_item_bid=bid,
            title=item.title or "",
            parent_bid=item.parent_bid or "",
            position=item.position or "",
            node_type="chapter" if not (item.parent_bid or "").strip() else "lesson",
            learning_permission=_resolve_learning_permission(
                getattr(item, "type", None)
            ),
            is_visible=not bool(getattr(item, "hidden", 0)),
            content_status=_resolve_content_status(item),
            follow_up_count=int(follow_up_count_map.get(bid, 0) or 0),
            rating_score=rating_score_map.get(bid, ""),
            rating_count=int(rating_count_map.get(bid, 0) or 0),
            modifier_user_bid=modifier_user_bid,
            modifier_mobile=modifier.get("mobile", ""),
            modifier_email=modifier.get("email", ""),
            modifier_nickname=modifier.get("nickname", ""),
            updated_at=item.updated_at,
            children=[],
        )
        node_map[bid] = node
        ordered_nodes.append(node)

    roots: list[AdminOperationCourseDetailChapterDTO] = []
    for node in ordered_nodes:
        parent_bid = node.parent_bid.strip()
        parent = node_map.get(parent_bid) if parent_bid else None
        if parent is None:
            roots.append(node)
            continue
        parent.children.append(node)

    def _rollup_learning_stats(
        node: AdminOperationCourseDetailChapterDTO,
    ) -> tuple[int, int]:
        follow_up_count = int(node.follow_up_count or 0)
        rating_count = int(node.rating_count or 0)
        for child in node.children:
            child_follow_up_count, child_rating_count = _rollup_learning_stats(child)
            follow_up_count += child_follow_up_count
            rating_count += child_rating_count
        node.follow_up_count = follow_up_count
        node.rating_count = rating_count
        return follow_up_count, rating_count

    for root in roots:
        _rollup_learning_stats(root)
    return roots


def _load_outline_learning_stats(
    shifu_bid: str,
    outline_item_bids: Sequence[str],
) -> tuple[Dict[str, int], Dict[str, int], Dict[str, str]]:
    normalized_outline_item_bids = [
        str(outline_item_bid or "").strip()
        for outline_item_bid in outline_item_bids
        if str(outline_item_bid or "").strip()
    ]
    if not normalized_outline_item_bids:
        return {}, {}, {}

    follow_up_rows = (
        db.session.query(
            LearnGeneratedBlock.outline_item_bid,
            db.func.count(LearnGeneratedBlock.id),
        )
        .filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.role == ROLE_STUDENT,
            LearnGeneratedBlock.outline_item_bid.in_(normalized_outline_item_bids),
        )
        .group_by(LearnGeneratedBlock.outline_item_bid)
        .all()
    )
    follow_up_count_map = {
        str(outline_item_bid or "").strip(): int(count or 0)
        for outline_item_bid, count in follow_up_rows
        if str(outline_item_bid or "").strip()
    }

    rating_rows = (
        db.session.query(
            LearnLessonFeedback.outline_item_bid,
            db.func.count(LearnLessonFeedback.id),
            db.func.avg(LearnLessonFeedback.score),
        )
        .filter(
            LearnLessonFeedback.shifu_bid == shifu_bid,
            LearnLessonFeedback.deleted == 0,
            LearnLessonFeedback.outline_item_bid.in_(normalized_outline_item_bids),
        )
        .group_by(LearnLessonFeedback.outline_item_bid)
        .all()
    )
    rating_count_map: Dict[str, int] = {}
    rating_score_map: Dict[str, str] = {}
    for outline_item_bid, count, score in rating_rows:
        normalized_outline_item_bid = str(outline_item_bid or "").strip()
        if not normalized_outline_item_bid:
            continue
        rating_count_map[normalized_outline_item_bid] = int(count or 0)
        rating_score_map[normalized_outline_item_bid] = _format_average_score(score)

    return follow_up_count_map, rating_count_map, rating_score_map


def get_operator_course_detail(
    app: Flask,
    *,
    shifu_bid: str,
) -> AdminOperationCourseDetailDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        course = detail_source["course"]
        course_status = detail_source["course_status"]

        creator_user_bid = str(course.created_user_bid or "").strip()
        visit_count_30d = _get_legacy_admin_symbol(
            "get_course_visit_count_30d", get_course_visit_count_30d
        )(app, normalized_shifu_bid)
        learner_count = (
            db.session.query(db.func.count(db.distinct(LearnProgressRecord.user_bid)))
            .filter(
                LearnProgressRecord.shifu_bid == normalized_shifu_bid,
                LearnProgressRecord.deleted == 0,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
            )
            .scalar()
            or 0
        )
        order_amount_expr = _build_course_order_amount_expr()
        order_summary = (
            db.session.query(
                db.func.count(Order.id).label("order_count"),
                db.func.coalesce(db.func.sum(order_amount_expr), 0).label(
                    "order_amount"
                ),
            )
            .filter(
                Order.shifu_bid == normalized_shifu_bid,
                Order.deleted == 0,
                Order.status == ORDER_STATUS_SUCCESS,
            )
            .first()
        )
        follow_up_count = (
            db.session.query(db.func.count(LearnGeneratedBlock.id))
            .filter(
                LearnGeneratedBlock.shifu_bid == normalized_shifu_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
                LearnGeneratedBlock.role == ROLE_STUDENT,
            )
            .scalar()
            or 0
        )
        rating_score = (
            db.session.query(db.func.avg(LearnLessonFeedback.score))
            .filter(
                LearnLessonFeedback.shifu_bid == normalized_shifu_bid,
                LearnLessonFeedback.deleted == 0,
            )
            .scalar()
        )
        detail_user_bids = {
            user_bid
            for user_bid in [creator_user_bid]
            + [
                str(getattr(item, "updated_user_bid", "") or "")
                for item in outline_items
            ]
            if str(user_bid or "").strip()
        }
        detail_user_map = _load_user_map(sorted(detail_user_bids))
        creator = detail_user_map.get(creator_user_bid, {})
        outline_learning_stats = _load_outline_learning_stats(
            normalized_shifu_bid,
            [
                str(getattr(item, "outline_item_bid", "") or "")
                for item in outline_items
            ],
        )
        follow_up_count_map, rating_count_map, rating_score_map = outline_learning_stats
        visible_leaf_outline_bids = _resolve_visible_leaf_outline_bids(outline_items)
        credit_metrics = _build_operator_course_credit_metrics(
            normalized_shifu_bid,
            visible_leaf_outline_bids,
        )

        return AdminOperationCourseDetailDTO(
            basic_info=AdminOperationCourseDetailBasicInfoDTO(
                shifu_bid=normalized_shifu_bid,
                course_name=course.title or "",
                course_status=course_status,
                creator_user_bid=creator_user_bid,
                creator_mobile=creator.get("mobile", ""),
                creator_email=creator.get("email", ""),
                creator_nickname=creator.get("nickname", ""),
                created_at=course.created_at,
                updated_at=course.updated_at,
            ),
            metrics=AdminOperationCourseDetailMetricsDTO(
                visit_count_30d=int(visit_count_30d),
                learner_count=int(learner_count),
                order_count=int(getattr(order_summary, "order_count", 0) or 0),
                order_amount=_format_decimal(
                    Decimal(str(getattr(order_summary, "order_amount", 0) or 0))
                ),
                follow_up_count=int(follow_up_count),
                rating_score=_format_average_score(rating_score),
                credit_consumed_total=credit_metrics["credit_consumed_total"],
                credit_usage_count=credit_metrics["credit_usage_count"],
                credit_user_count=credit_metrics["credit_user_count"],
                completed_credit_user_count=credit_metrics[
                    "completed_credit_user_count"
                ],
                completed_user_avg_credits=credit_metrics["completed_user_avg_credits"],
            ),
            chapters=_build_chapter_tree(
                outline_items,
                detail_user_map,
                follow_up_count_map=follow_up_count_map,
                rating_count_map=rating_count_map,
                rating_score_map=rating_score_map,
            ),
        )


def get_operator_course_prompt(
    app: Flask,
    *,
    shifu_bid: str,
) -> AdminOperationCoursePromptDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        detail_source = _load_operator_course_detail_source(normalized_shifu_bid)
        if detail_source is None:
            raise_error("server.shifu.shifuNotFound")

        course = detail_source["course"]
        return AdminOperationCoursePromptDTO(
            course_prompt=str(getattr(course, "llm_system_prompt", "") or "").strip()
        )


def get_operator_course_chapter_detail(
    app: Flask,
    *,
    shifu_bid: str,
    outline_item_bid: str,
) -> AdminOperationCourseChapterDetailDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_outline_item_bid = str(outline_item_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")
        if not normalized_outline_item_bid:
            raise_param_error("outline_item_bid is required")

        detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        course = detail_source["course"]
        outline_item_map = {
            str(item.outline_item_bid or "").strip(): item
            for item in outline_items
            if str(item.outline_item_bid or "").strip()
        }
        outline_item = outline_item_map.get(normalized_outline_item_bid)
        if outline_item is None:
            raise_error("server.shifu.outlineItemNotFound")

        llm_system_prompt, llm_system_prompt_source = _resolve_prompt_with_fallback(
            outline_item=outline_item,
            outline_item_map=outline_item_map,
            course=course,
            field_name="llm_system_prompt",
        )
        return AdminOperationCourseChapterDetailDTO(
            outline_item_bid=normalized_outline_item_bid,
            title=outline_item.title or "",
            content=getattr(outline_item, "content", "") or "",
            llm_system_prompt=llm_system_prompt,
            llm_system_prompt_source=llm_system_prompt_source,
        )

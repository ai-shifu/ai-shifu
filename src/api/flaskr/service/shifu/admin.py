from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, Iterable, Optional, Sequence, Set

from flask import Flask
from sqlalchemy import or_

from flaskr.dao import db
from flaskr.service.common.dtos import PageNationDTO
from flaskr.service.shifu.admin_dtos import AdminOperationCourseSummaryDTO
from flaskr.service.shifu.demo_courses import is_builtin_demo_course
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity


def _format_decimal(value: Optional[Decimal]) -> str:
    if value is None:
        return "0"
    if isinstance(value, str):
        normalized = value
    else:
        normalized = "{0:.2f}".format(value)
    if normalized.endswith(".00"):
        return normalized[:-3]
    return normalized


def _format_datetime(value: Optional[datetime]) -> str:
    if not value:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _normalize_identifier(value: str) -> str:
    normalized = str(value or "").strip()
    if "@" in normalized:
        return normalized.lower()
    return normalized


def _load_user_map(user_bids: Sequence[str]) -> Dict[str, Dict[str, str]]:
    if not user_bids:
        return {}

    credentials = (
        AuthCredential.query.filter(
            AuthCredential.user_bid.in_(list(user_bids)),
            AuthCredential.provider_name.in_(["phone", "email"]),
            AuthCredential.deleted == 0,
        )
        .order_by(AuthCredential.id.desc())
        .all()
    )
    phone_map: Dict[str, str] = {}
    email_map: Dict[str, str] = {}
    for credential in credentials:
        user_bid = credential.user_bid or ""
        if not user_bid:
            continue
        if credential.provider_name == "phone" and user_bid not in phone_map:
            phone_map[user_bid] = credential.identifier or ""
        if credential.provider_name == "email" and user_bid not in email_map:
            email_map[user_bid] = credential.identifier or ""

    users = (
        UserEntity.query.filter(
            UserEntity.user_bid.in_(list(user_bids)),
            UserEntity.deleted == 0,
        )
        .order_by(UserEntity.id.asc())
        .all()
    )
    user_map: Dict[str, Dict[str, str]] = {}
    for user in users:
        mobile = phone_map.get(user.user_bid, "")
        email = email_map.get(user.user_bid, "")
        identify = user.user_identify or ""
        if not mobile and identify.isdigit():
            mobile = identify
        if not email and "@" in identify:
            email = identify
        user_map[user.user_bid] = {
            "mobile": mobile or "",
            "email": email or "",
            "identify": identify,
            "nickname": user.nickname or "",
        }
    return user_map


def _find_matching_creator_bids(keyword: str) -> Optional[Set[str]]:
    normalized = _normalize_identifier(keyword)
    if not normalized:
        return None

    user_bids = {
        row[0]
        for row in db.session.query(UserEntity.user_bid)
        .filter(
            UserEntity.deleted == 0,
            or_(
                UserEntity.user_bid == normalized,
                UserEntity.user_identify == normalized,
            ),
        )
        .all()
        if row and row[0]
    }

    credential_rows = (
        db.session.query(AuthCredential.user_bid)
        .filter(
            AuthCredential.deleted == 0,
            AuthCredential.provider_name.in_(["phone", "email"]),
            AuthCredential.identifier == normalized,
        )
        .all()
    )
    for row in credential_rows:
        if row and row[0]:
            user_bids.add(row[0])

    return user_bids


def _load_latest_shifus(
    model,
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: Optional[Set[str]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    updated_start_time: Optional[datetime],
    updated_end_time: Optional[datetime],
):
    latest_subquery = db.session.query(db.func.max(model.id).label("max_id")).filter(
        model.deleted == 0
    )
    if shifu_bid:
        latest_subquery = latest_subquery.filter(model.shifu_bid == shifu_bid)
    if course_name:
        latest_subquery = latest_subquery.filter(model.title.ilike(f"%{course_name}%"))
    if creator_bids is not None:
        if not creator_bids:
            return []
        latest_subquery = latest_subquery.filter(
            model.created_user_bid.in_(creator_bids)
        )
    if start_time:
        latest_subquery = latest_subquery.filter(model.created_at >= start_time)
    if end_time:
        latest_subquery = latest_subquery.filter(model.created_at <= end_time)
    if updated_start_time:
        latest_subquery = latest_subquery.filter(model.updated_at >= updated_start_time)
    if updated_end_time:
        latest_subquery = latest_subquery.filter(model.updated_at <= updated_end_time)

    latest_subquery = latest_subquery.group_by(model.shifu_bid).subquery()
    return (
        db.session.query(model)
        .filter(model.id.in_(db.session.query(latest_subquery.c.max_id)))
        .order_by(model.updated_at.desc(), model.id.desc())
        .all()
    )


def _build_course_summary(
    course,
    user_map: Dict[str, Dict[str, str]],
) -> AdminOperationCourseSummaryDTO:
    creator = user_map.get(course.created_user_bid or "", {})
    updater = user_map.get(course.updated_user_bid or "", {})
    return AdminOperationCourseSummaryDTO(
        shifu_bid=course.shifu_bid or "",
        course_name=course.title or "",
        price=_format_decimal(course.price),
        creator_user_bid=course.created_user_bid or "",
        creator_mobile=creator.get("mobile", ""),
        creator_email=creator.get("email", ""),
        creator_nickname=creator.get("nickname", ""),
        updater_user_bid=course.updated_user_bid or "",
        updater_mobile=updater.get("mobile", ""),
        updater_email=updater.get("email", ""),
        updater_nickname=updater.get("nickname", ""),
        created_at=_format_datetime(course.created_at),
        updated_at=_format_datetime(course.updated_at),
    )


def _merge_courses(
    drafts: Iterable[DraftShifu],
    published: Iterable[PublishedShifu],
):
    course_map = {}
    for course in drafts:
        if course.shifu_bid and not is_builtin_demo_course(
            shifu_bid=course.shifu_bid,
            title=course.title,
            created_user_bid=course.created_user_bid,
        ):
            course_map[course.shifu_bid] = course
    for course in published:
        if (
            course.shifu_bid
            and not is_builtin_demo_course(
                shifu_bid=course.shifu_bid,
                title=course.title,
                created_user_bid=course.created_user_bid,
            )
            and course.shifu_bid not in course_map
        ):
            course_map[course.shifu_bid] = course
    return sorted(
        course_map.values(),
        key=lambda item: (
            item.updated_at or datetime.min,
            item.created_at or datetime.min,
            item.shifu_bid or "",
        ),
        reverse=True,
    )


def list_operator_courses(
    app: Flask,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
) -> PageNationDTO:
    with app.app_context():
        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = max(int(page_size or 20), 1)
        filters = filters or {}

        shifu_bid = str(filters.get("shifu_bid", "") or "").strip()
        course_name = str(filters.get("course_name", "") or "").strip()
        creator_keyword = str(filters.get("creator_keyword", "") or "").strip()
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")
        updated_start_time = filters.get("updated_start_time")
        updated_end_time = filters.get("updated_end_time")

        creator_bids = _find_matching_creator_bids(creator_keyword)
        draft_rows = _load_latest_shifus(
            DraftShifu,
            shifu_bid=shifu_bid,
            course_name=course_name,
            creator_bids=creator_bids,
            start_time=start_time,
            end_time=end_time,
            updated_start_time=updated_start_time,
            updated_end_time=updated_end_time,
        )
        published_rows = _load_latest_shifus(
            PublishedShifu,
            shifu_bid=shifu_bid,
            course_name=course_name,
            creator_bids=creator_bids,
            start_time=start_time,
            end_time=end_time,
            updated_start_time=updated_start_time,
            updated_end_time=updated_end_time,
        )

        merged_courses = _merge_courses(draft_rows, published_rows)
        total = len(merged_courses)
        page_offset = (safe_page_index - 1) * safe_page_size
        page_items = merged_courses[page_offset : page_offset + safe_page_size]

        user_bids = {
            user_bid
            for course in page_items
            for user_bid in [course.created_user_bid, course.updated_user_bid]
            if user_bid
        }
        user_map = _load_user_map(list(user_bids))
        items = [_build_course_summary(course, user_map) for course in page_items]
        return PageNationDTO(safe_page_index, safe_page_size, total, items)

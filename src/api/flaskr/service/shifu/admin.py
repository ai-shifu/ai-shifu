from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional, Sequence, Set

from flask import Flask
from sqlalchemy import and_, or_

from flaskr.common.cache_provider import cache as redis
from flaskr.common.config import get_config
from flaskr.dao import db
from flaskr.service.common.dtos import PageNationDTO
from flaskr.service.common.models import raise_error
from flaskr.service.shifu.admin_dtos import AdminOperationCourseSummaryDTO
from flaskr.service.shifu.demo_courses import is_builtin_demo_course
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.user.consts import USER_STATE_REGISTERED, USER_STATE_UNREGISTERED
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
from flaskr.service.user.repository import (
    ensure_user_for_identifier,
    load_user_aggregate_by_identifier,
    mark_user_roles,
    set_user_state,
    upsert_credential,
)
from flaskr.service.user.utils import (
    ensure_demo_course_permissions,
    load_existing_demo_shifu_ids,
)

COURSE_STATUS_PUBLISHED = "published"
COURSE_STATUS_UNPUBLISHED = "unpublished"


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
    latest_subquery = latest_subquery.group_by(model.shifu_bid).subquery()
    latest_rows = db.session.query(model).filter(
        model.id.in_(db.session.query(latest_subquery.c.max_id))
    )
    if course_name:
        latest_rows = latest_rows.filter(model.title.ilike(f"%{course_name}%"))
    if creator_bids is not None:
        if not creator_bids:
            return []
        latest_rows = latest_rows.filter(model.created_user_bid.in_(creator_bids))
    if start_time:
        latest_rows = latest_rows.filter(model.created_at >= start_time)
    if end_time:
        latest_rows = latest_rows.filter(model.created_at <= end_time)
    if updated_start_time:
        latest_rows = latest_rows.filter(model.updated_at >= updated_start_time)
    if updated_end_time:
        latest_rows = latest_rows.filter(model.updated_at <= updated_end_time)

    return latest_rows.order_by(model.updated_at.desc(), model.id.desc()).all()


def _build_course_summary(
    course,
    user_map: Dict[str, Dict[str, str]],
    course_status: str,
    activity: Optional[Dict[str, Any]] = None,
) -> AdminOperationCourseSummaryDTO:
    resolved_activity = activity or {}
    creator = user_map.get(course.created_user_bid or "", {})
    updater_user_bid = str(
        resolved_activity.get("updated_user_bid") or course.updated_user_bid or ""
    ).strip()
    updater = user_map.get(updater_user_bid, {})
    updated_at = resolved_activity.get("updated_at") or course.updated_at
    return AdminOperationCourseSummaryDTO(
        shifu_bid=course.shifu_bid or "",
        course_name=course.title or "",
        course_status=course_status,
        price=_format_decimal(course.price),
        creator_user_bid=course.created_user_bid or "",
        creator_mobile=creator.get("mobile", ""),
        creator_email=creator.get("email", ""),
        creator_nickname=creator.get("nickname", ""),
        updater_user_bid=updater_user_bid,
        updater_mobile=updater.get("mobile", ""),
        updater_email=updater.get("email", ""),
        updater_nickname=updater.get("nickname", ""),
        created_at=_format_datetime(course.created_at),
        updated_at=_format_datetime(updated_at),
    )


def _is_operator_visible_course(course) -> bool:
    return bool(course.shifu_bid) and not is_builtin_demo_course(
        shifu_bid=course.shifu_bid,
        title=course.title,
        created_user_bid=course.created_user_bid,
    )


def _resolve_course_status(shifu_bid: str, published_bids: Set[str]) -> str:
    if shifu_bid in published_bids:
        return COURSE_STATUS_PUBLISHED
    return COURSE_STATUS_UNPUBLISHED


def _record_course_activity(
    activity_map: Dict[str, Dict[str, Any]],
    *,
    shifu_bid: str,
    updated_at: Optional[datetime],
    updated_user_bid: str,
    prefer_on_equal: bool = False,
) -> None:
    if not shifu_bid:
        return
    current = activity_map.get(shifu_bid)
    candidate_time = updated_at or datetime.min
    current_time = (
        current.get("updated_at")
        if current and current.get("updated_at")
        else datetime.min
    )
    should_replace = current is None or candidate_time > current_time
    if (
        not should_replace
        and prefer_on_equal
        and current is not None
        and candidate_time == current_time
    ):
        should_replace = True
    if should_replace:
        activity_map[shifu_bid] = {
            "updated_at": updated_at,
            "updated_user_bid": str(updated_user_bid or "").strip(),
        }


def _load_course_activity_map(
    drafts: Iterable[DraftShifu],
    published: Iterable[PublishedShifu],
) -> Dict[str, Dict[str, Any]]:
    activity_map: Dict[str, Dict[str, Any]] = {}
    shifu_bids: Set[str] = set()

    for course in list(drafts) + list(published):
        shifu_bid = str(course.shifu_bid or "").strip()
        if not shifu_bid:
            continue
        shifu_bids.add(shifu_bid)
        _record_course_activity(
            activity_map,
            shifu_bid=shifu_bid,
            updated_at=course.updated_at,
            updated_user_bid=course.updated_user_bid or "",
        )

    if not shifu_bids:
        return activity_map

    ordered_shifu_bids = sorted(shifu_bids)
    outline_models = [DraftOutlineItem, PublishedOutlineItem]
    for model in outline_models:
        latest_updated_subquery = (
            db.session.query(
                model.shifu_bid.label("shifu_bid"),
                db.func.max(model.updated_at).label("max_updated_at"),
            )
            .filter(
                model.deleted == 0,
                model.shifu_bid.in_(ordered_shifu_bids),
            )
            .group_by(model.shifu_bid)
            .subquery()
        )
        latest_id_subquery = (
            db.session.query(
                model.shifu_bid.label("shifu_bid"),
                db.func.max(model.id).label("max_id"),
            )
            .join(
                latest_updated_subquery,
                and_(
                    model.shifu_bid == latest_updated_subquery.c.shifu_bid,
                    or_(
                        model.updated_at == latest_updated_subquery.c.max_updated_at,
                        and_(
                            model.updated_at.is_(None),
                            latest_updated_subquery.c.max_updated_at.is_(None),
                        ),
                    ),
                ),
            )
            .filter(
                model.deleted == 0,
                model.shifu_bid.in_(ordered_shifu_bids),
            )
            .group_by(model.shifu_bid)
            .subquery()
        )
        rows = (
            db.session.query(
                model.shifu_bid,
                model.updated_at,
                model.updated_user_bid,
            )
            .join(latest_id_subquery, model.id == latest_id_subquery.c.max_id)
            .all()
        )
        for shifu_bid, updated_at, updated_user_bid in rows:
            normalized_shifu_bid = str(shifu_bid or "").strip()
            if not normalized_shifu_bid:
                continue
            _record_course_activity(
                activity_map,
                shifu_bid=normalized_shifu_bid,
                updated_at=updated_at,
                updated_user_bid=updated_user_bid or "",
                prefer_on_equal=True,
            )

    return activity_map


def _load_latest_course_for_transfer(shifu_bid: str):
    draft = (
        DraftShifu.query.filter(
            DraftShifu.shifu_bid == shifu_bid,
            DraftShifu.deleted == 0,
        )
        .order_by(DraftShifu.id.desc())
        .first()
    )
    if draft:
        return draft

    return (
        PublishedShifu.query.filter(
            PublishedShifu.shifu_bid == shifu_bid,
            PublishedShifu.deleted == 0,
        )
        .order_by(PublishedShifu.id.desc())
        .first()
    )


def _clear_shifu_permission_cache(app: Flask, user_id: str, shifu_bid: str) -> None:
    prefixes = {
        app.config.get("CACHE_KEY_PREFIX", "") or "",
        get_config("REDIS_KEY_PREFIX") or "",
    }
    for prefix in prefixes:
        cache_key = f"{prefix}shifu_permission:{user_id}:{shifu_bid}"
        redis.delete(cache_key)


def _clear_shifu_creator_cache(app: Flask, shifu_bid: str) -> None:
    prefixes = {
        app.config.get("REDIS_KEY_PREFIX", "") or "",
        get_config("REDIS_KEY_PREFIX") or "",
        "ai-shifu",
    }
    for prefix in prefixes:
        cache_key = f"{prefix}:shifu_creator:{shifu_bid}"
        redis.delete(cache_key)


def _update_course_creator_bid(shifu_bid: str, creator_user_bid: str) -> None:
    DraftShifu.query.filter(DraftShifu.shifu_bid == shifu_bid).update(
        {DraftShifu.created_user_bid: creator_user_bid},
        synchronize_session=False,
    )
    PublishedShifu.query.filter(PublishedShifu.shifu_bid == shifu_bid).update(
        {PublishedShifu.created_user_bid: creator_user_bid},
        synchronize_session=False,
    )


def transfer_operator_course_creator(
    app: Flask,
    *,
    shifu_bid: str,
    contact_type: str,
    identifier: str,
) -> Dict[str, Any]:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_contact_type = str(contact_type or "").strip().lower()
        normalized_identifier = _normalize_identifier(identifier)

        latest_course = _load_latest_course_for_transfer(normalized_shifu_bid)
        if not latest_course:
            raise_error("server.shifu.shifuNotFound")
        if not _is_operator_visible_course(latest_course):
            raise_error("server.shifu.transferCreatorDemoNotAllowed")

        previous_creator_user_bid = str(latest_course.created_user_bid or "").strip()

        existing_aggregate = load_user_aggregate_by_identifier(
            normalized_identifier,
            providers=[normalized_contact_type],
        )
        created_new_user = False
        granted_demo_permissions = False
        if existing_aggregate is None:
            target_aggregate, created_new_user = ensure_user_for_identifier(
                app,
                provider=normalized_contact_type,
                identifier=normalized_identifier,
                defaults={
                    "identify": normalized_identifier,
                    "nickname": "",
                    "state": USER_STATE_REGISTERED,
                },
            )
        else:
            target_aggregate = existing_aggregate

        target_user_bid = str(target_aggregate.user_bid or "").strip()
        if not target_user_bid:
            raise_error("server.shifu.transferCreatorTargetNotFound")
        if target_user_bid == previous_creator_user_bid:
            raise_error("server.shifu.transferCreatorSameUser")

        should_grant_demo_permissions = created_new_user
        if (
            existing_aggregate is not None
            and existing_aggregate.state == USER_STATE_UNREGISTERED
        ):
            set_user_state(target_user_bid, USER_STATE_REGISTERED)
            should_grant_demo_permissions = True

        upsert_credential(
            app,
            user_bid=target_user_bid,
            provider_name=normalized_contact_type,
            subject_id=normalized_identifier,
            subject_format=normalized_contact_type,
            identifier=normalized_identifier,
            metadata={},
            verified=True,
        )

        if should_grant_demo_permissions:
            demo_shifu_ids = load_existing_demo_shifu_ids()
            if demo_shifu_ids:
                ensure_demo_course_permissions(
                    app,
                    target_user_bid,
                    demo_ids=demo_shifu_ids,
                )
                granted_demo_permissions = True

        mark_user_roles(target_user_bid, is_creator=True)
        _update_course_creator_bid(normalized_shifu_bid, target_user_bid)

        db.session.commit()
        if previous_creator_user_bid:
            _clear_shifu_permission_cache(
                app, previous_creator_user_bid, normalized_shifu_bid
            )
        _clear_shifu_permission_cache(app, target_user_bid, normalized_shifu_bid)
        _clear_shifu_creator_cache(app, normalized_shifu_bid)
        return {
            "shifu_bid": normalized_shifu_bid,
            "previous_creator_user_bid": previous_creator_user_bid,
            "target_creator_user_bid": target_user_bid,
            "created_new_user": created_new_user,
            "granted_demo_permissions": granted_demo_permissions,
        }


def _merge_courses(
    drafts: Iterable[DraftShifu],
    published: Iterable[PublishedShifu],
):
    course_map = {}
    published_bids: Set[str] = set()
    for course in drafts:
        visible = _is_operator_visible_course(course)
        if visible:
            course_map[course.shifu_bid] = course
    for course in published:
        visible = _is_operator_visible_course(course)
        if visible:
            published_bids.add(course.shifu_bid)
        if visible and course.shifu_bid not in course_map:
            course_map[course.shifu_bid] = course
    return (
        sorted(
            course_map.values(),
            key=lambda item: (
                item.updated_at or datetime.min,
                item.created_at or datetime.min,
                item.shifu_bid or "",
            ),
            reverse=True,
        ),
        published_bids,
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
        course_status = str(filters.get("course_status", "") or "").strip().lower()
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
            updated_start_time=None,
            updated_end_time=None,
        )
        published_rows = _load_latest_shifus(
            PublishedShifu,
            shifu_bid=shifu_bid,
            course_name=course_name,
            creator_bids=creator_bids,
            start_time=start_time,
            end_time=end_time,
            updated_start_time=None,
            updated_end_time=None,
        )

        merged_courses, published_bids = _merge_courses(draft_rows, published_rows)
        activity_map = _load_course_activity_map(draft_rows, published_rows)

        def resolve_activity(course) -> Dict[str, Any]:
            return activity_map.get(str(course.shifu_bid or "").strip(), {})

        def resolve_updated_at(course) -> Optional[datetime]:
            activity = resolve_activity(course)
            return activity.get("updated_at") or course.updated_at

        if course_status in {COURSE_STATUS_PUBLISHED, COURSE_STATUS_UNPUBLISHED}:
            merged_courses = [
                course
                for course in merged_courses
                if _resolve_course_status(course.shifu_bid or "", published_bids)
                == course_status
            ]
        if updated_start_time:
            merged_courses = [
                course
                for course in merged_courses
                if (resolve_updated_at(course) or datetime.min) >= updated_start_time
            ]
        if updated_end_time:
            merged_courses = [
                course
                for course in merged_courses
                if (resolve_updated_at(course) or datetime.min) <= updated_end_time
            ]
        merged_courses = sorted(
            merged_courses,
            key=lambda item: (
                resolve_updated_at(item) or datetime.min,
                item.created_at or datetime.min,
                item.shifu_bid or "",
            ),
            reverse=True,
        )
        total = len(merged_courses)
        page_offset = (safe_page_index - 1) * safe_page_size
        page_items = merged_courses[page_offset : page_offset + safe_page_size]

        user_bids = {
            user_bid
            for course in page_items
            for user_bid in [
                course.created_user_bid,
                (
                    resolve_activity(course).get("updated_user_bid")
                    or course.updated_user_bid
                ),
            ]
            if user_bid and user_bid != "system"
        }
        user_map = _load_user_map(list(user_bids))
        items = [
            _build_course_summary(
                course,
                user_map,
                _resolve_course_status(course.shifu_bid or "", published_bids),
                resolve_activity(course),
            )
            for course in page_items
        ]
        return PageNationDTO(safe_page_index, safe_page_size, total, items)

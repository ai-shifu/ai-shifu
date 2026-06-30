from __future__ import annotations

from typing import Optional

from flask import Flask
from sqlalchemy import and_, case

from flaskr.dao import db
from flaskr.service.common.models import raise_param_error
from flaskr.service.shifu.admin_dtos import (
    AdminOperationUserListDTO,
    AdminOperationUserOverviewDTO,
    AdminOperationUserSummaryDTO,
)
from flaskr.service.shifu.admin_operations.user_support import (
    OPERATOR_USER_LIST_MAX_PAGE_SIZE,
    OPERATOR_USER_QUICK_FILTER_CREATED_LAST_30D,
    OPERATOR_USER_QUICK_FILTER_CREATOR,
    OPERATOR_USER_QUICK_FILTER_GUEST,
    OPERATOR_USER_QUICK_FILTER_LEARNER,
    OPERATOR_USER_QUICK_FILTER_LEARNING_ACTIVE_30D,
    OPERATOR_USER_QUICK_FILTER_PAID,
    OPERATOR_USER_QUICK_FILTER_PAID_LAST_30D,
    OPERATOR_USER_QUICK_FILTER_REGISTERED,
    OPERATOR_USER_QUICK_FILTER_REGISTERED_LAST_30D,
    OPERATOR_USER_ROLE_CREATOR,
    OPERATOR_USER_ROLE_LEARNER,
    OPERATOR_USER_ROLE_OPERATOR,
    OPERATOR_USER_ROLE_REGULAR,
    OPERATOR_USER_STATUS_PAID,
    OPERATOR_USER_STATUS_REGISTERED,
    OPERATOR_USER_STATUS_TRIAL,
    OPERATOR_USER_STATUS_UNREGISTERED,
    build_learner_user_bid_subquery,
    build_operator_user_summary,
    build_recent_learning_active_user_bid_subquery,
    build_recent_paid_user_bid_subquery,
    build_registered_user_timestamp_subquery,
    find_matching_user_bids_by_identifier,
    load_learner_user_bids,
    load_operator_user_auth_credentials,
    load_operator_user_contact_map,
    load_operator_user_course_count_maps,
    load_operator_user_course_maps,
    load_operator_user_credit_summary_map,
    load_operator_user_last_learning_map,
    load_operator_user_last_login_map,
    load_operator_user_or_raise,
    load_operator_user_registration_source_map,
    load_operator_user_total_paid_amount_map,
    resolve_operator_user_quick_filter,
    resolve_recent_days_window,
)
from flaskr.service.user.consts import (
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import UserInfo as UserEntity


def _build_operator_user_overview() -> AdminOperationUserOverviewDTO:
    registered_states = [USER_STATE_REGISTERED, USER_STATE_TRAIL, USER_STATE_PAID]
    learner_subquery = build_learner_user_bid_subquery()
    registered_timestamp_subquery = build_registered_user_timestamp_subquery()
    recent_window_start, recent_window_end = resolve_recent_days_window(30)
    recent_learning_subquery = build_recent_learning_active_user_bid_subquery(
        since=recent_window_start,
        until=recent_window_end,
    )
    recent_paid_subquery = build_recent_paid_user_bid_subquery(
        since=recent_window_start,
        until=recent_window_end,
    )
    learner_user_count_subquery = (
        db.session.query(db.func.count(db.distinct(learner_subquery.c.user_bid)))
        .join(UserEntity, UserEntity.user_bid == learner_subquery.c.user_bid)
        .filter(UserEntity.deleted == 0)
        .scalar_subquery()
    )
    learning_active_30d_user_count_subquery = (
        db.session.query(
            db.func.count(db.distinct(recent_learning_subquery.c.user_bid))
        )
        .join(UserEntity, UserEntity.user_bid == recent_learning_subquery.c.user_bid)
        .filter(UserEntity.deleted == 0)
        .scalar_subquery()
    )
    registered_last_30d_user_count_subquery = (
        db.session.query(
            db.func.count(db.distinct(registered_timestamp_subquery.c.user_bid))
        )
        .filter(
            registered_timestamp_subquery.c.registered_at >= recent_window_start,
            registered_timestamp_subquery.c.registered_at <= recent_window_end,
        )
        .scalar_subquery()
    )
    paid_last_30d_user_count_subquery = (
        db.session.query(db.func.count(db.distinct(recent_paid_subquery.c.user_bid)))
        .join(UserEntity, UserEntity.user_bid == recent_paid_subquery.c.user_bid)
        .filter(UserEntity.deleted == 0)
        .scalar_subquery()
    )
    summary = (
        db.session.query(
            db.func.count(UserEntity.user_bid).label("total_user_count"),
            db.func.coalesce(
                db.func.sum(
                    case((UserEntity.state.in_(registered_states), 1), else_=0)
                ),
                0,
            ).label("registered_user_count"),
            db.func.coalesce(
                db.func.sum(case((UserEntity.is_creator == 1, 1), else_=0)),
                0,
            ).label("creator_user_count"),
            db.func.coalesce(learner_user_count_subquery, 0).label(
                "learner_user_count"
            ),
            db.func.coalesce(
                db.func.sum(case((UserEntity.state == USER_STATE_PAID, 1), else_=0)),
                0,
            ).label("paid_user_count"),
            db.func.coalesce(
                db.func.sum(
                    case(
                        (
                            and_(
                                UserEntity.created_at >= recent_window_start,
                                UserEntity.created_at <= recent_window_end,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("created_last_30d_user_count"),
            db.func.coalesce(registered_last_30d_user_count_subquery, 0).label(
                "registered_last_30d_user_count"
            ),
            db.func.coalesce(learning_active_30d_user_count_subquery, 0).label(
                "learning_active_30d_user_count"
            ),
            db.func.coalesce(paid_last_30d_user_count_subquery, 0).label(
                "paid_last_30d_user_count"
            ),
            db.func.coalesce(
                db.func.sum(
                    case((UserEntity.state == USER_STATE_UNREGISTERED, 1), else_=0)
                ),
                0,
            ).label("guest_user_count"),
        )
        .filter(UserEntity.deleted == 0)
        .one()
    )

    return AdminOperationUserOverviewDTO(
        total_user_count=int(summary.total_user_count or 0),
        registered_user_count=int(summary.registered_user_count or 0),
        creator_user_count=int(summary.creator_user_count or 0),
        learner_user_count=int(summary.learner_user_count or 0),
        paid_user_count=int(summary.paid_user_count or 0),
        created_last_30d_user_count=int(summary.created_last_30d_user_count or 0),
        registered_last_30d_user_count=int(summary.registered_last_30d_user_count or 0),
        learning_active_30d_user_count=int(summary.learning_active_30d_user_count or 0),
        paid_last_30d_user_count=int(summary.paid_last_30d_user_count or 0),
        guest_user_count=int(summary.guest_user_count or 0),
    )


def get_operator_user_overview(app: Flask) -> AdminOperationUserOverviewDTO:
    with app.app_context():
        return _build_operator_user_overview()


def list_operator_users(
    app: Flask,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
) -> AdminOperationUserListDTO:
    with app.app_context():
        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            OPERATOR_USER_LIST_MAX_PAGE_SIZE,
        )
        filters = filters or {}

        user_bid = str(filters.get("user_bid", "") or "").strip()
        identifier = str(
            filters.get("identifier", "") or filters.get("mobile", "") or ""
        ).strip()
        nickname = str(filters.get("nickname", "") or "").strip()
        user_status = str(filters.get("user_status", "") or "").strip().lower()
        user_role = str(filters.get("user_role", "") or "").strip().lower()
        quick_filter = resolve_operator_user_quick_filter(
            filters.get("quick_filter", "")
        )
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")

        query = UserEntity.query.filter(UserEntity.deleted == 0)
        if user_bid:
            query = query.filter(UserEntity.user_bid == user_bid)
        if nickname:
            query = query.filter(UserEntity.nickname.ilike(f"%{nickname}%"))
        if user_status:
            if user_status == OPERATOR_USER_STATUS_UNREGISTERED:
                query = query.filter(UserEntity.state == USER_STATE_UNREGISTERED)
            elif user_status == OPERATOR_USER_STATUS_REGISTERED:
                query = query.filter(
                    UserEntity.state.in_([USER_STATE_REGISTERED, USER_STATE_TRAIL])
                )
            elif user_status == OPERATOR_USER_STATUS_TRIAL:
                query = query.filter(UserEntity.state == USER_STATE_TRAIL)
            elif user_status == OPERATOR_USER_STATUS_PAID:
                query = query.filter(UserEntity.state == USER_STATE_PAID)
            else:
                raise_param_error("user_status")
        if user_role == OPERATOR_USER_ROLE_OPERATOR:
            query = query.filter(UserEntity.is_operator == 1)
        elif user_role == OPERATOR_USER_ROLE_CREATOR:
            query = query.filter(UserEntity.is_creator == 1)
        elif user_role == OPERATOR_USER_ROLE_LEARNER:
            learner_subquery = build_learner_user_bid_subquery()
            query = query.filter(
                UserEntity.is_operator == 0,
                UserEntity.is_creator == 0,
                UserEntity.user_bid.in_(db.session.query(learner_subquery.c.user_bid)),
            )
        elif user_role == OPERATOR_USER_ROLE_REGULAR:
            learner_subquery = build_learner_user_bid_subquery()
            query = query.filter(
                UserEntity.is_operator == 0,
                UserEntity.is_creator == 0,
                ~UserEntity.user_bid.in_(db.session.query(learner_subquery.c.user_bid)),
            )
        elif user_role:
            raise_param_error("user_role")
        if start_time:
            query = query.filter(UserEntity.created_at >= start_time)
        if end_time:
            query = query.filter(UserEntity.created_at <= end_time)
        if identifier:
            matching_user_bids = find_matching_user_bids_by_identifier(identifier)
            if not matching_user_bids:
                return AdminOperationUserListDTO(
                    safe_page_index,
                    safe_page_size,
                    0,
                    [],
                )
            query = query.filter(UserEntity.user_bid.in_(list(matching_user_bids)))
        if quick_filter:
            recent_window_start, recent_window_end = resolve_recent_days_window(30)
            if quick_filter == OPERATOR_USER_QUICK_FILTER_CREATOR:
                query = query.filter(UserEntity.is_creator == 1)
            elif quick_filter == OPERATOR_USER_QUICK_FILTER_LEARNER:
                learner_subquery = build_learner_user_bid_subquery()
                query = query.filter(
                    UserEntity.user_bid.in_(
                        db.session.query(learner_subquery.c.user_bid)
                    )
                )
            elif quick_filter == OPERATOR_USER_QUICK_FILTER_REGISTERED:
                query = query.filter(
                    UserEntity.state.in_(
                        [USER_STATE_REGISTERED, USER_STATE_TRAIL, USER_STATE_PAID]
                    )
                )
            elif quick_filter == OPERATOR_USER_QUICK_FILTER_PAID:
                query = query.filter(UserEntity.state == USER_STATE_PAID)
            elif quick_filter == OPERATOR_USER_QUICK_FILTER_CREATED_LAST_30D:
                query = query.filter(
                    UserEntity.created_at >= recent_window_start,
                    UserEntity.created_at <= recent_window_end,
                )
            elif quick_filter == OPERATOR_USER_QUICK_FILTER_REGISTERED_LAST_30D:
                registered_timestamp_subquery = (
                    build_registered_user_timestamp_subquery()
                )
                query = query.filter(
                    UserEntity.user_bid.in_(
                        db.session.query(
                            registered_timestamp_subquery.c.user_bid
                        ).filter(
                            registered_timestamp_subquery.c.registered_at
                            >= recent_window_start,
                            registered_timestamp_subquery.c.registered_at
                            <= recent_window_end,
                        )
                    )
                )
            elif quick_filter == OPERATOR_USER_QUICK_FILTER_LEARNING_ACTIVE_30D:
                recent_learning_subquery = (
                    build_recent_learning_active_user_bid_subquery(
                        since=recent_window_start,
                        until=recent_window_end,
                    )
                )
                query = query.filter(
                    UserEntity.user_bid.in_(
                        db.session.query(recent_learning_subquery.c.user_bid)
                    )
                )
            elif quick_filter == OPERATOR_USER_QUICK_FILTER_PAID_LAST_30D:
                recent_paid_subquery = build_recent_paid_user_bid_subquery(
                    since=recent_window_start,
                    until=recent_window_end,
                )
                query = query.filter(
                    UserEntity.user_bid.in_(
                        db.session.query(recent_paid_subquery.c.user_bid)
                    )
                )
            elif quick_filter == OPERATOR_USER_QUICK_FILTER_GUEST:
                query = query.filter(UserEntity.state == USER_STATE_UNREGISTERED)

        total = query.count()
        page_offset = (safe_page_index - 1) * safe_page_size
        page_items = (
            query.order_by(UserEntity.created_at.desc(), UserEntity.id.desc())
            .offset(page_offset)
            .limit(safe_page_size)
            .all()
        )
        user_bids = [
            str(user.user_bid or "").strip() for user in page_items if user.user_bid
        ]
        credential_rows = load_operator_user_auth_credentials(user_bids)
        contact_map = load_operator_user_contact_map(
            user_bids,
            users=page_items,
            credential_rows=credential_rows,
        )
        created_course_count_map, learning_course_count_map = (
            load_operator_user_course_count_maps(user_bids)
        )
        learner_user_bids = load_learner_user_bids(user_bids)
        registration_source_map = load_operator_user_registration_source_map(
            user_bids,
            users=page_items,
            credential_rows=credential_rows,
        )
        last_login_map = load_operator_user_last_login_map(user_bids)
        total_paid_amount_map = load_operator_user_total_paid_amount_map(user_bids)
        last_learning_map = load_operator_user_last_learning_map(user_bids)
        credit_summary_map = load_operator_user_credit_summary_map(user_bids)
        items = [
            build_operator_user_summary(
                user,
                contact_map,
                learner_user_bids,
                registration_source_map,
                last_login_map,
                total_paid_amount_map,
                last_learning_map,
                credit_summary_map,
                learning_course_count_map=learning_course_count_map,
                created_course_count_map=created_course_count_map,
            )
            for user in page_items
        ]
        return AdminOperationUserListDTO(
            safe_page_index,
            safe_page_size,
            total,
            items,
        )


def get_operator_user_detail(
    app: Flask,
    user_bid: str,
) -> AdminOperationUserSummaryDTO:
    with app.app_context():
        normalized_user_bid = str(user_bid or "").strip()
        user = load_operator_user_or_raise(normalized_user_bid)

        credential_rows = load_operator_user_auth_credentials([normalized_user_bid])
        contact_map = load_operator_user_contact_map(
            [normalized_user_bid],
            users=[user],
            credential_rows=credential_rows,
        )
        created_courses_map, learning_courses_map = load_operator_user_course_maps(
            [normalized_user_bid]
        )
        learner_user_bids = load_learner_user_bids([normalized_user_bid])
        registration_source_map = load_operator_user_registration_source_map(
            [normalized_user_bid],
            users=[user],
            credential_rows=credential_rows,
        )
        last_login_map = load_operator_user_last_login_map([normalized_user_bid])
        total_paid_amount_map = load_operator_user_total_paid_amount_map(
            [normalized_user_bid]
        )
        last_learning_map = load_operator_user_last_learning_map([normalized_user_bid])
        credit_summary_map = load_operator_user_credit_summary_map(
            [normalized_user_bid]
        )
        return build_operator_user_summary(
            user,
            contact_map,
            learner_user_bids,
            registration_source_map,
            last_login_map,
            total_paid_amount_map,
            last_learning_map,
            credit_summary_map,
            learning_courses_map=learning_courses_map,
            created_courses_map=created_courses_map,
        )

"""Record and query first-party visits to published courses."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.learn.models import LearnCourseVisitor
from flaskr.service.shifu.models import PublishedShifu
from flaskr.service.user.consts import (
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
)
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.util.datetime import now_utc
from sqlalchemy import case
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from flask import Flask


COURSE_VISIT_WINDOW = timedelta(days=30)
_REGISTERED_USER_STATES = (
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_PAID,
)


def _is_registered_user(user_bid: str) -> bool:
    registered_user = (
        db.session.query(UserEntity.id)
        .filter(
            UserEntity.user_bid == user_bid,
            UserEntity.state.in_(_REGISTERED_USER_STATES),
            UserEntity.deleted == 0,
        )
        .first()
    )
    return registered_user is not None


def _require_published_course(shifu_bid: str) -> None:
    published_course = (
        db.session.query(PublishedShifu.id)
        .filter(
            PublishedShifu.shifu_bid == shifu_bid,
            PublishedShifu.deleted == 0,
        )
        .first()
    )
    if published_course is None:
        raise_error("server.shifu.shifuNotFound")


def _build_supported_dialect_upsert(
    *,
    dialect_name: str,
    shifu_bid: str,
    user_bid: str,
    visited_at: datetime,
    recorded_at: datetime,
) -> object | None:
    table = LearnCourseVisitor.__table__
    values = {
        "shifu_bid": shifu_bid,
        "user_bid": user_bid,
        "first_visited_at": visited_at,
        "last_visited_at": visited_at,
        "created_at": recorded_at,
        "updated_at": recorded_at,
    }
    created_at = case(
        (table.c.created_at > recorded_at, recorded_at),
        else_=table.c.created_at,
    )
    updated_at = case(
        (table.c.updated_at < recorded_at, recorded_at),
        else_=table.c.updated_at,
    )
    first_visited_at = case(
        (table.c.first_visited_at > visited_at, visited_at),
        else_=table.c.first_visited_at,
    )
    last_visited_at = case(
        (table.c.last_visited_at < visited_at, visited_at),
        else_=table.c.last_visited_at,
    )

    if dialect_name == "mysql":
        statement = mysql_insert(table).values(**values)
        statement = statement.on_duplicate_key_update(
            created_at=created_at,
            first_visited_at=first_visited_at,
            last_visited_at=last_visited_at,
            updated_at=updated_at,
        )
    elif dialect_name == "sqlite":
        statement = sqlite_insert(table).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.shifu_bid, table.c.user_bid],
            set_={
                "created_at": created_at,
                "first_visited_at": first_visited_at,
                "last_visited_at": last_visited_at,
                "updated_at": updated_at,
            },
        )
    elif dialect_name == "postgresql":
        statement = postgresql_insert(table).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.shifu_bid, table.c.user_bid],
            set_={
                "created_at": created_at,
                "first_visited_at": first_visited_at,
                "last_visited_at": last_visited_at,
                "updated_at": updated_at,
            },
        )
    else:
        return None

    return statement


def _execute_supported_dialect_upsert(
    *,
    shifu_bid: str,
    user_bid: str,
    visited_at: datetime,
    recorded_at: datetime,
) -> bool:
    statement = _build_supported_dialect_upsert(
        dialect_name=db.session.get_bind().dialect.name,
        shifu_bid=shifu_bid,
        user_bid=user_bid,
        visited_at=visited_at,
        recorded_at=recorded_at,
    )
    if statement is None:
        return False

    db.session.execute(statement)
    return True


def _execute_fallback_upsert(
    *,
    shifu_bid: str,
    user_bid: str,
    visited_at: datetime,
    recorded_at: datetime,
) -> None:
    created_at = case(
        (LearnCourseVisitor.created_at > recorded_at, recorded_at),
        else_=LearnCourseVisitor.created_at,
    )
    updated_at = case(
        (LearnCourseVisitor.updated_at < recorded_at, recorded_at),
        else_=LearnCourseVisitor.updated_at,
    )
    first_visited_at = case(
        (LearnCourseVisitor.first_visited_at > visited_at, visited_at),
        else_=LearnCourseVisitor.first_visited_at,
    )
    last_visited_at = case(
        (LearnCourseVisitor.last_visited_at < visited_at, visited_at),
        else_=LearnCourseVisitor.last_visited_at,
    )
    query = LearnCourseVisitor.query.filter(
        LearnCourseVisitor.shifu_bid == shifu_bid,
        LearnCourseVisitor.user_bid == user_bid,
    )
    updated = query.update(
        {
            LearnCourseVisitor.created_at: created_at,
            LearnCourseVisitor.first_visited_at: first_visited_at,
            LearnCourseVisitor.last_visited_at: last_visited_at,
            LearnCourseVisitor.updated_at: updated_at,
        },
        synchronize_session=False,
    )
    if updated:
        return

    try:
        with db.session.begin_nested():
            db.session.add(
                LearnCourseVisitor(
                    shifu_bid=shifu_bid,
                    user_bid=user_bid,
                    first_visited_at=visited_at,
                    last_visited_at=visited_at,
                    created_at=recorded_at,
                    updated_at=recorded_at,
                )
            )
            db.session.flush()
    except IntegrityError:
        query.update(
            {
                LearnCourseVisitor.created_at: created_at,
                LearnCourseVisitor.first_visited_at: first_visited_at,
                LearnCourseVisitor.last_visited_at: last_visited_at,
                LearnCourseVisitor.updated_at: updated_at,
            },
            synchronize_session=False,
        )


def record_course_visit(
    app: Flask,
    *,
    shifu_bid: str,
    user_bid: str,
    visited_at: datetime | None = None,
) -> bool:
    """Record an eligible learner's latest visit to a published course."""
    with app_context_scope(app), unit_of_work():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_user_bid = str(user_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")
        if not normalized_user_bid:
            return False

        if not _is_registered_user(normalized_user_bid):
            return False
        _require_published_course(normalized_shifu_bid)
        recorded_at = now_utc()
        effective_visited_at = visited_at or recorded_at
        if not _execute_supported_dialect_upsert(
            shifu_bid=normalized_shifu_bid,
            user_bid=normalized_user_bid,
            visited_at=effective_visited_at,
            recorded_at=recorded_at,
        ):
            _execute_fallback_upsert(
                shifu_bid=normalized_shifu_bid,
                user_bid=normalized_user_bid,
                visited_at=effective_visited_at,
                recorded_at=recorded_at,
            )
        return True


def count_recent_course_visitors(
    shifu_bid: str,
    *,
    as_of: datetime | None = None,
) -> int:
    """Count distinct registered visitors in the exact trailing 30-day window."""
    normalized_shifu_bid = str(shifu_bid or "").strip()
    if not normalized_shifu_bid:
        return 0

    effective_as_of = as_of or now_utc()
    cutoff = effective_as_of - COURSE_VISIT_WINDOW
    return int(
        db.session.query(db.func.count(LearnCourseVisitor.id))
        .filter(
            LearnCourseVisitor.shifu_bid == normalized_shifu_bid,
            LearnCourseVisitor.last_visited_at >= cutoff,
            LearnCourseVisitor.last_visited_at <= effective_as_of,
        )
        .scalar()
        or 0
    )

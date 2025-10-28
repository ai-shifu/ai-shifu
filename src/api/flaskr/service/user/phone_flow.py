"""Phone verification workflow utilities."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, Tuple

from flask import Flask

from flaskr.dao import db
from flaskr.dao import redis_client as redis
from sqlalchemy import text
from flaskr.service.common.dtos import UserToken
from flaskr.service.common.models import raise_error
from flaskr.service.order.consts import LEARN_STATUS_RESET
from flaskr.service.profile.funcs import (
    get_user_profile_labels,
    update_user_profile_with_lable,
)
from flaskr.service.shifu.models import PublishedShifu
from flaskr.service.user.consts import USER_STATE_REGISTERED, USER_STATE_UNREGISTERED
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.utils import generate_token
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    build_user_profile_snapshot_from_aggregate,
    ensure_user_for_identifier,
    get_user_entity_by_bid,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    mark_user_roles,
    update_user_entity_fields,
    upsert_credential,
    upsert_wechat_credentials,
    transactional_session,
)

FIX_CHECK_CODE = None


def configure_fix_check_code(value: Optional[str]) -> None:
    global FIX_CHECK_CODE
    FIX_CHECK_CODE = value


def migrate_user_study_record(
    app: Flask, from_user_id: str, to_user_id: str, course_id: Optional[str] = None
) -> None:
    from flaskr.service.learn.models import LearnProgressRecord

    app.logger.info(
        "migrate_user_study_record from_user_id:%s to_user_id:%s",
        from_user_id,
        to_user_id,
    )
    from_attends = LearnProgressRecord.query.filter(
        LearnProgressRecord.user_bid == from_user_id,
        LearnProgressRecord.status != LEARN_STATUS_RESET,
        LearnProgressRecord.shifu_bid == course_id,
    ).all()
    to_attends = LearnProgressRecord.query.filter(
        LearnProgressRecord.user_bid == to_user_id,
        LearnProgressRecord.status != LEARN_STATUS_RESET,
        LearnProgressRecord.shifu_bid == course_id,
    ).all()
    migrate_attends = []
    for from_attend in from_attends:
        to_attend = [
            attend
            for attend in to_attends
            if attend.outline_item_bid == from_attend.outline_item_bid
        ]
        if to_attend:
            continue
        migrate_attends.append(from_attend)

    if not migrate_attends:
        return

    db.session.execute(
        text(
            "update learn_progress_records set user_bid = '%s' where id in (%s)"
            % (to_user_id, ",".join(str(attend.id) for attend in migrate_attends))
        )
    )
    db.session.execute(
        text(
            "update learn_generated_blocks set user_bid = '%s' where progress_record_bid in (%s)"
            % (
                to_user_id,
                ",".join(
                    "'" + str(attend.progress_record_bid) + "'"
                    for attend in migrate_attends
                ),
            )
        )
    )
    db.session.flush()


def init_first_course(app: Flask, user_id: str) -> None:
    user_count = UserEntity.query.filter(
        UserEntity.state != USER_STATE_UNREGISTERED
    ).count()
    if user_count != 1:
        return

    course_count = PublishedShifu.query.filter(PublishedShifu.deleted == 0).count()
    if course_count != 1:
        return

    mark_user_roles(user_id, is_admin=True, is_creator=True)

    course = (
        PublishedShifu.query.filter(PublishedShifu.deleted == 0)
        .order_by(PublishedShifu.id.asc())
        .first()
    )
    if course:
        course.created_user_id = user_id
    db.session.flush()


def verify_phone_code(
    app: Flask,
    user_id: Optional[str],
    phone: str,
    code: str,
    course_id: Optional[str] = None,
    language: Optional[str] = None,
) -> Tuple[UserToken, bool, Dict[str, Optional[str]]]:
    if FIX_CHECK_CODE is None:
        configure_fix_check_code(app.config.get("UNIVERSAL_VERIFICATION_CODE"))

    check_save = redis.get(app.config["REDIS_KEY_PREFIX_PHONE_CODE"] + phone)
    if check_save is None and code != FIX_CHECK_CODE:
        raise_error("server.user.smsSendExpired")

    check_save_str = str(check_save, encoding="utf-8") if check_save else ""
    if code != check_save_str and code != FIX_CHECK_CODE:
        raise_error("server.user.smsCheckError")

    redis.delete(app.config["REDIS_KEY_PREFIX_PHONE_CODE"] + phone)

    created_new_user = False
    normalized_phone = phone.strip()

    with transactional_session():
        target_aggregate = load_user_aggregate_by_identifier(
            normalized_phone, providers=["phone"]
        )
        origin_aggregate = load_user_aggregate(user_id) if user_id else None

        if not target_aggregate and origin_aggregate:
            target_aggregate = origin_aggregate

        if (
            target_aggregate
            and user_id
            and target_aggregate.user_bid != user_id
            and course_id is not None
        ):
            new_profiles = get_user_profile_labels(app, user_id, course_id)
            update_user_profile_with_lable(
                app, target_aggregate.user_bid, new_profiles, False, course_id
            )
            migrate_user_study_record(
                app,
                origin_aggregate.user_bid if origin_aggregate else user_id,
                target_aggregate.user_bid,
                course_id,
            )
            if (
                origin_aggregate
                and origin_aggregate.wechat_open_id
                and not target_aggregate.wechat_open_id
            ):
                upsert_wechat_credentials(
                    app,
                    user_bid=target_aggregate.user_bid,
                    open_id=origin_aggregate.wechat_open_id,
                    union_id=origin_aggregate.wechat_union_id,
                    verified=True,
                )

        if target_aggregate is None:
            defaults = {
                "user_bid": user_id or uuid.uuid4().hex,
                "nickname": normalized_phone or user_id,
                "language": language,
                "state": USER_STATE_REGISTERED,
            }
            target_aggregate, created_new_user = ensure_user_for_identifier(
                app,
                provider="phone",
                identifier=normalized_phone,
                defaults=defaults,
            )
            init_first_course(app, target_aggregate.user_bid)
        else:
            entity = get_user_entity_by_bid(
                target_aggregate.user_bid, include_deleted=True
            )
            if entity:
                updates: Dict[str, Any] = {"identify": normalized_phone}
                if target_aggregate.state == USER_STATE_UNREGISTERED:
                    updates["state"] = USER_STATE_REGISTERED
                if language:
                    updates["language"] = language
                update_user_entity_fields(entity, **updates)

        upsert_credential(
            app,
            user_bid=target_aggregate.user_bid,
            provider_name="phone",
            subject_id=normalized_phone,
            subject_format="phone",
            identifier=normalized_phone,
            metadata={"course_id": course_id, "language": language},
            verified=True,
        )

        refreshed = load_user_aggregate(target_aggregate.user_bid)
        if not refreshed:
            raise_error("USER.USER_NOT_FOUND")
        token = generate_token(app, user_id=refreshed.user_bid)
        user_dto = build_user_info_from_aggregate(refreshed)
        snapshot = build_user_profile_snapshot_from_aggregate(refreshed)

    return (
        UserToken(userInfo=user_dto, token=token),
        created_new_user,
        {
            "course_id": course_id,
            "language": language,
            "snapshot": snapshot.to_dict(),
        },
    )

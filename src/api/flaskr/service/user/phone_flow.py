"""Phone verification workflow utilities."""

from __future__ import annotations

import uuid
from typing import Dict, Optional, Tuple

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
from flaskr.service.user.consts import (
    USER_STATE_REGISTERED,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import User
from flaskr.service.user.utils import generate_token
from flaskr.service.user.repository import (
    build_user_info_dto,
    build_user_profile_snapshot,
    list_credentials,
    sync_user_entity_for_legacy,
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
    user_count = User.query.filter(User.user_state != USER_STATE_UNREGISTERED).count()
    if user_count != 1:
        return

    course_count = PublishedShifu.query.filter(PublishedShifu.deleted == 0).count()
    if course_count != 1:
        return

    first_user = User.query.filter(User.user_id == user_id).first()
    if first_user:
        first_user.is_admin = True
        first_user.is_creator = True

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
        raise_error("module.backend.user.smsSendExpired")

    check_save_str = str(check_save, encoding="utf-8") if check_save else ""
    if code != check_save_str and code != FIX_CHECK_CODE:
        raise_error("module.backend.user.smsCheckError")

    redis.delete(app.config["REDIS_KEY_PREFIX_PHONE_CODE"] + phone)

    user_info = (
        User.query.filter(User.mobile == phone)
        .order_by(User.user_state.desc())
        .order_by(User.id.asc())
        .first()
    )

    created_new_user = False

    with transactional_session():
        if not user_info and user_id:
            user_info = (
                User.query.filter(User.user_id == user_id)
                .order_by(User.id.asc())
                .first()
            )

        if (
            user_info
            and user_id
            and user_id != user_info.user_id
            and course_id is not None
        ):
            new_profiles = get_user_profile_labels(app, user_id, course_id)
            update_user_profile_with_lable(
                app, user_info.user_id, new_profiles, False, course_id
            )
            origin_user = User.query.filter(User.user_id == user_id).first()
            migrate_user_study_record(
                app,
                origin_user.user_id if origin_user else user_id,
                user_info.user_id,
                course_id,
            )
            if (
                origin_user
                and origin_user.user_open_id != user_info.user_open_id
                and (not user_info.user_open_id)
            ):
                user_info.user_open_id = origin_user.user_open_id

        if user_info is None:
            generated_user_id = uuid.uuid4().hex
            user_info = User(
                user_id=generated_user_id,
                username="",
                name="",
                email="",
                mobile=phone,
            )
            user_info.user_state = USER_STATE_REGISTERED
            if language:
                user_info.user_language = language
            db.session.add(user_info)
            init_first_course(app, user_info.user_id)
            created_new_user = True
        else:
            if user_info.user_state == USER_STATE_UNREGISTERED:
                user_info.user_state = USER_STATE_REGISTERED
            user_info.mobile = phone
            if language:
                user_info.user_language = language

        token = generate_token(app, user_id=user_info.user_id)
        db.session.flush()

        user_entity = sync_user_entity_for_legacy(app, user_info)
        if user_entity:
            # On phone verification, persist the phone as the user's identifier
            user_entity.user_identify = phone
        db.session.flush()
        user_dto = build_user_info_dto(user_info)
        snapshot = build_user_profile_snapshot(
            user_info, credentials=list_credentials(user_bid=user_info.user_id)
        )

    return (
        UserToken(userInfo=user_dto, token=token),
        created_new_user,
        {
            "course_id": course_id,
            "language": language,
            "snapshot": snapshot.to_dict(),
        },
    )

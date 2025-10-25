"""Email verification workflow utilities."""

from __future__ import annotations

import uuid
from typing import Dict, Optional, Tuple

from flask import Flask

from flaskr.dao import db
from flaskr.dao import redis_client as redis
from flaskr.service.common.dtos import UserToken
from flaskr.service.common.models import raise_error
from flaskr.service.profile.funcs import (
    get_user_profile_labels,
    update_user_profile_with_lable,
)
from flaskr.service.user.phone_flow import migrate_user_study_record, init_first_course
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


def verify_email_code(
    app: Flask,
    user_id: Optional[str],
    email: str,
    code: str,
    course_id: Optional[str] = None,
    language: Optional[str] = None,
) -> Tuple[UserToken, bool, Dict[str, Optional[str]]]:
    if FIX_CHECK_CODE is None:
        configure_fix_check_code(app.config.get("UNIVERSAL_VERIFICATION_CODE"))

    check_save = redis.get(app.config["REDIS_KEY_PREFIX_MAIL_CODE"] + email)
    if check_save is None and code != FIX_CHECK_CODE:
        raise_error("server.user.mailSendExpired")

    check_save_str = str(check_save, encoding="utf-8") if check_save else ""
    if code != check_save_str and code != FIX_CHECK_CODE:
        raise_error("server.user.mailCheckError")

    redis.delete(app.config["REDIS_KEY_PREFIX_MAIL_CODE"] + email)

    normalized_email = email.lower() if email else ""

    user_info = (
        User.query.filter(User.email == normalized_email)
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
            if origin_user:
                migrate_user_study_record(
                    app, origin_user.user_id, user_info.user_id, course_id
                )
                if (
                    origin_user.user_open_id
                    and origin_user.user_open_id != user_info.user_open_id
                    and not user_info.user_open_id
                ):
                    user_info.user_open_id = origin_user.user_open_id

        if user_info is None:
            generated_user_id = uuid.uuid4().hex
            user_info = User(
                user_id=generated_user_id,
                username="",
                name="",
                email=normalized_email,
                mobile="",
            )
            user_info.user_state = USER_STATE_REGISTERED
            user_info.user_language = language or user_info.user_language
            user_info.email = normalized_email
            db.session.add(user_info)
            init_first_course(app, user_info.user_id)
            created_new_user = True
        else:
            if user_info.user_state == USER_STATE_UNREGISTERED:
                user_info.user_state = USER_STATE_REGISTERED
            if language:
                user_info.user_language = language
            user_info.email = normalized_email

        token = generate_token(app, user_id=user_info.user_id)
        db.session.flush()

        user_entity = sync_user_entity_for_legacy(app, user_info)
        if user_entity:
            # On email verification, persist normalized email as identifier
            user_entity.user_identify = normalized_email
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

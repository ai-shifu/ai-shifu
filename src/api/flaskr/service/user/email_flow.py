"""Email verification workflow utilities."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, Tuple

from flask import Flask

from flaskr.dao import redis_client as redis
from flaskr.service.common.dtos import UserToken
from flaskr.service.common.models import raise_error
from flaskr.service.profile.funcs import (
    get_user_profile_labels,
    update_user_profile_with_lable,
)
from flaskr.service.user.phone_flow import migrate_user_study_record, init_first_course
from flaskr.service.user.consts import USER_STATE_REGISTERED, USER_STATE_UNREGISTERED
from flaskr.service.user.utils import generate_token
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    build_user_profile_snapshot_from_aggregate,
    ensure_user_for_identifier,
    get_user_entity_by_bid,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    update_user_entity_fields,
    upsert_wechat_credentials,
    upsert_credential,
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

    created_new_user = False

    with transactional_session():
        target_aggregate = load_user_aggregate_by_identifier(
            normalized_email, providers=["email"]
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
            if origin_aggregate:
                migrate_user_study_record(
                    app,
                    origin_aggregate.user_bid,
                    target_aggregate.user_bid,
                    course_id,
                )
                if (
                    origin_aggregate.wechat_open_id
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
                "nickname": normalized_email or user_id,
                "language": language,
                "state": USER_STATE_REGISTERED,
            }
            target_aggregate, created_new_user = ensure_user_for_identifier(
                app,
                provider="email",
                identifier=normalized_email,
                defaults=defaults,
            )
            init_first_course(app, target_aggregate.user_bid)
        else:
            entity = get_user_entity_by_bid(
                target_aggregate.user_bid, include_deleted=True
            )
            if entity:
                updates: Dict[str, Any] = {"identify": normalized_email}
                promote_state = target_aggregate.state in (
                    USER_STATE_UNREGISTERED,
                    0,
                )
                if promote_state:
                    updates["state"] = USER_STATE_REGISTERED
                if language:
                    updates["language"] = language
                entity = update_user_entity_fields(entity, **updates)
                if promote_state:
                    init_first_course(app, entity.user_bid)

        upsert_credential(
            app,
            user_bid=target_aggregate.user_bid,
            provider_name="email",
            subject_id=normalized_email,
            subject_format="email",
            identifier=normalized_email,
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

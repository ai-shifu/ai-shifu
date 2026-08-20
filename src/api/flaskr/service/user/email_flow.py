"""Email verification workflow utilities."""

from __future__ import annotations

import contextlib
import datetime
import uuid
from typing import Any

from flask import Flask
from flaskr.common.cache_provider import cache as redis
from flaskr.common.config import get_redis_derived_prefix
from flaskr.dao import db
from flaskr.service.common.dtos import UserToken
from flaskr.service.common.models import raise_error
from flaskr.service.profile.api import merge_learner_profile_for_sign_in
from flaskr.service.user.consts import USER_STATE_REGISTERED, USER_STATE_UNREGISTERED
from flaskr.service.user.models import UserVerifyCode
from flaskr.service.user.phone_flow import init_first_course, migrate_user_study_record
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    build_user_profile_snapshot_from_aggregate,
    ensure_user_for_identifier,
    get_user_entity_by_bid,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    transactional_session,
    update_user_entity_fields,
    upsert_credential,
    upsert_wechat_credentials,
)
from flaskr.service.user.utils import generate_token
from flaskr.util.datetime import now_utc

FIX_CHECK_CODE = None


def configure_fix_check_code(value: str | None) -> None:
    global FIX_CHECK_CODE
    FIX_CHECK_CODE = value


def _is_within_seconds(value: datetime.datetime, *, seconds: int) -> bool:
    if value is None:
        return False
    with contextlib.suppress(Exception):
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
    now = now_utc()
    return (now - value).total_seconds() <= seconds


def _consume_latest_email_code_from_db(app: Flask, email: str, code: str) -> str:
    """Consume the latest sent email verification code from the database.

    Returns:
      - "ok" when the code is valid and is marked as used.
      - "expired" when no valid code exists (missing/used/expired).
      - "invalid" when a code exists but does not match.

    """
    expire_seconds = int(app.config.get("MAIL_CODE_EXPIRE_TIME", 300))
    latest = (
        UserVerifyCode.query.filter(
            UserVerifyCode.mail == email,
            UserVerifyCode.verify_code_type == 2,
            UserVerifyCode.verify_code_send == 1,
        )
        .order_by(UserVerifyCode.created.desc(), UserVerifyCode.id.desc())
        .first()
    )
    if not latest or int(getattr(latest, "verify_code_used", 0) or 0) == 1:
        return "expired"
    created_at = getattr(latest, "created", None)
    if not created_at or not _is_within_seconds(created_at, seconds=expire_seconds):
        return "expired"
    if (latest.verify_code or "") != (code or ""):
        return "invalid"
    latest.verify_code_used = 1
    db.session.flush()
    return "ok"


def verify_email_code(
    app: Flask,
    user_id: str | None,
    email: str,
    code: str,
    course_id: str | None = None,
    language: str | None = None,
) -> tuple[UserToken, bool, dict[str, str | None]]:
    # Local import avoids circular dependency during module initialization.
    from flaskr.service.profile.funcs import (
        get_user_profile_labels,
        update_user_profile_with_lable,
    )

    if FIX_CHECK_CODE is None:
        configure_fix_check_code(app.config.get("UNIVERSAL_VERIFICATION_CODE"))

    email_key = (email or "").strip()
    code_key = (
        get_redis_derived_prefix("REDIS_KEY_PREFIX_MAIL_CODE", app=app) + email_key
    )
    if code != FIX_CHECK_CODE:
        cached = redis.get(code_key)
        if cached is not None:
            cached_str = (
                cached.decode("utf-8") if isinstance(cached, bytes) else str(cached)
            )
            if code != cached_str:
                raise_error("server.user.mailCheckError")
            _consume_latest_email_code_from_db(app, email_key, code)
        else:
            status = _consume_latest_email_code_from_db(app, email_key, code)
            if status != "ok" and email_key.lower() != email_key:
                status = _consume_latest_email_code_from_db(
                    app, email_key.lower(), code
                )
            if status == "invalid":
                raise_error("server.user.mailCheckError")
            if status != "ok":
                raise_error("server.user.mailSendExpired")

    redis.delete(code_key)

    normalized_email = email_key.lower() if email_key else ""

    created_new_user = False

    with transactional_session():
        target_aggregate = load_user_aggregate_by_identifier(
            normalized_email, providers=["email"]
        )
        origin_aggregate = load_user_aggregate(user_id) if user_id else None

        if not target_aggregate and origin_aggregate:
            target_aggregate = origin_aggregate

        if target_aggregate and user_id and target_aggregate.user_bid != user_id:
            include_legacy_nickname = merge_learner_profile_for_sign_in(
                source_user_id=user_id,
                target_user_id=target_aggregate.user_bid,
            )
            if course_id is not None:
                new_profiles = get_user_profile_labels(
                    app,
                    user_id,
                    course_id,
                    include_nickname=include_legacy_nickname,
                )
                update_user_profile_with_lable(
                    app, target_aggregate.user_bid, new_profiles, False, course_id
                )
            if origin_aggregate and course_id is not None:
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
                "nickname": "",
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
                updates: dict[str, Any] = {"identify": normalized_email}
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

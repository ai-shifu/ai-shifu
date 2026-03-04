"""Phone verification workflow utilities."""

from __future__ import annotations

import uuid
import datetime
from typing import Any, Dict, Optional, Tuple, Union

from flask import Flask

from flaskr.common.cache_provider import cache as redis
from flaskr.dao import db
from sqlalchemy import text
from flaskr.service.common.dtos import UserToken
from flaskr.service.common.models import raise_error
from flaskr.service.order.consts import LEARN_STATUS_RESET
from flaskr.service.shifu.models import PublishedShifu, DraftShifu
from flaskr.service.user.consts import (
    USER_STATE_REGISTERED,
    USER_STATE_UNREGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_PAID,
)
from flaskr.service.user.models import UserInfo as UserEntity, UserVerifyCode
from flaskr.service.user.utils import (
    generate_token,
    ensure_admin_creator_and_demo_permissions,
)
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


def _is_within_seconds(value: datetime.datetime, *, seconds: int) -> bool:
    if value is None:
        return False
    try:
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
    except Exception:
        pass
    now = datetime.datetime.utcnow()
    return (now - value).total_seconds() <= seconds


def _consume_latest_sms_code_from_db(app: Flask, phone: str, code: str) -> str:
    """
    Consume the latest sent SMS verification code from the database.

    Returns:
      - "ok" when the code is valid and is marked as used.
      - "expired" when no valid code exists (missing/used/expired).
      - "invalid" when a code exists but does not match.
    """
    expire_seconds = int(app.config.get("PHONE_CODE_EXPIRE_TIME", 300))
    latest = (
        UserVerifyCode.query.filter(
            UserVerifyCode.phone == phone,
            UserVerifyCode.verify_code_type == 1,
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
    # Ensure pending state changes are visible to subsequent queries
    db.session.flush()

    # Count users who are actually verified/registered or above.
    # Support both legacy (0..3) and new (1101..1104) state ranges.
    verified_states = [
        1,
        2,
        3,
        USER_STATE_REGISTERED,
        USER_STATE_TRAIL,
        USER_STATE_PAID,
    ]
    user_count = (
        UserEntity.query.filter(UserEntity.deleted == 0)
        .filter(UserEntity.state.in_(verified_states))
        .count()
    )
    if user_count != 1:
        db.session.flush()
        return

    # Always grant admin/creator to the first verified user
    mark_user_roles(user_id, is_creator=True)

    ShifuModel: Union[PublishedShifu, DraftShifu] = PublishedShifu
    # Assign demo shifu only when there is exactly one published course
    course_count = PublishedShifu.query.filter(PublishedShifu.deleted == 0).count()
    if course_count == 0:
        course_count = DraftShifu.query.filter(DraftShifu.deleted == 0).count()
        ShifuModel = DraftShifu
    if course_count != 1:
        db.session.flush()
        return

    course = (
        ShifuModel.query.filter(ShifuModel.deleted == 0)
        .order_by(ShifuModel.id.asc())
        .first()
    )
    if course:
        # Persist creator on the published record
        course.created_user_bid = user_id
        # Also persist creator on the corresponding draft (used by permission checks)
        draft = ShifuModel.query.filter(
            ShifuModel.shifu_bid == course.shifu_bid
        ).first()
        if draft:
            draft.created_user_bid = user_id
    db.session.flush()


def verify_phone_code(
    app: Flask,
    user_id: Optional[str],
    phone: str,
    code: str,
    course_id: Optional[str] = None,
    language: Optional[str] = None,
    login_context: Optional[str] = None,
) -> Tuple[UserToken, bool, Dict[str, Optional[str]]]:
    # Local import avoids circular dependency during module initialization.
    from flaskr.service.profile.funcs import (
        get_user_profile_labels,
        update_user_profile_with_lable,
    )

    code_key = app.config["REDIS_KEY_PREFIX_PHONE_CODE"] + phone
    cached = redis.get(code_key)
    if cached is not None:
        cached_str = (
            cached.decode("utf-8") if isinstance(cached, bytes) else str(cached)
        )
        if code != cached_str:
            raise_error("server.user.smsCheckError")
        _consume_latest_sms_code_from_db(app, phone, code)
    else:
        status = _consume_latest_sms_code_from_db(app, phone, code)
        if status == "invalid":
            raise_error("server.user.smsCheckError")
        if status != "ok":
            raise_error("server.user.smsSendExpired")

    redis.delete(code_key)

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
                "nickname": "",
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
            provider_name="phone",
            subject_id=normalized_phone,
            subject_format="phone",
            identifier=normalized_phone,
            metadata={"course_id": course_id, "language": language},
            verified=True,
        )

        # If configured, automatically grant creator and demo-course permissions
        ensure_admin_creator_and_demo_permissions(
            app, target_aggregate.user_bid, target_aggregate.language, login_context
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

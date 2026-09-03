"""Phone verification workflow utilities."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from flaskr.dao import db
from flaskr.service.common.dtos import UserToken
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.phone_numbers import normalize_phone_identifier
from flaskr.service.order.consts import LEARN_STATUS_RESET
from flaskr.service.profile.api import merge_learner_profile_for_sign_in
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.consts import (
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    build_user_profile_snapshot_from_aggregate,
    ensure_user_for_identifier,
    get_user_entity_by_bid,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    mark_user_roles,
    transactional_session,
    update_user_entity_fields,
    upsert_credential,
    upsert_wechat_credentials,
)
from flaskr.service.user.utils import (
    ensure_admin_creator_and_demo_permissions,
    generate_token,
)
from flaskr.service.user.verification_codes import consume_verification_code
from sqlalchemy import text

if TYPE_CHECKING:
    from flask import Flask

BOOTSTRAP_LOCK_NAME = "user_first_verified_bootstrap"


def _acquire_bootstrap_lock(app: Flask, timeout_seconds: int = 5) -> bool | None:
    bind = db.session.get_bind()
    dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
    if dialect_name != "mysql":
        return None

    lock_value = db.session.execute(
        text("SELECT GET_LOCK(:name, :timeout_seconds)"),
        {
            "name": BOOTSTRAP_LOCK_NAME,
            "timeout_seconds": timeout_seconds,
        },
    ).scalar()
    acquired = bool(lock_value)
    if not acquired:
        app.logger.warning(
            "init_first_course skip bootstrap: failed to acquire named lock %s",
            BOOTSTRAP_LOCK_NAME,
        )
    return acquired


def _release_bootstrap_lock() -> None:
    bind = db.session.get_bind()
    dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
    if dialect_name != "mysql":
        return
    db.session.execute(
        text("SELECT RELEASE_LOCK(:name)"),
        {"name": BOOTSTRAP_LOCK_NAME},
    )


def migrate_user_study_record(
    app: Flask, from_user_id: str, to_user_id: str, course_id: str | None = None
) -> None:
    """Migrate user study record."""
    from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord

    normalized_course_id = str(course_id or "").strip()
    if not normalized_course_id:
        app.logger.warning(
            "migrate_user_study_record skipped: missing course_id, from_user_id=%s, to_user_id=%s",
            from_user_id,
            to_user_id,
        )
        return

    app.logger.info(
        "migrate_user_study_record from_user_id:%s to_user_id:%s course_id:%s",
        from_user_id,
        to_user_id,
        normalized_course_id,
    )
    from_attends = LearnProgressRecord.query.filter(
        LearnProgressRecord.user_bid == from_user_id,
        LearnProgressRecord.status != LEARN_STATUS_RESET,
        LearnProgressRecord.shifu_bid == normalized_course_id,
    ).all()
    to_attends = LearnProgressRecord.query.filter(
        LearnProgressRecord.user_bid == to_user_id,
        LearnProgressRecord.status != LEARN_STATUS_RESET,
        LearnProgressRecord.shifu_bid == normalized_course_id,
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
        app.logger.info(
            "migrate_user_study_record no-op: from_records=%s to_records=%s course_id=%s",
            len(from_attends),
            len(to_attends),
            normalized_course_id,
        )
        return

    record_ids = [attend.id for attend in migrate_attends]
    progress_record_bids = [attend.progress_record_bid for attend in migrate_attends]
    db.session.query(LearnProgressRecord).filter(
        LearnProgressRecord.id.in_(record_ids)
    ).update({LearnProgressRecord.user_bid: to_user_id}, synchronize_session=False)
    db.session.query(LearnGeneratedBlock).filter(
        LearnGeneratedBlock.user_bid == from_user_id,
        LearnGeneratedBlock.progress_record_bid.in_(progress_record_bids),
    ).update({LearnGeneratedBlock.user_bid: to_user_id}, synchronize_session=False)
    db.session.flush()
    app.logger.info(
        "migrate_user_study_record done: migrated_records=%s course_id=%s",
        len(migrate_attends),
        normalized_course_id,
    )


def init_first_course(app: Flask, user_id: str) -> bool:
    # Ensure pending state changes are visible to subsequent queries
    """Initialize first course."""
    db.session.flush()

    # Count only verified users for the bootstrap check.
    # Support both legacy verified states (1..3) and canonical verified states
    # (1102..1104), while intentionally excluding unregistered states.
    verified_states = [
        1,
        2,
        3,
        USER_STATE_REGISTERED,
        USER_STATE_TRAIL,
        USER_STATE_PAID,
    ]
    lock_acquired = _acquire_bootstrap_lock(app)
    if lock_acquired is False:
        return False
    creator_granted_now = False
    try:
        verified_users = (
            UserEntity.query.filter(UserEntity.deleted == 0)
            .filter(UserEntity.state.in_(verified_states))
            .order_by(UserEntity.created_at.asc(), UserEntity.id.asc())
            .limit(2)
            .all()
        )
        if len(verified_users) != 1 or verified_users[0].user_bid != user_id:
            db.session.flush()
            return False

        # Bootstrap the first verified account so self-hosted deployments are
        # manageable without extra manual role assignment.
        creator_granted_now = not bool(verified_users[0].is_creator)
        mark_user_roles(user_id, is_creator=True, is_operator=True)

        # Holds a model class, so it keeps the CapWords spelling.
        ShifuModel: PublishedShifu | DraftShifu = PublishedShifu  # noqa: N806
        # Assign demo shifu only when there is exactly one published course
        course_count = PublishedShifu.query.filter(PublishedShifu.deleted == 0).count()
        if course_count == 0:
            course_count = DraftShifu.query.filter(DraftShifu.deleted == 0).count()
            ShifuModel = DraftShifu  # noqa: N806
        if course_count != 1:
            db.session.flush()
            return creator_granted_now

        course = (
            ShifuModel.query.filter(ShifuModel.deleted == 0)
            .order_by(ShifuModel.id.asc())
            .first()
        )
        if course:
            # Persist creator on the published record
            course.created_user_bid = user_id
            # Also persist creator on the corresponding draft (used by permission checks)
            draft = DraftShifu.query.filter(
                DraftShifu.deleted == 0,
                DraftShifu.shifu_bid == course.shifu_bid,
            ).first()
            if draft:
                draft.created_user_bid = user_id
        db.session.flush()
        return creator_granted_now
    finally:
        if lock_acquired:
            _release_bootstrap_lock()


def verify_phone_code(
    app: Flask,
    user_id: str | None,
    phone: str,
    code: str,
    course_id: str | None = None,
    language: str | None = None,
    login_context: str | None = None,
) -> tuple[UserToken, bool, dict[str, str | None]]:
    # Local import avoids circular dependency during module initialization.
    """Verify phone code."""
    from flaskr.service.profile.funcs import (
        get_user_profile_labels,
        update_user_profile_with_lable,
    )

    raw_phone = (phone or "").strip()
    normalized_phone = normalize_phone_identifier(raw_phone)
    if not normalized_phone:
        raise_param_error("mobile")
    consume_verification_code(
        app,
        identifier=raw_phone,
        code=code,
        kind="sms",
    )

    created_new_user = False
    creator_granted_now = False
    normalized_course_id = str(course_id or "").strip() or None

    with transactional_session():
        target_aggregate = load_user_aggregate_by_identifier(
            normalized_phone, providers=["phone"]
        )
        origin_aggregate = load_user_aggregate(user_id) if user_id else None

        if not target_aggregate and origin_aggregate:
            target_aggregate = origin_aggregate

        if target_aggregate and user_id and target_aggregate.user_bid != user_id:
            app.logger.info(
                "verify_phone_code merge_candidate origin_user_id=%s target_user_id=%s course_id=%s",
                user_id,
                target_aggregate.user_bid,
                normalized_course_id,
            )
            include_legacy_nickname = merge_learner_profile_for_sign_in(
                source_user_id=user_id,
                target_user_id=target_aggregate.user_bid,
            )
            if normalized_course_id is None:
                app.logger.warning(
                    "verify_phone_code skip_study_migration missing_course_id origin_user_id=%s target_user_id=%s",
                    user_id,
                    target_aggregate.user_bid,
                )
            else:
                new_profiles = get_user_profile_labels(
                    app,
                    user_id,
                    normalized_course_id,
                    include_nickname=include_legacy_nickname,
                    include_background=False,
                )
                update_user_profile_with_lable(
                    app,
                    target_aggregate.user_bid,
                    new_profiles,
                    update_all=False,
                    course_id=normalized_course_id,
                )
                migrate_user_study_record(
                    app,
                    origin_aggregate.user_bid if origin_aggregate else user_id,
                    target_aggregate.user_bid,
                    normalized_course_id,
                )
            if origin_aggregate:
                missing_open_id = (
                    origin_aggregate.wechat_open_id
                    and not target_aggregate.wechat_open_id
                )
                missing_union_id = (
                    origin_aggregate.wechat_union_id
                    and not target_aggregate.wechat_union_id
                )
                if missing_open_id or missing_union_id:
                    upsert_wechat_credentials(
                        app,
                        user_bid=target_aggregate.user_bid,
                        open_id=(
                            origin_aggregate.wechat_open_id if missing_open_id else None
                        ),
                        union_id=(
                            origin_aggregate.wechat_union_id
                            if missing_union_id
                            else None
                        ),
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
            creator_granted_now = (
                init_first_course(app, target_aggregate.user_bid) or creator_granted_now
            )
        else:
            entity = get_user_entity_by_bid(
                target_aggregate.user_bid, include_deleted=True
            )
            if entity:
                updates: dict[str, Any] = {"identify": normalized_phone}
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
                    created_new_user = True
                    creator_granted_now = (
                        init_first_course(app, entity.user_bid) or creator_granted_now
                    )

        upsert_credential(
            app,
            user_bid=target_aggregate.user_bid,
            provider_name="phone",
            subject_id=normalized_phone,
            subject_format="phone",
            identifier=normalized_phone,
            metadata={"course_id": normalized_course_id, "language": language},
            verified=True,
        )

        # If configured, automatically grant creator and demo-course permissions
        creator_granted_now = (
            ensure_admin_creator_and_demo_permissions(
                app,
                target_aggregate.user_bid,
                target_aggregate.language,
                login_context,
            )
            or creator_granted_now
        )

        refreshed = load_user_aggregate(target_aggregate.user_bid)
        if not refreshed:
            raise_error("USER.USER_NOT_FOUND")
        token = generate_token(app, user_id=refreshed.user_bid)
        user_dto = build_user_info_from_aggregate(refreshed)
        snapshot = build_user_profile_snapshot_from_aggregate(refreshed)

    return (
        UserToken(user_info=user_dto, token=token),
        created_new_user,
        {
            "course_id": normalized_course_id,
            "creator_granted_now": creator_granted_now,
            "language": language,
            "snapshot": snapshot.to_dict(),
        },
    )

"""Email verification workflow utilities."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from flaskr.service.common.dtos import UserToken
from flaskr.service.common.models import raise_error
from flaskr.service.profile.api import merge_learner_profile_for_sign_in
from flaskr.service.user.consts import USER_STATE_REGISTERED, USER_STATE_UNREGISTERED
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
from flaskr.service.user.utils import (
    ensure_admin_creator_and_demo_permissions,
    generate_token,
)
from flaskr.service.user.verification_codes import consume_verification_code

if TYPE_CHECKING:
    from flask import Flask


def verify_email_code(
    app: Flask,
    user_id: str | None,
    email: str,
    code: str,
    course_id: str | None = None,
    language: str | None = None,
    login_context: str | None = None,
) -> tuple[UserToken, bool, dict[str, str | None]]:
    # Local import avoids circular dependency during module initialization.
    """Verify email code."""
    from flaskr.service.profile.funcs import (
        get_user_profile_labels,
        update_user_profile_with_lable,
    )

    email_key = (email or "").strip()
    consume_verification_code(
        app,
        identifier=email_key,
        code=code,
    )

    normalized_email = email_key.lower() if email_key else ""

    created_new_user = False
    creator_granted_now = False

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
                    include_background=False,
                )
                update_user_profile_with_lable(
                    app,
                    target_aggregate.user_bid,
                    new_profiles,
                    update_all=False,
                    course_id=course_id,
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
            creator_granted_now = (
                init_first_course(app, target_aggregate.user_bid) or creator_granted_now
            )
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
                    created_new_user = True
                    creator_granted_now = (
                        init_first_course(app, entity.user_bid) or creator_granted_now
                    )

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
            "course_id": course_id,
            "creator_granted_now": creator_granted_now,
            "language": language,
            "snapshot": snapshot.to_dict(),
        },
    )

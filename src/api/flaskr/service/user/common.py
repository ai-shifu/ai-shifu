from flask import Flask, has_app_context

from typing import Optional

import jwt

from flaskr.i18n import get_i18n_list
from ..common.dtos import UserInfo, UserToken
from ..common.models import raise_error
from ...dao import db
from .auth import get_provider
from .auth.base import VerificationRequest
from .repository import (
    build_user_info_from_aggregate,
    get_user_entity_by_bid,
    load_user_aggregate,
    update_user_entity_fields,
    upsert_credential,
)
from ..profile.funcs import save_user_profiles
from ..profile.dtos import ProfileToSave
from .token_store import token_store


def _load_user_info(user_bid: str) -> UserInfo:
    aggregate = load_user_aggregate(user_bid)
    if not aggregate:
        raise_error("USER.USER_NOT_FOUND")
    return build_user_info_from_aggregate(aggregate)


def validate_user(app: Flask, token: str) -> UserInfo:
    def _validate() -> UserInfo:
        if not token:
            raise_error("server.user.userNotLogin")
        try:
            if app.config.get("ENVERIMENT", "prod") == "dev":
                return _load_user_info(token)
            else:
                user_id = jwt.decode(
                    token, app.config["SECRET_KEY"], algorithms=["HS256"]
                )["user_id"]
                app.logger.info("user_id:" + user_id)

            app.logger.info("user_id:" + user_id)
            ttl_seconds = app.config.get("TOKEN_EXPIRE_TIME", 60 * 60 * 24 * 7)
            lookup = token_store.get_and_refresh(
                app,
                token=token,
                expected_user_id=user_id,
                ttl_seconds=ttl_seconds,
            )
            if lookup is None:
                raise_error("server.user.userTokenExpired")
            return _load_user_info(lookup.user_id)
        except jwt.exceptions.ExpiredSignatureError:
            raise_error("server.user.userTokenExpired")
        except jwt.exceptions.DecodeError:
            raise_error("server.user.userNotFound")

    if has_app_context():
        return _validate()
    with app.app_context():
        return _validate()


def update_user_info(
    app: Flask,
    user: UserInfo,
    name,
    email=None,
    mobile=None,
    language=None,
    avatar=None,
) -> UserInfo:
    with app.app_context():
        if not user:
            raise_error("server.user.userNotFound")

        app.logger.info("update_user_info %s %s %s %s", name, email, mobile, language)
        aggregate = load_user_aggregate(user.user_id)
        if not aggregate:
            raise_error("server.user.userNotFound")

        updates = {}
        updates_profile = {}
        update_profile = False
        if name is not None:
            updates["nickname"] = name
            updates_profile["sys_user_nickname"] = name
            update_profile = True
        if language is not None:
            if language in get_i18n_list(app):
                updates["language"] = language
                updates_profile["sys_user_language"] = language
                update_profile = True
            else:
                raise_error("USER.LANGUAGE_NOT_FOUND")
        if avatar is not None:
            updates["avatar"] = avatar

        entity = get_user_entity_by_bid(user.user_id, include_deleted=True)
        if not entity:
            raise_error("server.user.languageNotFound")
        entity = update_user_entity_fields(entity, **updates)
        if update_profile:
            save_user_profiles(
                app,
                user.user_id,
                "",
                [
                    ProfileToSave(key=key, value=value, bid=None)
                    for key, value in updates_profile.items()
                ],
            )

        if email is not None:
            normalized_email = email.lower() if email else ""
            if normalized_email:
                upsert_credential(
                    app,
                    user_bid=entity.user_bid,
                    provider_name="email",
                    subject_id=normalized_email,
                    subject_format="email",
                    identifier=normalized_email,
                    metadata={},
                    verified=False,
                )
        if mobile is not None:
            normalized_phone = mobile.strip() if mobile else ""
            if normalized_phone:
                upsert_credential(
                    app,
                    user_bid=entity.user_bid,
                    provider_name="phone",
                    subject_id=normalized_phone,
                    subject_format="phone",
                    identifier=normalized_phone,
                    metadata={},
                    verified=False,
                )

        db.session.commit()
        refreshed = load_user_aggregate(user.user_id)
        if not refreshed:
            raise_error("USER.USER_NOT_FOUND")
        return build_user_info_from_aggregate(refreshed)


def verify_sms_code(
    app: Flask,
    user_id,
    phone: str,
    chekcode: str,
    course_id: str = None,
    language: str = None,
    login_context: Optional[str] = None,
) -> UserToken:
    provider = get_provider("phone")
    request = VerificationRequest(
        identifier=phone,
        code=chekcode,
        metadata={
            "user_id": user_id,
            "course_id": course_id,
            "language": language,
            "login_context": login_context,
        },
    )
    auth_result = provider.verify(app, request)
    return auth_result.token

# common user


import random
import string
from flask import Flask

from typing import Optional

import jwt

from flaskr.api.sms.aliyun import send_sms_code_ali
from flaskr.i18n import get_i18n_list
from ..common.dtos import UserInfo, UserToken
from ..common.models import raise_error
from ...dao import redis_client as redis, db
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


def _load_user_info(app: Flask, user_bid: str) -> UserInfo:
    aggregate = load_user_aggregate(user_bid)
    if not aggregate:
        raise_error("USER.USER_NOT_FOUND")
    return build_user_info_from_aggregate(aggregate)


def validate_user(app: Flask, token: str) -> UserInfo:
    with app.app_context():
        if not token:
            raise_error("server.user.userNotLogin")
        try:
            if app.config.get("ENVERIMENT", "prod") == "dev":
                return _load_user_info(app, token)
            else:
                user_id = jwt.decode(
                    token, app.config["SECRET_KEY"], algorithms=["HS256"]
                )["user_id"]
                app.logger.info("user_id:" + user_id)

            app.logger.info("user_id:" + user_id)
            redis_user_id = redis.get(app.config["REDIS_KEY_PREFIX_USER"] + token)
            if redis_user_id is None:
                raise_error("server.user.userTokenExpired")
            set_user_id = str(
                redis_user_id,
                encoding="utf-8",
            )
            if set_user_id == user_id:
                return _load_user_info(app, user_id)
            else:
                raise_error("server.user.userTokenExpired")
        except jwt.exceptions.ExpiredSignatureError:
            raise_error("server.user.userTokenExpired")
        except jwt.exceptions.DecodeError:
            raise_error("server.user.userNotFound")


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
            updates = {"nickname": name}
            updates_profile = {"sys_user_nickname": name}
            update_profile = True
        if language is not None:
            if language in get_i18n_list(app):
                updates["language"] = language
                updates_profile = {"sys_user_language": language}
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


def get_user_info(app: Flask, user_id: str) -> UserInfo:
    with app.app_context():
        return _load_user_info(app, user_id)


def get_sms_code_info(app: Flask, user_id: str, resend: bool):
    with app.app_context():
        phone = redis.get(app.config["REDIS_KEY_PREFIX_PHONE"] + user_id)
        if phone is None:
            aggregate = load_user_aggregate(user_id)
            phone = aggregate.mobile if aggregate else ""
        else:
            phone = str(phone, encoding="utf-8")
        ttl = redis.ttl(app.config["REDIS_KEY_PREFIX_PHONE_CODE"] + phone)
        if ttl < 0:
            ttl = 0
        return {"expire_in": ttl, "phone": phone}


def send_sms_code_without_check(app: Flask, user_info: object, phone: str):
    user_bid = getattr(user_info, "user_id", None) or getattr(
        user_info, "user_bid", None
    )
    if not user_bid:
        raise_error("USER.USER_NOT_FOUND")
    characters = string.digits
    random_string = "".join(random.choices(characters, k=4))
    # 发送短信验证码
    redis.set(
        app.config["REDIS_KEY_PREFIX_PHONE"] + user_bid,
        phone,
        ex=app.config.get("PHONE_EXPIRE_TIME", 60 * 30),
    )
    redis.set(
        app.config["REDIS_KEY_PREFIX_PHONE_CODE"] + phone,
        random_string,
        ex=app.config["PHONE_CODE_EXPIRE_TIME"],
    )
    send_sms_code_ali(app, phone, random_string)
    db.session.flush()
    return {"expire_in": app.config["PHONE_CODE_EXPIRE_TIME"], "phone": phone}


def verify_sms_code_without_phone(
    app: Flask, user_info: object, checkcode, course_id: Optional[str] = None
) -> UserToken:
    with app.app_context():
        user_bid = getattr(user_info, "user_id", None) or getattr(
            user_info, "user_bid", None
        )
        if not user_bid:
            raise_error("USER.USER_NOT_FOUND")

        phone = redis.get(app.config["REDIS_KEY_PREFIX_PHONE"] + user_bid)
        if phone is None:
            app.logger.info("cache user_id:%s phone is None", user_bid)
            aggregate = load_user_aggregate(user_bid)
            phone = aggregate.mobile if aggregate else ""
        else:
            phone = str(phone, encoding="utf-8")
        ret = verify_sms_code(app, user_bid, phone, checkcode, course_id)
        db.session.commit()
        return ret


def verify_sms_code(
    app: Flask,
    user_id,
    phone: str,
    chekcode: str,
    course_id: str = None,
    language: str = None,
) -> UserToken:
    provider = get_provider("phone")
    request = VerificationRequest(
        identifier=phone,
        code=chekcode,
        metadata={
            "user_id": user_id,
            "course_id": course_id,
            "language": language,
        },
    )
    auth_result = provider.verify(app, request)
    return auth_result.token

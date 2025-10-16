# common user


import random
import string
from flask import Flask

import jwt

from flaskr.service.user.models import User
from flaskr.api.sms.aliyun import send_sms_code_ali
from ..common.dtos import UserInfo, UserToken
from ..common.models import raise_error
from ...dao import redis_client as redis, db
from flaskr.i18n import get_i18n_list
from .auth import get_provider
from .auth.base import VerificationRequest
from .repository import (
    build_user_info_dto,
    load_user_with_entity,
    sync_user_entity_for_legacy,
)


def _user_info_from_legacy(app: Flask, legacy_user: User) -> UserInfo:
    sync_user_entity_for_legacy(app, legacy_user)
    return build_user_info_dto(legacy_user)


def validate_user(app: Flask, token: str) -> UserInfo:
    with app.app_context():
        if not token:
            raise_error("USER.USER_NOT_LOGIN")
        try:
            if app.config.get("ENVERIMENT", "prod") == "dev":
                user_id = token
                user = User.query.filter_by(user_id=user_id).first()

                if user:
                    return _user_info_from_legacy(app, user)
            else:
                user_id = jwt.decode(
                    token, app.config["SECRET_KEY"], algorithms=["HS256"]
                )["user_id"]
                app.logger.info("user_id:" + user_id)

            app.logger.info("user_id:" + user_id)
            redis_user_id = redis.get(app.config["REDIS_KEY_PREFIX_USER"] + token)
            if redis_user_id is None:
                raise_error("USER.USER_TOKEN_EXPIRED")
            set_user_id = str(
                redis_user_id,
                encoding="utf-8",
            )
            if set_user_id == user_id:
                legacy_user, _ = load_user_with_entity(app, user_id)
                if legacy_user:
                    return _user_info_from_legacy(app, legacy_user)
                else:
                    raise_error("USER.USER_TOKEN_EXPIRED")
            else:
                raise_error("USER.USER_TOKEN_EXPIRED")
        except jwt.exceptions.ExpiredSignatureError:
            raise_error("USER.USER_TOKEN_EXPIRED")
        except jwt.exceptions.DecodeError:
            raise_error("USER.USER_NOT_FOUND")


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
            raise_error("USER.USER_NOT_FOUND")

        app.logger.info("update_user_info %s %s %s %s", name, email, mobile, language)
        legacy_user = User.query.filter_by(user_id=user.user_id).first()
        if not legacy_user:
            raise_error("USER.USER_NOT_FOUND")

        legacy_user.name = name
        if email is not None:
            legacy_user.email = email
        if mobile is not None:
            legacy_user.mobile = mobile
        if language is not None:
            if language in get_i18n_list(app):
                legacy_user.user_language = language
            else:
                raise_error("USER.LANGUAGE_NOT_FOUND")

        sync_user_entity_for_legacy(app, legacy_user)
        db.session.commit()
        return build_user_info_dto(legacy_user)


def get_user_info(app: Flask, user_id: str) -> UserInfo:
    with app.app_context():
        legacy_user, _ = load_user_with_entity(app, user_id)
        if not legacy_user:
            raise_error("USER.USER_NOT_FOUND")
        return build_user_info_dto(legacy_user)


def get_sms_code_info(app: Flask, user_id: str, resend: bool):
    with app.app_context():
        phone = redis.get(app.config["REDIS_KEY_PREFIX_PHONE"] + user_id)
        if phone is None:
            user = User.query.filter(User.user_id == user_id).first()
            phone = user.mobile
        else:
            phone = str(phone, encoding="utf-8")
        ttl = redis.ttl(app.config["REDIS_KEY_PREFIX_PHONE_CODE"] + phone)
        if ttl < 0:
            ttl = 0
        return {"expire_in": ttl, "phone": phone}


def send_sms_code_without_check(app: Flask, user_info: User, phone: str):
    user_info.mobile = phone
    characters = string.digits
    random_string = "".join(random.choices(characters, k=4))
    # 发送短信验证码
    redis.set(
        app.config["REDIS_KEY_PREFIX_PHONE"] + user_info.user_id,
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
    app: Flask, user_info: User, checkcode, course_id: str = None
) -> UserToken:
    with app.app_context():
        phone = redis.get(app.config["REDIS_KEY_PREFIX_PHONE"] + user_info.user_id)
        if phone is None:
            app.logger.info("cache user_id:" + user_info.user_id + " phone is None")
            user = (
                User.query.filter(User.user_id == user_info.user_id)
                .order_by(User.id.asc())
                .first()
            )
            phone = user.mobile
        else:
            phone = str(phone, encoding="utf-8")
            user = (
                User.query.filter(User.mobile == phone).order_by(User.id.asc()).first()
            )
            if user:
                user_id = user.user_id
        ret = verify_sms_code(app, user_id, phone, checkcode, course_id)
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


# verify mail code
def verify_mail_code(
    app: Flask,
    user_id,
    mail: str,
    chekcode: str,
    course_id: str = None,
    language: str = None,
) -> UserToken:
    provider = get_provider("email")
    request = VerificationRequest(
        identifier=mail.lower(),
        code=chekcode,
        metadata={
            "user_id": user_id,
            "course_id": course_id,
            "language": language,
        },
    )
    auth_result = provider.verify(app, request)
    return auth_result.token

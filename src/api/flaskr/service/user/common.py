# common user


import random
import string
import uuid
from flaskr.common.config import get_config
from flask import Flask

import jwt

from flaskr.service.user.models import User
from flaskr.api.sms.aliyun import send_sms_code_ali
from ..common.dtos import (
    USER_STATE_REGISTERED,
    USER_STATE_UNREGISTERED,
    UserInfo,
    UserToken,
)
from ..common.models import raise_error
from .utils import generate_token, get_user_language, get_user_openid
from ...dao import redis_client as redis, db
from flaskr.i18n import get_i18n_list
from .phone_flow import init_first_course, migrate_user_study_record
from ..auth import get_provider
from ..auth.base import VerificationRequest

FIX_CHECK_CODE = get_config("UNIVERSAL_VERIFICATION_CODE")


def validate_user(app: Flask, token: str) -> UserInfo:
    with app.app_context():
        if not token:
            raise_error("USER.USER_NOT_LOGIN")
        try:
            if app.config.get("ENVERIMENT", "prod") == "dev":
                user_id = token
                user = User.query.filter_by(user_id=user_id).first()

                if user:
                    return UserInfo(
                        user_id=user.user_id,
                        username=user.username,
                        name=user.name,
                        email=user.email,
                        mobile=user.mobile,
                        user_state=user.user_state,
                        wx_openid=get_user_openid(user),
                        language=get_user_language(user),
                        user_avatar=user.user_avatar,
                        is_admin=user.is_admin,
                        is_creator=user.is_creator,
                    )
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
                user = User.query.filter_by(user_id=user_id).first()
                if user:
                    return UserInfo(
                        user_id=user.user_id,
                        username=user.username,
                        name=user.name,
                        email=user.email,
                        mobile=user.mobile,
                        user_state=user.user_state,
                        wx_openid=get_user_openid(user),
                        language=get_user_language(user),
                        user_avatar=user.user_avatar,
                        is_admin=user.is_admin,
                        is_creator=user.is_creator,
                    )
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
        if user:
            app.logger.info(
                "update_user_info {} {} {} {} {}".format(
                    name, email, mobile, language, avatar
                )
            )
            dbuser = User.query.filter_by(user_id=user.user_id).first()
            if name is not None:
                dbuser.name = name
            if email is not None:
                dbuser.email = email
            if mobile is not None:
                dbuser.mobile = mobile
            if language is not None:
                if language in get_i18n_list(app):
                    dbuser.user_language = language
                else:
                    raise_error("USER.LANGUAGE_NOT_FOUND")
            if avatar is not None:
                dbuser.user_avatar = avatar
            db.session.commit()
            return UserInfo(
                user_id=user.user_id,
                username=user.username,
                name=user.name,
                email=user.email,
                mobile=user.mobile,
                user_state=dbuser.user_state,
                wx_openid=get_user_openid(user),
                language=dbuser.user_language,
                user_avatar=dbuser.user_avatar,
                is_admin=dbuser.is_admin,
                is_creator=dbuser.is_creator,
            )
        else:
            raise_error("USER.USER_NOT_FOUND")


def get_user_info(app: Flask, user_id: str) -> UserInfo:
    with app.app_context():
        user = User.query.filter_by(user_id=user_id).first()
        if user:
            return UserInfo(
                user_id=user.user_id,
                username=user.username,
                name=user.name,
                email=user.email,
                mobile=user.mobile,
                user_state=user.user_state,
                wx_openid=get_user_openid(user),
                language=get_user_language(user),
                user_avatar=user.user_avatar,
                is_admin=user.is_admin,
                is_creator=user.is_creator,
            )
        else:
            raise_error("USER.USER_NOT_FOUND")


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
    from flaskr.service.profile.funcs import (
        get_user_profile_labels,
        update_user_profile_with_lable,
    )

    check_save = redis.get(app.config["REDIS_KEY_PREFIX_MAIL_CODE"] + mail)
    if check_save is None and chekcode != FIX_CHECK_CODE:
        raise_error("USER.MAIL_SEND_EXPIRED")
    check_save_str = str(check_save, encoding="utf-8") if check_save else ""
    if chekcode != check_save_str and chekcode != FIX_CHECK_CODE:
        raise_error("USER.MAIL_CHECK_ERROR")
    else:
        redis.delete(app.config["REDIS_KEY_PREFIX_MAIL_CODE"] + mail)
        user_info = (
            User.query.filter(User.email == mail)
            .order_by(User.user_state.desc())
            .order_by(User.id.asc())
            .first()
        )
        if not user_info:
            user_info = (
                User.query.filter(User.user_id == user_id)
                .order_by(User.id.asc())
                .first()
            )
        elif user_id != user_info.user_id and course_id is not None:
            new_profiles_dto = get_user_profile_labels(app, user_id, course_id)
            new_profiles = [
                {
                    "key": profile.key,
                    "value": profile.value,
                    "label": profile.label,
                    "type": profile.type,
                    "items": profile.items,
                }
                for profile in new_profiles_dto.profiles
            ]
            update_user_profile_with_lable(
                app, user_info.user_id, new_profiles, False, course_id
            )
            origin_user = User.query.filter(User.user_id == user_id).first()
            migrate_user_study_record(
                app, origin_user.user_id, user_info.user_id, course_id
            )
            if (
                origin_user
                and origin_user.user_open_id != user_info.user_open_id  # noqa W503
                and (
                    user_info.user_open_id is None  # noqa W503
                    or user_info.user_open_id == ""
                )
            ):
                user_info.user_open_id = origin_user.user_open_id
        if user_info is None:
            user_id = str(uuid.uuid4()).replace("-", "")
            user_info = User(
                user_id=user_id, username="", name="", email=mail, mobile=""
            )
            if (
                user_info.user_state is None
                or user_info.user_state == USER_STATE_UNREGISTERED  # noqa W503
            ):
                user_info.user_state = USER_STATE_REGISTERED
            user_info.email = mail
            user_info.user_language = language
            db.session.add(user_info)
            # New user registration requires course association detection
            # When there is an install ui, the logic here should be removed
            init_first_course(app, user_info.user_id)

        if user_info.user_state == USER_STATE_UNREGISTERED:
            user_info.email = mail
            user_info.user_state = USER_STATE_REGISTERED
            user_info.user_language = language
        user_id = user_info.user_id
        token = generate_token(app, user_id=user_id)
        db.session.flush()
        return UserToken(
            UserInfo(
                user_id=user_info.user_id,
                username=user_info.username,
                name=user_info.name,
                email=user_info.email,
                mobile=user_info.mobile,
                user_state=user_info.user_state,
                wx_openid=get_user_openid(user_info),
                language=get_user_language(user_info),
                user_avatar=user_info.user_avatar,
                is_admin=user_info.is_admin,
                is_creator=user_info.is_creator,
            ),
            token,
        )

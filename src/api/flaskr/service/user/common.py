# common user


import hashlib
import random
import string
import uuid
from flask import Flask
import jwt

from flaskr.service.order.consts import ATTEND_STATUS_RESET
from flaskr.service.profile.funcs import (
    get_user_profile_labels,
    update_user_profile_with_lable,
)
from sqlalchemy import text
from flaskr.api.sms.aliyun import send_sms_code_ali
from flaskr.service.order.models import AICourseLessonAttend
from ..common.dtos import (
    USER_STATE_REGISTERED,
    USER_STATE_UNTEGISTERED,
    UserInfo,
    UserToken,
)
from ..common.models import raise_error
from .utils import generate_token, get_user_language, get_user_openid
from ...dao import redis_client as redis, db
from .models import User as CommonUser, AdminUser as AdminUser


FIX_CHECK_CODE = "0615"


def get_model(app: Flask):
    if app.config.get("MODE", "api") == "admin":
        return AdminUser
    else:
        return CommonUser


def verify_user(app: Flask, login: str, raw_password: str) -> UserToken:
    User = get_model(app)
    with app.app_context():
        user = User.query.filter(
            (User.username == login) | (User.email == login) | (User.mobile == login)
        ).first()
        if user:
            password_hash = hashlib.md5(
                (user.user_id + raw_password).encode()
            ).hexdigest()
            if password_hash == user.password_hash:
                token = generate_token(app, user_id=user.user_id)
                return UserToken(
                    UserInfo(
                        user_id=user.user_id,
                        username=user.username,
                        name=user.name,
                        email=user.email,
                        mobile=user.mobile,
                        model=user.default_model,
                        user_state=user.user_state,
                        wx_openid=get_user_openid(user),
                        language=get_user_language(user),
                    ),
                    token=token,
                )
            else:
                raise_error("USER.USER_PASSWORD_ERROR")
        else:
            raise_error("USER.USER_NOT_FOUND")


def validate_user(app: Flask, token: str) -> UserInfo:
    User = get_model(app)
    with app.app_context():
        if token is None:
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
                        model=user.default_model,
                        user_state=user.user_state,
                        wx_openid=get_user_openid(user),
                        language=get_user_language(user),
                    )
            else:
                user_id = jwt.decode(
                    token, app.config["SECRET_KEY"], algorithms=["HS256"]
                )["user_id"]

            app.logger.info("user_id:" + user_id)
            redis_token = redis.get(app.config["REDIS_KEY_PRRFIX_USER"] + user_id)
            if redis_token is None:
                raise_error("USER.USER_TOKEN_EXPIRED")
            set_token = str(
                redis.get(app.config["REDIS_KEY_PRRFIX_USER"] + user_id),
                encoding="utf-8",
            )
            if set_token == token:
                user = User.query.filter_by(user_id=user_id).first()
                if user:
                    return UserInfo(
                        user_id=user.user_id,
                        username=user.username,
                        name=user.name,
                        email=user.email,
                        mobile=user.mobile,
                        model=user.default_model,
                        user_state=user.user_state,
                        wx_openid=get_user_openid(user),
                        language=get_user_language(user),
                    )
                else:
                    raise_error("USER.USER_TOKEN_EXPIRED")
            else:
                raise_error("USER.USER_TOKEN_EXPIRED")
        except (jwt.exceptions.ExpiredSignatureError):
            raise_error("USER.USER_TOKEN_EXPIRED")
        except (jwt.exceptions.DecodeError):
            raise_error("USER.USER_NOT_FOUND")


def update_user_info(
    app: Flask, user: UserInfo, name, email=None, mobile=None
) -> UserInfo:
    User = get_model(app)
    with app.app_context():
        if user:
            dbuser = User.query.filter_by(user_id=user.user_id).first()
            dbuser.name = name
            if email is not None:
                dbuser.email = email
            if mobile is not None:
                dbuser.mobile = mobile
            db.session.commit()
            return UserInfo(
                user_id=user.user_id,
                username=user.username,
                name=user.name,
                email=user.email,
                mobile=user.mobile,
                model=dbuser.default_model,
                user_state=dbuser.user_state,
                wx_openid=get_user_openid(user),
                language=get_user_language(user),
            )
        else:
            raise_error("USER.USER_NOT_FOUND")


def change_user_passwd(app: Flask, user: UserInfo, oldpwd, newpwd) -> UserInfo:
    User = get_model(app)
    with app.app_context():
        if user:
            user = User.query.filter_by(user_id=user.user_id).first()
            password_hash = hashlib.md5((user.user_id + oldpwd).encode()).hexdigest()
            if password_hash == user.password_hash:
                user.password_hash = hashlib.md5(
                    (user.user_id + newpwd).encode()
                ).hexdigest()
                db.session.commit()
                return UserInfo(
                    user_id=user.user_id,
                    username=user.username,
                    name=user.name,
                    email=user.email,
                    mobile=user.mobile,
                    model=user.default_model,
                    user_state=user.user_state,
                    wx_openid=get_user_openid(user),
                    language=get_user_language(user),
                )
            else:
                raise_error("USER.OLD_PASSWORD_ERROR")
        else:
            raise_error("USER.USER_NOT_FOUND")


def get_user_info(app: Flask, user_id: str) -> UserInfo:
    User = get_model(app)
    with app.app_context():
        user = User.query.filter_by(user_id=user_id).first()
        if user:
            return UserInfo(
                user_id=user.user_id,
                username=user.username,
                name=user.name,
                email=user.email,
                mobile=user.mobile,
                model=user.default_model,
                user_state=user.user_state,
                wx_openid=get_user_openid(user),
                language=get_user_language(user),
            )
        else:
            raise_error("USER.USER_NOT_FOUND")


def require_reset_pwd_code(app: Flask, login: str):
    User = get_model(app)
    with app.app_context():
        user = User.query.filter(
            (User.username == login) | (User.email == login) | (User.mobile == login)
        ).first()
        if user:
            code = random.randint(0, 9999)
            redis.set(
                app.config["REDIS_KEY_PRRFIX_RESET_PWD"] + user.user_id,
                code,
                ex=app.config["RESET_PWD_CODE_EXPIRE_TIME"],
            )
            return True
        else:
            raise_error("USER.USER_NOT_FOUND")


def reset_pwd(app: Flask, login: str, code: int, newpwd: str):
    User = get_model(app)
    with app.app_context():
        user = User.query.filter(
            (User.username == login) | (User.email == login) | (User.mobile == login)
        ).first()
        if user:
            redis_code = redis.get(
                app.config["REDIS_KEY_PRRFIX_RESET_PWD"] + user.user_id
            )
            if redis_code is None:
                raise_error("USER.RESET_PWD_CODE_EXPIRED")
            set_code = int(str(redis_code, encoding="utf-8"))
            app.logger.info("code:" + str(code) + " set_code:" + str(set_code))
            if str(set_code) == str(code):
                app.logger.info("code:" + str(code) + " set_code:" + str(set_code))
                user.password_hash = hashlib.md5(
                    (user.user_id + newpwd).encode()
                ).hexdigest()
                db.session.commit()
                app.logger.info("update password")
                return True
            else:
                raise_error("USER.RESET_PWD_CODE_ERROR")
        else:
            raise_error("USER.USER_NOT_FOUND")


def get_sms_code_info(app: Flask, user_id: str, resend: bool):
    User = get_model(app)
    with app.app_context():
        phone = redis.get(app.config["REDIS_KEY_PRRFIX_PHONE"] + user_id)
        if phone is None:
            user = User.query.filter(User.user_id == user_id).first()
            phone = user.mobile
        else:
            phone = str(phone, encoding="utf-8")
        ttl = redis.ttl(app.config["REDIS_KEY_PRRFIX_PHONE_CODE"] + phone)
        if ttl < 0:
            ttl = 0
        return {"expire_in": ttl, "phone": phone}


def send_sms_code_without_check(app: Flask, user_id: str, phone: str):
    User = get_model(app)
    user = User.query.filter(User.user_id == user_id).first()
    user.mobile = phone
    characters = string.digits
    random_string = "".join(random.choices(characters, k=4))
    # 发送短信验证码
    redis.set(
        app.config["REDIS_KEY_PRRFIX_PHONE"] + user_id,
        phone,
        ex=app.config.get("PHONE_EXPIRE_TIME", 60 * 30),
    )
    redis.set(
        app.config["REDIS_KEY_PRRFIX_PHONE_CODE"] + phone,
        random_string,
        ex=app.config["PHONE_CODE_EXPIRE_TIME"],
    )
    send_sms_code_ali(app, phone, random_string)
    db.session.flush()
    return {"expire_in": app.config["PHONE_CODE_EXPIRE_TIME"], "phone": phone}


def verify_sms_code_without_phone(app: Flask, user_id: str, checkcode) -> UserToken:
    User = get_model(app)
    with app.app_context():
        phone = redis.get(app.config["REDIS_KEY_PRRFIX_PHONE"] + user_id)
        if phone is None:
            app.logger.info("cache user_id:" + user_id + " phone is None")
            user = (
                User.query.filter(User.user_id == user_id)
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
        ret = verify_sms_code(app, user_id, phone, checkcode)
        db.session.commit()
        return ret


def migrate_user_study_record(app: Flask, from_user_id: str, to_user_id: str):
    app.logger.info(
        "migrate_user_study_record from_user_id:"
        + from_user_id
        + " to_user_id:"
        + to_user_id
    )
    from_attends = AICourseLessonAttend.query.filter(
        AICourseLessonAttend.user_id == from_user_id,
        AICourseLessonAttend.status != ATTEND_STATUS_RESET,
    ).all()
    to_attends = AICourseLessonAttend.query.filter(
        AICourseLessonAttend.user_id == to_user_id,
        AICourseLessonAttend.status != ATTEND_STATUS_RESET,
    ).all()
    for from_attend in from_attends:
        to_attend = [
            to_attend
            for to_attend in to_attends
            if to_attend.lesson_id == from_attend.lesson_id
        ]
        if len(to_attend) > 0:
            continue
        else:
            app.logger.info(
                "migrate_user_study_record from_attend.lesson_id:"
                + from_attend.lesson_id
            )
            from_attend.user_id = to_user_id
            db.session.execute(
                text(
                    "update ai_course_lesson_attendscript set user_id = '%s' where attend_id = '%s'"
                    % (to_user_id, from_attend.attend_id)
                )
            )
            db.session.flush()


# verify sms code
def verify_sms_code(app: Flask, user_id, phone: str, chekcode: str) -> UserToken:
    User = get_model(app)
    check_save = redis.get(app.config["REDIS_KEY_PRRFIX_PHONE_CODE"] + phone)
    if check_save is None and chekcode != FIX_CHECK_CODE:
        raise_error("USER.SMS_SEND_EXPIRED")
    check_save_str = str(check_save, encoding="utf-8") if check_save else ""
    if chekcode != check_save_str and chekcode != FIX_CHECK_CODE:
        raise_error("USER.SMS_CHECK_ERROR")
    else:
        user_info = (
            User.query.filter(User.mobile == phone)
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
        elif user_id != user_info.user_id:
            new_profiles = get_user_profile_labels(app, user_id)
            update_user_profile_with_lable(app, user_info.user_id, new_profiles)
            origin_user = User.query.filter(User.user_id == user_id).first()
            migrate_user_study_record(app, origin_user.user_id, user_info.user_id)
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
                user_id=user_id, username="", name="", email="", mobile=phone
            )
            if (
                user_info.user_state is None
                or user_info.user_state == USER_STATE_UNTEGISTERED  # noqa W503
            ):
                user_info.user_state = USER_STATE_REGISTERED
            user_info.mobile = phone
            db.session.add(user_info)
        if user_info.user_state == USER_STATE_UNTEGISTERED:
            user_info.mobile = phone
            user_info.user_state = USER_STATE_REGISTERED
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
                model=user_info.default_model,
                user_state=user_info.user_state,
                wx_openid=get_user_openid(user_info),
                language=get_user_language(user_info),
            ),
            token,
        )

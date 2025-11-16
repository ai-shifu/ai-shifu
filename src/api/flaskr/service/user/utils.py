from flask import Flask
import jwt
import time
import string
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flaskr.i18n import _

from ..common.models import raise_error
from ...dao import redis_client as redis, db
from flaskr.api.sms.aliyun import send_sms_code_ali
from .models import UserVerifyCode

import json

from flaskr.service.config.funcs import get_config as get_dynamic_config
from flaskr.service.shifu.models import AiCourseAuth
from flaskr.service.user.repository import mark_user_roles
from flaskr.util import generate_id


def get_user_openid(user):
    if hasattr(user, "user_open_id"):
        return user.user_open_id
    else:
        return ""


def _normalize_language_code(language_code: str) -> str:
    """Normalize legacy or inconsistent language codes into a canonical form."""
    if not language_code:
        return ""

    normalized = language_code.replace("_", "-")
    parts = [segment for segment in normalized.split("-") if segment]

    if not parts:
        return ""

    primary = parts[0].lower()
    subtags = []

    for segment in parts[1:]:
        if len(segment) == 2 and segment.isalpha():
            subtags.append(segment.upper())
        elif len(segment) == 4 and segment.isalpha():
            subtags.append(segment.title())
        else:
            subtags.append(segment)

    normalized_parts = [primary]
    normalized_parts.extend(subtags)
    return "-".join(normalized_parts)


def get_user_language(user):
    if hasattr(user, "user_language") and user.user_language:
        # Return the user's language as-is, let the i18n system handle fallback
        # Only normalize old format for compatibility
        normalized = _normalize_language_code(user.user_language)
        if normalized:
            return normalized
        return user.user_language
    else:
        # No language set, default to English
        return "en-US"


# generate token
def generate_token(app: Flask, user_id: str) -> str:
    with app.app_context():
        token = jwt.encode(
            {"user_id": user_id, "time_stamp": time.time()},
            app.config["SECRET_KEY"],
            algorithm="HS256",
        )
        redis.set(
            app.config["REDIS_KEY_PREFIX_USER"] + token,
            user_id,
            ex=app.config["TOKEN_EXPIRE_TIME"],
        )
        return token


# send sms code
def send_sms_code(app: Flask, phone: str, ip: str = None):
    with app.app_context():
        # Check IP ban status
        if ip:
            ip_ban_key = app.config["REDIS_KEY_PREFIX_IP_BAN"] + ip
            if redis.get(ip_ban_key):
                # Development, debugging and use
                # redis.delete(ip_ban_key)
                raise_error("server.user.ipBanned")

            # Check IP sending frequency
            ip_limit_key = app.config["REDIS_KEY_PREFIX_IP_LIMIT"] + ip
            ip_send_count = redis.get(ip_limit_key)

            if ip_send_count:
                ip_send_count = int(ip_send_count)
                if ip_send_count >= int(app.config["IP_SMS_LIMIT_COUNT"]):
                    # Ban the IP
                    redis.set(ip_ban_key, 1, ex=int(app.config["IP_BAN_TIME"]))
                    raise_error("server.user.ipBanned")
                else:
                    redis.incr(ip_limit_key)
            else:
                redis.set(ip_limit_key, 1, ex=int(app.config["IP_SMS_LIMIT_TIME"]))

        # Check phone sending frequency limit
        phone_limit_key = app.config["REDIS_KEY_PREFIX_PHONE_LIMIT"] + phone
        last_send_time = redis.get(phone_limit_key)

        if last_send_time:
            last_send_time = int(last_send_time)
            current_time = int(time.time())
            time_diff = current_time - last_send_time

            interval = int(app.config["SMS_CODE_INTERVAL"])
            if time_diff < interval:
                raise_error("server.user.smsSendTooFrequent")

        characters = string.digits
        # Generate a random string of length 4
        random_string = "".join(random.choices(characters, k=4))
        # 发送短信验证码
        redis.set(
            app.config["REDIS_KEY_PREFIX_PHONE_CODE"] + phone,
            random_string,
            ex=app.config["PHONE_CODE_EXPIRE_TIME"],
        )

        # Record the sending time
        redis.set(
            phone_limit_key, int(time.time()), ex=int(app.config["SMS_CODE_INTERVAL"])
        )

        user_verify_code = create_and_commit_user_verify_code(
            mail=None,
            phone=phone,
            verify_code=random_string,
            verify_code_type=1,  # 1: SMS, 2: Email
            ip=ip,
        )

        send_res = send_sms_code_ali(app, phone, random_string)
        if send_res:
            user_verify_code.verify_code_send = 1
            db.session.commit()
        return {"expire_in": app.config["PHONE_CODE_EXPIRE_TIME"]}


def send_email_code(app: Flask, email: str, ip: str = None, language: str = None):
    with app.app_context():
        # Check IP ban status
        if ip:
            ip_ban_key = app.config["REDIS_KEY_PREFIX_IP_BAN"] + ip
            if redis.get(ip_ban_key):
                # Development, debugging and use
                # redis.delete(ip_ban_key)
                raise_error("server.user.ipBanned")

            # Check IP sending frequency
            ip_limit_key = app.config["REDIS_KEY_PREFIX_IP_LIMIT"] + ip
            ip_send_count = redis.get(ip_limit_key)

            if ip_send_count:
                ip_send_count = int(ip_send_count)
                if ip_send_count >= int(app.config["IP_MAIL_LIMIT_COUNT"]):
                    # Ban the IP
                    redis.set(ip_ban_key, 1, ex=int(app.config["IP_BAN_TIME"]))
                    raise_error("server.user.ipBanned")
                else:
                    redis.incr(ip_limit_key)
            else:
                redis.set(ip_limit_key, 1, ex=int(app.config["IP_MAIL_LIMIT_TIME"]))

        # Check the transmission frequency limit
        email_limit_key = app.config["REDIS_KEY_PREFIX_MAIL_LIMIT"] + email
        last_send_time = redis.get(email_limit_key)

        if last_send_time:
            last_send_time = int(last_send_time)
            current_time = int(time.time())
            time_diff = current_time - last_send_time

            interval = int(app.config["MAIL_CODE_INTERVAL"])
            if time_diff < interval:
                raise_error("server.user.emailSendTooFrequent")

        # Create the email content
        msg = MIMEMultipart()
        msg["From"] = app.config["SMTP_SENDER"]
        msg["To"] = email
        msg["Subject"] = _("server.user.emailVerificationSubject")
        characters = string.digits
        random_string = "".join(random.choices(characters, k=4))
        # to set redis
        redis.set(
            app.config["REDIS_KEY_PREFIX_MAIL_CODE"] + email,
            random_string,
            ex=app.config["MAIL_CODE_EXPIRE_TIME"],
        )

        # Record the sending time of this time
        redis.set(
            email_limit_key, int(time.time()), ex=int(app.config["MAIL_CODE_INTERVAL"])
        )

        body = f"Your verification code is: {random_string}"
        msg.attach(MIMEText(body, "plain"))

        user_verify_code = create_and_commit_user_verify_code(
            mail=email,
            phone=None,
            verify_code=random_string,
            verify_code_type=2,  # 1: SMS, 2: Email
            ip=ip,
        )

        try:
            # Connect to the SMTP server
            server = smtplib.SMTP(app.config["SMTP_SERVER"], app.config["SMTP_PORT"])
            server.starttls()
            server.login(app.config["SMTP_USERNAME"], app.config["SMTP_PASSWORD"])

            # Send the email
            server.sendmail(app.config["SMTP_SENDER"], email, msg.as_string())
            server.quit()

            app.logger.info(f"Verification code sent to {email}")
            user_verify_code.verify_code_send = 1
            db.session.commit()
        except Exception as e:
            app.logger.error(f"Failed to send verification code to {email}: {str(e)}")
            raise_error("server.user.emailSendFailed")
        return {"expire_in": app.config["MAIL_CODE_EXPIRE_TIME"]}


def create_and_commit_user_verify_code(
    mail: str,
    phone: str,
    verify_code: str,
    verify_code_type: int,
    ip: str,
):
    user_verify_code = UserVerifyCode(
        phone=phone,
        mail=mail,
        verify_code=verify_code,
        verify_code_type=verify_code_type,  # 1: SMS, 2: Email
        verify_code_used=0,
        verify_code_send=0,
        user_ip=ip,
    )
    db.session.add(user_verify_code)
    db.session.commit()
    return user_verify_code


def ensure_admin_creator_and_demo_permissions(
    app: Flask, user_id: str, login_context: str | None = None
) -> None:
    """
    Ensure that an admin-login user is a creator and has demo course permissions.

    This helper is controlled by the ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO flag and
    is intended for demo/staging environments.
    """
    # Only apply when the feature flag is enabled
    if not app.config.get("ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO", False):
        return

    # Only act on explicit admin logins
    if login_context != "admin":
        return

    # Mark user as creator
    mark_user_roles(user_id, is_creator=True)

    # Grant demo course permissions if demo shifus are configured
    demo_ids = set()
    for key in ("DEMO_SHIFU_BID", "DEMO_EN_SHIFU_BID"):
        bid = get_dynamic_config(app, key)
        if bid:
            demo_ids.add(bid)

    if not demo_ids:
        # No demo courses configured; nothing more to do
        return

    full_auth_types = json.dumps(["view"])

    for shifu_bid in demo_ids:
        auth = AiCourseAuth.query.filter(
            AiCourseAuth.user_id == user_id,
            AiCourseAuth.course_id == shifu_bid,
        ).first()
        if auth:
            updated = False
            if auth.auth_type != full_auth_types:
                auth.auth_type = full_auth_types
                updated = True
            if auth.status != 1:
                auth.status = 1
                updated = True
            if updated:
                db.session.flush()
        else:
            auth = AiCourseAuth(
                course_auth_id=generate_id(app),
                user_id=user_id,
                course_id=shifu_bid,
                auth_type=full_auth_types,
                status=1,
            )
            db.session.add(auth)
            db.session.flush()

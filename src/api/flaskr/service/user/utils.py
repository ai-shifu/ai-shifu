from flask import Flask
import jwt
import time
import base64
import string
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flaskr.i18n import _

from ..common.models import raise_error
from ...dao import redis_client as redis
from captcha.image import ImageCaptcha
from flaskr.api.sms.aliyun import send_sms_code_ali
from io import BytesIO


def get_user_openid(user):
    if hasattr(user, "user_open_id"):
        return user.user_open_id
    else:
        return ""


def get_user_language(user):
    if hasattr(user, "user_language"):
        return user.user_language if user.user_language else "zh_CN"
    else:
        return "zh_CN"


# generate token
def generate_token(app: Flask, user_id: str) -> str:
    with app.app_context():
        token = jwt.encode(
            {"user_id": user_id, "time_stamp": time.time()},
            app.config["SECRET_KEY"],
            algorithm="HS256",
        )
        redis.set(
            app.config["REDIS_KEY_PREFIX_USER"] + user_id,
            token,
            ex=app.config["TOKEN_EXPIRE_TIME"],
        )
        return token


# generate image captcha
# author: yfge
def generation_img_chk(app: Flask, identifying_account: str):
    with app.app_context():
        image_captcha = ImageCaptcha()
        characters = string.ascii_uppercase + string.digits
        # Generate a random string of length 4
        random_string = "".join(random.choices(characters, k=4))
        captcha_image = image_captcha.generate_image(random_string)
        # Save the image to a BytesIO object
        buffered = BytesIO()
        captcha_image.save(buffered, format="PNG")
        app.logger.info(
            "identifying_account:"
            + identifying_account
            + " random_string:"
            + random_string
        )
        # Encode the image to base64
        img_base64 = "data:image/png;base64," + base64.b64encode(
            buffered.getvalue()
        ).decode("utf-8")
        redis.set(
            app.config["REDIS_KEY_PREFIX_CAPTCHA"] + identifying_account,
            random_string,
            ex=app.config["CAPTCHA_CODE_EXPIRE_TIME"],
        )
        return {"img": img_base64, "expire_in": app.config["CAPTCHA_CODE_EXPIRE_TIME"]}


# send sms code
def send_sms_code(app: Flask, phone: str, ip: str = None):
    with app.app_context():
        # Check IP ban status
        if ip:
            ip_ban_key = app.config["REDIS_KEY_PREFIX_IP_BAN"] + ip
            if redis.get(ip_ban_key):
                # Development, debugging and use
                # redis.delete(ip_ban_key)
                raise_error("USER.IP_BANNED")

            # Check IP sending frequency
            ip_limit_key = app.config["REDIS_KEY_PREFIX_IP_LIMIT"] + ip
            ip_send_count = redis.get(ip_limit_key)

            if ip_send_count:
                ip_send_count = int(ip_send_count)
                if ip_send_count >= int(app.config["IP_SMS_LIMIT_COUNT"]):
                    # Ban the IP
                    redis.set(ip_ban_key, 1, ex=int(app.config["IP_BAN_TIME"]))
                    raise_error("USER.IP_BANNED")
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
                raise_error("USER.SMS_SEND_TOO_FREQUENT")

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

        send_sms_code_ali(app, phone, random_string)
        return {"expire_in": app.config["PHONE_CODE_EXPIRE_TIME"]}


def send_email_code(app: Flask, email: str, ip: str = None):
    with app.app_context():
        # Check IP ban status
        if ip:
            ip_ban_key = app.config["REDIS_KEY_PREFIX_IP_BAN"] + ip
            if redis.get(ip_ban_key):
                # Development, debugging and use
                # redis.delete(ip_ban_key)
                raise_error("USER.IP_BANNED")

            # Check IP sending frequency
            ip_limit_key = app.config["REDIS_KEY_PREFIX_IP_LIMIT"] + ip
            ip_send_count = redis.get(ip_limit_key)

            if ip_send_count:
                ip_send_count = int(ip_send_count)
                if ip_send_count >= int(app.config["IP_MAIL_LIMIT_COUNT"]):
                    # Ban the IP
                    redis.set(ip_ban_key, 1, ex=int(app.config["IP_BAN_TIME"]))
                    raise_error("USER.IP_BANNED")
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
                raise_error("USER.EMAIL_SEND_TOO_FREQUENT")

        # Create the email content
        msg = MIMEMultipart()
        msg["From"] = app.config["SMTP_SENDER"]
        msg["To"] = email
        msg["Subject"] = _("EMAIL_VERIFICATION_SUBJECT")
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

        try:
            # Connect to the SMTP server
            server = smtplib.SMTP(app.config["SMTP_SERVER"], app.config["SMTP_PORT"])
            server.starttls()
            server.login(app.config["SMTP_USERNAME"], app.config["SMTP_PASSWORD"])

            # Send the email
            server.sendmail(app.config["SMTP_SENDER"], email, msg.as_string())
            server.quit()

            app.logger.info(f"Verification code sent to {email}")
        except Exception as e:
            app.logger.error(f"Failed to send verification code to {email}: {str(e)}")
            raise_error("USER.EMAIL_SEND_FAILED")
        return {"expire_in": app.config["MAIL_CODE_EXPIRE_TIME"]}

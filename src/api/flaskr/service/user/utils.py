from flask import Flask
import jwt
import time
import base64
import string
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
            app.config["REDIS_KEY_PRRFIX_USER"] + user_id,
            token,
            ex=app.config["TOKEN_EXPIRE_TIME"],
        )
        return token


# generate image captcha
# author: yfge
def generation_img_chk(app: Flask, mobile: str):
    with app.app_context():
        image_captcha = ImageCaptcha()
        characters = string.ascii_uppercase + string.digits
        # Generate a random string of length 4
        random_string = "".join(random.choices(characters, k=4))
        captcha_image = image_captcha.generate_image(random_string)
        # Save the image to a BytesIO object
        buffered = BytesIO()
        captcha_image.save(buffered, format="PNG")
        app.logger.info("mobile:" + mobile + " random_string:" + random_string)
        # Encode the image to base64
        img_base64 = "data:image/png;base64," + base64.b64encode(
            buffered.getvalue()
        ).decode("utf-8")
        redis.set(
            app.config["REDIS_KEY_PRRFIX_CAPTCHA"] + mobile,
            random_string,
            ex=app.config["CAPTCHA_CODE_EXPIRE_TIME"],
        )
        return {"img": img_base64, "expire_in": app.config["CAPTCHA_CODE_EXPIRE_TIME"]}


# send sms code
def send_sms_code(app: Flask, phone: str, chekcode: str):
    with app.app_context():
        check_save = redis.get(app.config["REDIS_KEY_PRRFIX_CAPTCHA"] + phone)
        if check_save is None:
            raise_error("USER.CHECK_CODE_EXPIRED")
        check_save_str = str(check_save, encoding="utf-8")
        app.logger.info("check_save_str:" + check_save_str + " chekcode:" + chekcode)
        if chekcode.lower() != check_save_str.lower():
            raise_error("USER.CHECK_CODE_ERROR")
        else:
            characters = string.digits
            # Generate a random string of length 4
            random_string = "".join(random.choices(characters, k=4))
            # 发送短信验证码
            redis.set(
                app.config["REDIS_KEY_PRRFIX_PHONE_CODE"] + phone,
                random_string,
                ex=app.config["PHONE_CODE_EXPIRE_TIME"],
            )
            send_sms_code_ali(app, phone, random_string)
            return {"expire_in": app.config["PHONE_CODE_EXPIRE_TIME"]}


def send_email_code(app: Flask, email: str, code: str, checkcode: str):
    with app.app_context():
        # Create the email content
        msg = MIMEMultipart()
        msg["From"] = app.config["SMTP_SENDER"]
        msg["To"] = email
        msg["Subject"] = "AI-Shifu:Your Verification Code"

        body = f"Your verification code is: {code}"
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

import base64
from io import BytesIO
import random
import string
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Date
from sympy import Q

from ...service.common.dtos import UserInfo, UserToken
from ...api.aliyun import send_sms_code_ali
from ...common.swagger import register_schema_to_swagger
from ...service.common.models import CHECK_CODE_ERROR, CHECK_CODE_EXPIRED, SMS_CHECK_ERROR, SMS_SEND_EXPIRED
from ...service.common.dtos import USE_STATE_VALUES, USER_STATE_REGISTERED, USER_STATE_UNTEGISTERED
from ...dao import db,redis_client as redis
from ...api.sendcloud import send_email
import uuid
from .models import AdminUser as User    
import hashlib
from ..common import USER_NOT_FOUND,USER_PASSWORD_ERROR,USER_ALREADY_EXISTS,USER_TOKEN_EXPIRED,USER_NOT_LOGIN,OLD_PASSWORD_ERROR,RESET_PWD_CODE_EXPIRED,RESET_PWD_CODE_ERROR
import jwt
import time
from captcha.image import ImageCaptcha 
import oss2



FIX_CHECK_CODE = "0615"



def create_new_user(app:Flask, username: str, name: str, raw_password: str, email: str, mobile: str)->UserToken:
    with app.app_context():
        user = User.query.filter((User.username == username) | (User.email == email) | (User.mobile == mobile)).first()
        if user:
            raise USER_ALREADY_EXISTS
        user_id = str(uuid.uuid4()).replace('-', '')
        password_hash = hashlib.md5((user_id + raw_password).encode()).hexdigest()
        new_user = User(user_id=user_id, username=username, name=name, password_hash=password_hash, email=email, mobile=mobile,default_model=app.config["OPENAI_DEFAULT_MODEL"])
        db.session.add(new_user)
        db.session.commit()
        token = generate_token(app,user_id=user_id)
        return UserToken(
            UserInfo(user_id=user_id, username=username, name=name, email=email, mobile=mobile,model=new_user.default_model,user_state=new_user.user_state),
            token=token)
def generate_token(app:Flask, user_id: str) -> str:
    with app.app_context():
        token = jwt.encode({'user_id': user_id,"time_stamp": time.time()}, app.config['SECRET_KEY'], algorithm='HS256')
        redis.set(app.config["REDIS_KEY_PRRFIX_USER"] + user_id, token,ex=app.config['TOKEN_EXPIRE_TIME'])
        return token

def verify_user(app:Flask, login: str, raw_password: str) ->UserToken:
    with app.app_context():
        user = User.query.filter((User.username == login) | (User.email == login) | (User.mobile == login)).first()
        if user:
            password_hash = hashlib.md5((user.user_id + raw_password).encode()).hexdigest()
            if password_hash == user.password_hash:
                token = generate_token(app,user_id=user.user_id)  
                return UserToken(UserInfo(user_id=user.user_id, username=user.username, name=user.name, email=user.email, mobile=user.mobile,model=user.default_model,user_state=user.user_state),token=token)
            else:
                raise USER_PASSWORD_ERROR
        else:
            raise USER_NOT_FOUND
def validate_user(app:Flask, token: str) -> UserInfo:
    with app.app_context():
        if(token == None):
            raise USER_NOT_LOGIN
        try:
            user_id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['user_id']
            app.logger.info("user_id:"+user_id)
            redis_key = app.config["REDIS_KEY_PRRFIX_USER"] + user_id
            app.logger.info("redis_key:"+redis_key)

            redis_token = redis.get(app.config["REDIS_KEY_PRRFIX_USER"] + user_id);

            if(redis_token == None):
                raise USER_TOKEN_EXPIRED 
            set_token = str(redis.get(app.config["REDIS_KEY_PRRFIX_USER"] + user_id),encoding="utf-8")
            if set_token == token:
                user = User.query.filter(User.user_id==user_id).first()
                if user:
                    return UserInfo(user_id=user.user_id, username=user.username, name=user.name, email=user.email, mobile=user.mobile,model=user.default_model, user_state=user.user_state)
                else:
                    raise USER_TOKEN_EXPIRED
            else:
                raise USER_TOKEN_EXPIRED 
        except (jwt.exceptions.ExpiredSignatureError):
            raise USER_TOKEN_EXPIRED
        except (jwt.exceptions.DecodeError):
            raise USER_NOT_FOUND

def update_user_info(app:Flask,user:UserInfo,name,email=None,mobile=None)->UserInfo:
    with app.app_context():
        if user:
            dbuser = User.query.filter_by(user_id=user.user_id).first()
            dbuser.name = name
            if(email != None):
                dbuser.email = email
            if(mobile != None):
                dbuser.mobile = mobile
            db.session.commit()
            return UserInfo(user_id=user.user_id, username=user.username, name=user.name, email=user.email, mobile=user.mobile,model=dbuser.default_model,user_state=dbuser.user_state)
        else:
            raise USER_NOT_FOUND

def change_user_passwd(app:Flask,user:UserInfo,oldpwd,newpwd)->UserInfo:
    with app.app_context():
        if user:
            user = User.query.filter_by(user_id=user.user_id).first()
            password_hash = hashlib.md5((user.user_id + oldpwd).encode()).hexdigest()
            if password_hash == user.password_hash:
                user.password_hash = hashlib.md5((user.user_id + newpwd).encode()).hexdigest()
                db.session.commit()
                return UserInfo(user_id=user.user_id, username=user.username, name=user.name, email=user.email, mobile=user.mobile,model=user.default_model,user_state=user.user_state)
            else:
                raise OLD_PASSWORD_ERROR
        else:
            raise USER_NOT_FOUND
def get_user_info(app:Flask,user_id:str)->UserInfo:
    with app.app_context():
        user = User.query.filter_by(user_id=user_id).first()
        if user:
            return UserInfo(user_id=user.user_id, username=user.username, name=user.name, email=user.email, mobile=user.mobile,model=user.default_model,user_state=user.user_state)
        else:
            raise USER_NOT_FOUND


def require_reset_pwd_code(app:Flask,login:str):
    with app.app_context():
        user = User.query.filter((User.username == login) | (User.email == login) | (User.mobile == login)).first()
        if user:
            code = random.randint(0,9999) 
            redis.set(app.config["REDIS_KEY_PRRFIX_RESET_PWD"] + user.user_id, code,ex=app.config['RESET_PWD_CODE_EXPIRE_TIME'])
            send_email(app,'小卡AI助理',user.email,user.email,"重置密码","您的重置密码验证码为："+str(code))
            return True
        else:
            raise USER_NOT_FOUND
        
def reset_pwd(app:Flask,login:str,code:int,newpwd:str):
    with app.app_context():
        user = User.query.filter((User.username == login) | (User.email == login) | (User.mobile == login)).first()
        if user:
            redis_code = redis.get(app.config["REDIS_KEY_PRRFIX_RESET_PWD"] + user.user_id);
            if(redis_code == None):
                raise RESET_PWD_CODE_EXPIRED 
            set_code = int(str(redis_code,encoding="utf-8"))
            app.logger.info("code:"+str(code)+" set_code:"+str(set_code))
            if str(set_code) == str(code):
                app.logger.info("code:"+str(code)+" set_code:"+str(set_code))
                user.password_hash = hashlib.md5((user.user_id + newpwd).encode()).hexdigest()
                db.session.commit()
                app.logger.info("update password")
                return True
            else:
                raise RESET_PWD_CODE_ERROR 
        else:
            raise USER_NOT_FOUND 
    

# 生成图片验证码
def generation_img_chk(app:Flask,mobile:str):
    with app.app_context():
        image_captcha = ImageCaptcha()
        characters = string.ascii_uppercase + string.digits
        # Generate a random string of length 4
        random_string = ''.join(random.choices(characters, k=4))
        captcha_image = image_captcha.generate_image(random_string)
        # Save the image to a BytesIO object
        buffered = BytesIO()
        captcha_image.save(buffered, format="PNG")
        app.logger.info("mobile:"+mobile+" random_string:"+random_string)
        # Encode the image to base64
        img_base64 = 'data:image/png;base64,'+base64.b64encode(buffered.getvalue()).decode('utf-8')
        redis.set(app.config["REDIS_KEY_PRRFIX_CAPTCHA"] + mobile, random_string,ex=app.config['CAPTCHA_CODE_EXPIRE_TIME'])
        return {
            "img":img_base64,
            "expire_in":app.config['CAPTCHA_CODE_EXPIRE_TIME']
        }

# 发送短信验证码
def send_sms_code(app:Flask,phone:str,chekcode:str):
    with app.app_context():
        check_save = redis.get(app.config["REDIS_KEY_PRRFIX_CAPTCHA"] + phone)
        if check_save == None:
            raise CHECK_CODE_EXPIRED
        check_save_str = str(check_save,encoding="utf-8") 
        app.logger.info("check_save_str:"+check_save_str+" chekcode:"+chekcode)
        if chekcode.lower() != check_save_str.lower():
            raise CHECK_CODE_ERROR
        else:
            characters =  string.digits
            # Generate a random string of length 4
            random_string = ''.join(random.choices(characters, k=4))
            # 发送短信验证码
            redis.set(app.config["REDIS_KEY_PRRFIX_PHONE_CODE"] + phone, random_string,ex=app.config['PHONE_CODE_EXPIRE_TIME'])
            send_sms_code_ali(app,phone,random_string)
            return {
                "expire_in":app.config['PHONE_CODE_EXPIRE_TIME']
            } 

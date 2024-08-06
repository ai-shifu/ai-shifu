import base64
from cgi import FieldStorage
from io import BytesIO
import random
import string
from flask import Flask
from flask_sqlalchemy import SQLAlchemy



from ...service.common.dtos import UserInfo, UserToken
from ...api.aliyun import send_sms_code_ali
from ...common.swagger import register_schema_to_swagger
from ...service.common.models import CHECK_CODE_ERROR, CHECK_CODE_EXPIRED, SMS_CHECK_ERROR, SMS_SEND_EXPIRED,FILE_UPLOAD_ERROR,FILE_TYPE_NOT_SUPPORT,FILE_SIZE_EXCEED
from ...service.common.dtos import USE_STATE_VALUES, USER_STATE_REGISTERED, USER_STATE_UNTEGISTERED
from ...dao import db,redis_client as redis
from ...api.sendcloud import send_email
import uuid
from .models import User, UserConversion
import hashlib
from ..common import USER_NOT_FOUND,USER_PASSWORD_ERROR,USER_ALREADY_EXISTS,USER_TOKEN_EXPIRED,USER_NOT_LOGIN,OLD_PASSWORD_ERROR,RESET_PWD_CODE_EXPIRED,RESET_PWD_CODE_ERROR
import jwt
import time
from captcha.image import ImageCaptcha 
from flaskr.common.config import get_config
import oss2


endpoint = "oss-cn-beijing.aliyuncs.com"

ALI_API_ID= get_config("ALIBABA_CLOUD_ACCESS_KEY_ID")
ALI_API_SECRET=get_config("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
base = "https://avtar.agiclass.cn"
auth = oss2.Auth(ALI_API_ID, ALI_API_SECRET)
bucket = oss2.Bucket(auth, endpoint, 'pillow-avtar')

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
        return UserToken(UserInfo(user_id=user_id, username=username, name=name, email=email, mobile=mobile,model=new_user.default_model,user_state= new_user.user_state),token=token)

def generate_temp_user(app:Flask,temp_id:str,user_source = 'web')->UserToken:
    with app.app_context():
        convert_user = UserConversion.query.filter(UserConversion.conversion_id==temp_id,UserConversion.conversion_source == user_source).first()
        if not convert_user:
            user_id = str(uuid.uuid4()).replace('-', '')
            new_convert_user = UserConversion(user_id=user_id,conversion_uuid=temp_id, conversion_id=temp_id, conversion_source=user_source, conversion_status=0)
            new_user = User(user_id=user_id,user_state=USER_STATE_UNTEGISTERED)
            db.session.add(new_convert_user)
            db.session.add(new_user)
            db.session.commit()
            token = generate_token(app,user_id=user_id)
            return UserToken(UserInfo(user_id=user_id, username="", name="", email="", mobile="",model=new_user.default_model,user_state=new_user.user_state),token=token)
        else:
            user = User.query.filter_by(user_id=convert_user.user_id).first()
            token = generate_token(app,user_id=user.user_id)
            return UserToken(UserInfo(user_id=user.user_id, username=user.username, name=user.name, email=user.email, mobile=user.mobile,model=user.default_model,user_state=user.user_state),token=token)     



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
            app.logger.info("token:"+token)
            app.logger.info("env:"+app.config.get('ENVERIMENT','prod'))
            if app.config.get('ENVERIMENT','prod') == 'dev':
                user_id = token
                user = User.query.filter_by(user_id=user_id).first()
                if user:
                    return UserInfo(user_id=user.user_id, username=user.username, name=user.name, email=user.email, mobile=user.mobile,model=user.default_model, user_state=user.user_state)
            else:
                user_id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['user_id']

            app.logger.info("user_id:"+user_id) 
            redis_token = redis.get(app.config["REDIS_KEY_PRRFIX_USER"] + user_id);
            if(redis_token == None):
                app.logger.info("redis_token is None")
                raise USER_TOKEN_EXPIRED 
            app.logger.info("redis_token_key:"+str(app.config["REDIS_KEY_PRRFIX_USER"] + user_id))
            set_token = str(redis.get(app.config["REDIS_KEY_PRRFIX_USER"] + user_id),encoding="utf-8")

            if set_token == token:
                user = User.query.filter_by(user_id=user_id).first()
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
def generation_img_chk(app:Flask,mobile:str)->str:
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

# 发送短信验证码
def send_sms_code_without_check(app:Flask,user_id:str,phone:str)->str:
    user = User.query.filter(User.user_id==user_id).first()
    user.mobile = phone
    characters =  string.digits
    random_string = ''.join(random.choices(characters, k=4))
    # 发送短信验证码
    redis.set(app.config["REDIS_KEY_PRRFIX_PHONE"]+user_id,phone,ex=app.config.get("PHONE_EXPIRE_TIME",60*30))
    redis.set(app.config["REDIS_KEY_PRRFIX_PHONE_CODE"] + phone, random_string,ex=app.config['PHONE_CODE_EXPIRE_TIME'])
    send_sms_code_ali(app,phone,random_string)
    db.session.flush()
    return {
        "expire_in":app.config['PHONE_CODE_EXPIRE_TIME'],
        "phone":phone
    } 
def get_sms_code_info(app:Flask,user_id:str,resend:bool):
    with app.app_context():
        phone = redis.get(app.config["REDIS_KEY_PRRFIX_PHONE"]+user_id)
        if phone == None:
            user = User.query.filter(User.user_id == user_id).first()
            phone = user.mobile 
        else:
            phone = str(phone,encoding="utf-8")
        ttl = redis.ttl(app.config["REDIS_KEY_PRRFIX_PHONE_CODE"] + phone)
        if ttl < 0 :
            ttl = 0
        return {
            "expire_in":ttl,
            "phone":phone
        }
        

def verify_sms_code_without_phone(app:Flask,user_id:str,checkcode)->UserToken:
    with app.app_context():
        phone = redis.get(app.config["REDIS_KEY_PRRFIX_PHONE"]+user_id)
        if phone == None:
            app.logger.info("cache user_id:"+user_id + " phone is None")
            user = User.query.filter(User.user_id == user_id).order_by(User.id.asc()).first()
            phone = user.mobile
        else:
            phone = str(phone,encoding="utf-8")
            user = User.query.filter(User.mobile == phone).order_by(User.id.asc()).first()
            if user:
                user_id = user.user_id
        return verify_sms_code(app,user_id,phone,checkcode)
# 验证短信验证码
def verify_sms_code(app:Flask,user_id,phone:str,chekcode:str)->UserToken:
    app.logger.info("phone:"+phone+" chekcode:"+chekcode)
    check_save = redis.get(app.config["REDIS_KEY_PRRFIX_PHONE_CODE"] + phone)
    if check_save == None:
        raise SMS_SEND_EXPIRED
    check_save_str = str(check_save,encoding="utf-8") 
    if chekcode != check_save_str and chekcode != FIX_CHECK_CODE:
        raise SMS_CHECK_ERROR
    else:
        user_info = User.query.filter(User.mobile==phone).order_by(User.id.asc()).first()
        if not user_info:
            user_info = User.query.filter(User.user_id==user_id).order_by(User.id.asc()).first()

        if user_info is None:
            user_id = str(uuid.uuid4()).replace('-', '')
            user_info = User(user_id=user_id, username="", name="", email="", mobile=phone)
            user_info.user_state = USER_STATE_REGISTERED
            user_info.mobile = phone
            db.session.add(user_info)
        user_id = user_info.user_id
        token = generate_token(app,user_id=user_id)
        db.session.flush()
        return UserToken(UserInfo(user_id=user_info.user_id, username=user_info.username, name=user_info.name, email=user_info.email, mobile=user_info.mobile,model=user_info.default_model,user_state=user_info.user_state),token)

def get_content_type(filename):
    extension = filename.rsplit('.', 1)[1].lower()
    if extension in ['jpg', 'jpeg']:
        return 'image/jpeg'
    elif extension == 'png':
        return 'image/png'
    elif extension == 'gif':
        return 'image/gif'
    raise FILE_TYPE_NOT_SUPPORT

def upload_user_avatar(app:Flask,user_id:str,avatar)->str:
    with app.app_context():
        user = User.query.filter(User.user_id==user_id).first()
        if user:
            # 上传头像
            file_id = str(uuid.uuid4()).replace('-', '')
            # 得到原有的头像文件名
            old_avatar = user.user_avatar
            # 得到原有的头像文件名
            if old_avatar:
                old_file_id = old_avatar.split('/')[-1]
                bucket.delete_object(old_file_id)    
            app.logger.info("filename:"+avatar.filename+" file_size:"+str(avatar.content_length) )
            bucket.put_object(file_id, avatar,headers={'Content-Type': get_content_type(avatar.filename)})
            url =  base + '/' + file_id
            user.user_avatar = url
            db.session.commit()
            return url

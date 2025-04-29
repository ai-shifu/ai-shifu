import hashlib
import uuid
from flask import Flask

from ..common.dtos import UserInfo, UserToken
from ..common.models import raise_error
from .models import AdminUser as User
from .utils import generate_token
from ...dao import db


def create_new_admin_user(
    app: Flask, username: str, name: str, raw_password: str, email: str, mobile: str
) -> UserToken:
    with app.app_context():
        user = User.query.filter(
            (User.username == username)
            | (User.email == email)
            | (User.mobile == mobile)
        ).first()
        if user:
            raise_error("USER.USER_ALREADY_EXISTS")
        user_id = str(uuid.uuid4()).replace("-", "")
        password_hash = hashlib.md5((user_id + raw_password).encode()).hexdigest()
        new_user = User(
            user_id=user_id,
            username=username,
            name=name,
            password_hash=password_hash,
            email=email,
            mobile=mobile,
        )
        db.session.add(new_user)
        db.session.commit()
        token = generate_token(app, user_id=user_id)
        return UserToken(
            UserInfo(
                user_id=user_id,
                username=username,
                name=name,
                email=email,
                mobile=mobile,
                user_state=new_user.user_state,
                wx_openid="",
                language="zh_CN",
                has_password=True,
            ),
            token=token,
        )

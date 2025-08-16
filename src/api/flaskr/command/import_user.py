from flask import Flask
from flaskr.service.user import generate_temp_user
from flaskr.service.order import init_buy_record
from flaskr.service.order.coupon_funcs import use_coupon_code
from flaskr.service.user.models import User
from flaskr.service.common.dtos import USER_STATE_REGISTERED
import uuid
from flaskr.dao import db


def import_user(
    app: Flask, mobile, course_id, discount_code="web", user_nick_name=None
):
    """Import user and enable course"""
    app.logger.info(f"import_user: {mobile}, {course_id}")
    with app.app_context():

        user = User.query.filter_by(mobile=mobile).first()

        if not user:
            temp_id = str(uuid.uuid4()).replace("-", "")
            user = generate_temp_user(app, temp_id)
            # update user info
            user = User.query.filter_by(user_id=user.userInfo.user_id).first()
            user.mobile = mobile
            user.user_state = USER_STATE_REGISTERED
            if user_nick_name:
                user.name = user_nick_name
            db.session.commit()
            user_id = user.user_id
        else:
            user_id = user.user_id
        order = init_buy_record(app, user_id, course_id)
        use_coupon_code(app, user_id, discount_code, order.order_id)

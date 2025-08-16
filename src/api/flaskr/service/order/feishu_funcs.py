from flask import Flask
from flaskr.service.user.models import User, UserConversion
from flaskr.service.common import send_notify


def send_feishu_coupon_code(
    app: Flask, user_id, discount_code, discount_name, discount_value
):
    with app.app_context():
        user_info = User.query.filter(User.user_id == user_id).first()
        title = "优惠码通知"
        msgs = []
        msgs.append("手机号：{}".format(user_info.mobile))
        msgs.append("昵称：{}".format(user_info.name))
        msgs.append("优惠码：{}".format(discount_code))
        msgs.append("优惠名称：{}".format(discount_name))
        msgs.append("优惠额度：{}".format(discount_value))
        user_convertion = UserConversion.query.filter(
            UserConversion.user_id == user_id
        ).first()
        channel = ""
        if user_convertion:
            channel = user_convertion.conversion_source
        msgs.append("渠道：{}".format(channel))
        send_notify(app, title, msgs)

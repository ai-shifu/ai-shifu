from flask import Flask
from .models import FeedBack
from ...dao import db
from flaskr.api.doc.feishu import send_notify
from flaskr.service.user.models import User


def submit_feedback(app: Flask, user_id: str, feedback: str, mail: str):
    with app.app_context():
        feedback_item = FeedBack(user_id=user_id, feedback=feedback)
        user = User.query.filter(User.user_id == user_id).first()
        if user:
            send_notify(
                app,
                "有用户提交反馈,注意跟进",
                [
                    f"用户ID：{user_id}",
                    f"用户昵称：{user.name}",
                    f"用户手机：{user.mobile}",
                    f"用户反馈：{feedback}",
                ],
            )
        else:
            send_notify(
                app,
                "有用户提交登录反馈,注意跟进",
                [f"E-mail：{mail}", f"反馈：{feedback}"],
            )
        db.session.add(feedback_item)
        db.session.commit()
        return feedback_item.id

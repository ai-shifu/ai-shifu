from flask import Flask
from .models import FeedBack
from ...dao import db
from flaskr.api.doc.feishu import send_notify
from flaskr.service.user.models import User


def submit_feedback(app: Flask, user_id: str, feedback: str):
    with app.app_context():
        feedback = FeedBack(user_id=user_id, feedback=feedback)
        user = User.query.filter(User.user_id == user_id).first()
        if user:
            send_notify(
                app,
                "用户反馈",
                [
                    f"用户ID：{user_id}",
                    f"用户昵称：{user.name}",
                    f"用户手机：{user.mobile}",
                    f"用户反馈：{feedback}",
                ],
            )
        db.session.add(feedback)
        db.session.commit()
        return feedback.id

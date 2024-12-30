from flask import Flask
from ...dao import db
from .models import RiskControlResult


def add_risk_control_result(
    app: Flask,
    chat_id,
    user_id,
    text,
    check_vendor,
    check_result,
    check_resp,
    is_pass,
    check_strategy,
):
    with app.app_context():
        risk_control_result = RiskControlResult(
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            check_vendor=check_vendor,
            check_result=check_result,
            check_resp=check_resp,
            is_pass=is_pass,
            check_strategy=check_strategy,
        )
        db.session.add(risk_control_result)
        db.session.commit()
        return risk_control_result.id

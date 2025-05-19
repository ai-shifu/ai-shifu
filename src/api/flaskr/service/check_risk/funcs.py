from flask import Flask
from ...dao import db
from .models import RiskControlResult
from flaskr.api.check import check_text, CHECK_RESULT_REJECT, CHECK_RESULT_PASS
from flaskr.service.common.models import raise_error
from datetime import datetime


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


def check_text_with_risk_control(app: Flask, check_id, user_id, text):
    log_id = check_id + datetime.now().strftime("%Y%m%d%H%M%S")

    res = check_text(app, log_id, text, user_id)
    add_risk_control_result(
        app,
        check_id,
        user_id,
        text,
        res.provider,
        res.check_result,
        str(res.raw_data),
        1 if res.check_result == CHECK_RESULT_PASS else 0,
        "check_text",
    )
    if res.check_result == CHECK_RESULT_REJECT:
        raise_error("CHECK.CHECK_RISK_CONTROL_REJECT")

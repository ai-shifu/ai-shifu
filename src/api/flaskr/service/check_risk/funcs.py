"""Implement business operations for risk control."""

from flask import Flask
from flaskr.api.check import CHECK_RESULT_PASS, CHECK_RESULT_REJECT, check_text
from flaskr.api.check.dto import CheckResultDTO
from flaskr.dao import db
from flaskr.service.common.models import raise_error
from flaskr.util.datetime import now_utc

from .models import RiskControlResult


def add_risk_control_result(
    app: Flask,
    chat_id: object,
    user_id: object,
    text: object,
    check_vendor: object,
    check_result: object,
    check_resp: object,
    is_pass: object,
    check_strategy: object,
) -> int:
    """Add risk control result."""
    with app.app_context():
        risk_control_result = RiskControlResult(
            chat_id=chat_id,
            user_id=user_id,
            text=text or "",
            check_vendor=check_vendor,
            check_result=check_result,
            check_resp=check_resp,
            is_pass=is_pass,
            check_strategy=check_strategy,
        )
        db.session.add(risk_control_result)
        db.session.commit()
        return risk_control_result.id


def check_text_with_risk_control(
    app: Flask, check_id: str, user_id: str, text: str | None
) -> CheckResultDTO:
    """Check text with risk control."""
    if text is None or text == "":
        return CheckResultDTO(
            check_result=CHECK_RESULT_PASS,
            risk_labels=[],
            risk_label_ids=[],
            provider="skip_empty",
            raw_data={"reason": "empty_text"},
        )

    log_id = check_id + now_utc().strftime("%Y%m%d%H%M%S")

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
        raise_error("server.check.checkRiskControlReject")
    return None

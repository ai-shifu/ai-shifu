"""Content risk-check provider integrations."""

from flask import Flask

from .dto import (
    CHECK_RESULT_PASS,
    CHECK_RESULT_REJECT,
    CHECK_RESULT_REVIEW,
    CHECK_RESULT_UNCONF,
    CHECK_RESULT_UNKNOWN,
    CheckResultDTO,
)
from .ilivedata import ilivedata_check
from .yidun import yidun_check

__all__ = [
    "CHECK_RESULT_PASS",
    "CHECK_RESULT_REJECT",
    "CHECK_RESULT_REVIEW",
    "CHECK_RESULT_UNCONF",
]


def check_text(app: Flask, data_id: str, text: str, user_id: str) -> CheckResultDTO:
    check_provider = app.config.get("CHECK_PROVIDER")
    if check_provider == "ilivedata":
        return ilivedata_check(app, data_id, text, user_id)
    if check_provider == "yidun":
        return yidun_check(app, data_id, text, user_id)
    app.logger.warning("check_provider %s not supported", check_provider)
    return CheckResultDTO(
        check_result=CHECK_RESULT_UNKNOWN,
        risk_labels=[],
        risk_label_ids=[],
        provider=check_provider,
        raw_data={},
    )

from flask import Flask
from .ilivedata import ilivedata_check
from .yidun import yidun_check
from .dto import (
    CheckResultDTO,
    CHECK_RESULT_UNKNOWN,
    CHECK_RESULT_PASS,  # noqa
    CHECK_RESULT_REJECT,  # noqa
    CHECK_RESULT_REVIEW,  # noqa
    CHECK_RESULT_UNCONF,  # noqa
)  # noqa

__all__ = [
    "CHECK_RESULT_PASS",
    "CHECK_RESULT_REJECT",
    "CHECK_RESULT_REVIEW",
    "CHECK_RESULT_UNCONF",
]


def check_text(app: Flask, data_id: str, text: str, user_id: str):

    check_provider = app.config.get("CHECK_PROVIDER")
    if check_provider == "ilivedata":
        return ilivedata_check(app, data_id, text, user_id)
    elif check_provider == "yidun":
        return yidun_check(app, data_id, text, user_id)
    else:
        app.logger.warning(f"check_provider {check_provider} not supported")
        return CheckResultDTO(
            check_result=CHECK_RESULT_UNKNOWN,
            risk_labels=[],
            risk_label_ids=[],
            provider=check_provider,
            raw_data={},
        )

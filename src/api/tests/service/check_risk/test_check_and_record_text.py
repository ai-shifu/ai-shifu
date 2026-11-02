"""Verify moderation verdicts are recorded with their business-key linkage."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from flaskr.api.check import CHECK_RESULT_PASS, CHECK_RESULT_REJECT
from flaskr.api.check.dto import CheckResultDTO
from flaskr.service.check_risk import funcs
from flaskr.service.check_risk.models import RiskControlResult
from flaskr.service.common.models import AppError

if TYPE_CHECKING:
    from flask import Flask


def _verdict(check_result: str) -> CheckResultDTO:
    return CheckResultDTO(
        check_result=check_result,
        risk_labels=[],
        risk_label_ids=[],
        provider="test-provider",
        raw_data={"verdict": check_result},
    )


def test_check_and_record_text_sends_log_id_but_links_audit_to_check_id(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []

    def fake_check_text(_app: object, data_id: str, *_args: object) -> object:
        sent.append(data_id)
        return _verdict(CHECK_RESULT_REJECT)

    monkeypatch.setattr(funcs, "check_text", fake_check_text)
    with app.app_context():
        result = funcs.check_and_record_text(
            app, "check-log-id", "user-1", "text", "strategy-x", log_id="provider-id"
        )
        row = RiskControlResult.query.filter_by(chat_id="check-log-id").one()

    assert sent == ["provider-id"]
    assert result.check_result == CHECK_RESULT_REJECT
    assert (row.user_id, row.text, row.check_vendor, row.check_result) == (
        "user-1",
        "text",
        "test-provider",
        CHECK_RESULT_REJECT,
    )
    assert row.check_resp == str({"verdict": CHECK_RESULT_REJECT})
    assert (row.is_pass, row.check_strategy) == (0, "strategy-x")


def test_check_text_with_risk_control_records_then_rejects(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []

    def fake_check_text(_app: object, data_id: str, *_args: object) -> object:
        sent.append(data_id)
        return _verdict(CHECK_RESULT_REJECT)

    monkeypatch.setattr(funcs, "check_text", fake_check_text)
    with app.app_context():
        with pytest.raises(AppError):
            funcs.check_text_with_risk_control(app, "shifu-risk", "user-2", "bad")
        row = RiskControlResult.query.filter_by(chat_id="shifu-risk").one()

    assert len(sent) == 1
    assert sent[0].startswith("shifu-risk")
    assert len(sent[0]) == len("shifu-risk") + len("YYYYmmddHHMMSS")
    assert (row.is_pass, row.check_strategy) == (0, "check_text")


def test_check_text_with_risk_control_records_pass_verdict(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(funcs, "check_text", lambda *_a: _verdict(CHECK_RESULT_PASS))
    with app.app_context():
        assert (
            funcs.check_text_with_risk_control(app, "shifu-pass", "user-3", "ok")
            is None
        )
        row = RiskControlResult.query.filter_by(chat_id="shifu-pass").one()

    assert (row.is_pass, row.check_result) == (1, CHECK_RESULT_PASS)

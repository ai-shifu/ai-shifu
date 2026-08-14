from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from flaskr.api.check import CHECK_RESULT_UNKNOWN
from flaskr.dao import db
from flaskr.service.check_risk.models import RiskControlResult
from flaskr.service.common.models import AppException
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD
from flaskr.service.profile import learner_profile_optimizer as optimizer
from flaskr.service.user.models import UserInfo, UserOnboardingState
from flaskr.service.user.repository import create_user_entity

PROFILE_UPDATED_AT = datetime(2026, 8, 14, 8, 30, tzinfo=timezone.utc)
STATE_COMPLETED_AT = datetime(2026, 8, 14, 8, 45, tzinfo=timezone.utc)


def _create_profile_state(user_bid: str) -> None:
    create_user_entity(
        user_bid=user_bid,
        identify=user_bid,
        nickname="Existing nickname",
        language="zh-CN",
        learner_profile="Existing profile",
        learner_profile_updated_at=PROFILE_UPDATED_AT,
    )
    db.session.add(
        UserOnboardingState(
            user_bid=user_bid,
            scene_key="profile_onboarding",
            version="profile-v2",
            status="completed",
            trigger_source="settings",
            completed_at=STATE_COMPLETED_AT,
        )
    )
    db.session.commit()


def _snapshot_profile_state(user_bid: str) -> tuple:
    user = UserInfo.query.filter_by(user_bid=user_bid).one()
    state = UserOnboardingState.query.filter_by(
        user_bid=user_bid,
        scene_key="profile_onboarding",
        version="profile-v2",
    ).one()
    return (
        user.learner_profile,
        user.learner_profile_updated_at,
        user.nickname,
        state.status,
        state.trigger_source,
        state.completed_at,
    )


def _successful_llm(raw_output: str, captured: dict):
    def invoke(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        yield SimpleNamespace(result=raw_output)

    return invoke


def _install_trace_spies(monkeypatch, captured: dict) -> None:
    trace = object()
    root_span = object()

    def create_trace(**kwargs):
        captured["trace_create"] = kwargs
        return trace, root_span

    def finalize_trace(**kwargs):
        captured["trace_finalize"] = kwargs

    monkeypatch.setattr(optimizer, "create_trace_with_root_span", create_trace)
    monkeypatch.setattr(optimizer, "finalize_langfuse_trace", finalize_trace)


def test_optimize_returns_reviewable_draft_without_changing_business_state(
    app, monkeypatch
):
    user_bid = "profile-optimize-success"
    source = "我在上海做办公室工作，希望表达简洁。SENSITIVE_PROFILE_INPUT"
    optimized = "我在上海从事办公室工作，希望 AI 老师表达简洁。"
    captured: dict = {}
    monkeypatch.setattr(optimizer, "check_text_content", lambda *_args: True)
    monkeypatch.setattr(
        optimizer,
        "invoke_llm",
        _successful_llm(
            json.dumps({"optimized_learner_profile": optimized}, ensure_ascii=False),
            captured,
        ),
    )
    _install_trace_spies(monkeypatch, captured)

    with app.app_context():
        _create_profile_state(user_bid)
        before = _snapshot_profile_state(user_bid)
        result = optimizer.optimize_learner_profile(
            app,
            user_id=user_bid,
            learner_profile=source,
        )
        db.session.expire_all()
        after = _snapshot_profile_state(user_bid)

    assert result == {"optimized_learner_profile": optimized}
    assert after == before
    assert json.loads(captured["args"][4]) == {"learner_profile": source}
    assert captured["kwargs"]["json"] is True
    assert captured["kwargs"]["temperature"] == 0.1
    assert captured["kwargs"]["timeout"] == 15
    assert captured["kwargs"]["sensitive_content"] is True
    assert captured["kwargs"]["usage_scene"] == BILL_USAGE_SCENE_PROD
    assert captured["kwargs"]["billable"] == 0
    assert captured["kwargs"]["usage_context"].billable == 0
    assert (
        "Do not extract, invent, or otherwise process a nickname"
        in captured["kwargs"]["system"]
    )
    assert source in captured["trace_create"]["trace_payload"]["input"].values()
    assert optimized in captured["trace_finalize"]["trace_payload"]["output"].values()


def test_optimize_rejects_moderation_without_calling_llm_or_changing_state(
    app, monkeypatch
):
    user_bid = "profile-optimize-rejected"
    invoked = False
    monkeypatch.setattr(optimizer, "check_text_content", lambda *_args: False)

    def unexpected_invoke(*_args, **_kwargs):
        nonlocal invoked
        invoked = True
        yield SimpleNamespace(result="unexpected")

    monkeypatch.setattr(optimizer, "invoke_llm", unexpected_invoke)

    with app.app_context():
        _create_profile_state(user_bid)
        before = _snapshot_profile_state(user_bid)
        with pytest.raises(AppException) as raised:
            optimizer.optimize_learner_profile(
                app,
                user_id=user_bid,
                learner_profile="Rejected profile",
            )
        db.session.expire_all()
        after = _snapshot_profile_state(user_bid)

    assert raised.value.code == 1022
    assert invoked is False
    assert after == before


def test_optimize_provider_unavailable_moderation_still_allows_llm(app, monkeypatch):
    user_bid = "profile-optimize-moderation-unavailable"
    source = "Provider unavailable source profile"
    captured: dict = {}
    monkeypatch.setitem(app.config, "CHECK_PROVIDER", "unsupported-provider")
    monkeypatch.setattr(
        optimizer,
        "invoke_llm",
        _successful_llm(
            json.dumps({"optimized_learner_profile": "Optimized profile"}),
            captured,
        ),
    )
    _install_trace_spies(monkeypatch, captured)

    with app.app_context():
        _create_profile_state(user_bid)
        before = _snapshot_profile_state(user_bid)
        result = optimizer.optimize_learner_profile(
            app,
            user_id=user_bid,
            learner_profile=source,
        )
        db.session.expire_all()
        after = _snapshot_profile_state(user_bid)
        audit = RiskControlResult.query.filter_by(
            user_id=user_bid,
            check_strategy="check_learner_profile",
        ).one()

    assert result == {"optimized_learner_profile": "Optimized profile"}
    assert "args" in captured
    assert after == before
    assert audit.check_result == CHECK_RESULT_UNKNOWN
    assert audit.is_pass == 0
    assert source not in audit.text
    assert '"content":"[redacted]"' in audit.text


def test_optimize_missing_default_model_does_not_call_llm_or_change_state(
    app, monkeypatch
):
    user_bid = "profile-optimize-missing-model"
    invoked = False
    monkeypatch.setattr(optimizer, "check_text_content", lambda *_args: True)
    monkeypatch.setitem(app.config, "DEFAULT_LLM_MODEL", "")

    def unexpected_invoke(*_args, **_kwargs):
        nonlocal invoked
        invoked = True
        yield SimpleNamespace(result="unexpected")

    monkeypatch.setattr(optimizer, "invoke_llm", unexpected_invoke)

    with app.app_context():
        _create_profile_state(user_bid)
        before = _snapshot_profile_state(user_bid)
        with pytest.raises(AppException) as raised:
            optimizer.optimize_learner_profile(
                app,
                user_id=user_bid,
                learner_profile="Source profile",
            )
        db.session.expire_all()
        after = _snapshot_profile_state(user_bid)

    assert raised.value.code == 1021
    assert invoked is False
    assert after == before


@pytest.mark.parametrize(
    "raw_output",
    [
        "not json",
        "[]",
        json.dumps({"optimized_learner_profile": "ok", "extra": True}),
        json.dumps({"optimized_learner_profile": ""}),
        json.dumps({"optimized_learner_profile": "x" * 1001}),
    ],
)
def test_optimize_rejects_invalid_model_output_without_changing_state(
    app, monkeypatch, raw_output
):
    digest = hashlib.sha256(raw_output.encode("utf-8")).hexdigest()[:8]
    user_bid = f"profile-optimize-invalid-{digest}"
    captured: dict = {}
    monkeypatch.setattr(optimizer, "check_text_content", lambda *_args: True)
    monkeypatch.setattr(
        optimizer,
        "invoke_llm",
        _successful_llm(raw_output, captured),
    )
    _install_trace_spies(monkeypatch, captured)

    with app.app_context():
        _create_profile_state(user_bid)
        before = _snapshot_profile_state(user_bid)
        with pytest.raises(AppException) as raised:
            optimizer.optimize_learner_profile(
                app,
                user_id=user_bid,
                learner_profile="Valid source profile",
            )
        db.session.expire_all()
        after = _snapshot_profile_state(user_bid)

    assert raised.value.code == 1021
    assert after == before
    assert captured["trace_finalize"]["root_span"] is not None


def test_optimize_timeout_finalizes_trace_without_changing_state(app, monkeypatch):
    user_bid = "profile-optimize-timeout"
    captured: dict = {}
    monkeypatch.setattr(optimizer, "check_text_content", lambda *_args: True)

    def timeout_invoke(*_args, **_kwargs):
        raise TimeoutError("provider timeout")
        yield  # pragma: no cover

    monkeypatch.setattr(optimizer, "invoke_llm", timeout_invoke)
    _install_trace_spies(monkeypatch, captured)

    with app.app_context():
        _create_profile_state(user_bid)
        before = _snapshot_profile_state(user_bid)
        with pytest.raises(AppException) as raised:
            optimizer.optimize_learner_profile(
                app,
                user_id=user_bid,
                learner_profile="Valid source profile",
            )
        db.session.expire_all()
        after = _snapshot_profile_state(user_bid)

    assert raised.value.code == 1021
    assert after == before
    assert captured["trace_finalize"]["root_span"] is not None


@pytest.mark.parametrize("learner_profile", ["", "   ", "x" * 1001])
def test_optimize_rejects_invalid_input_before_moderation(
    app, monkeypatch, learner_profile
):
    moderated = False

    def unexpected_moderation(*_args):
        nonlocal moderated
        moderated = True
        return True

    monkeypatch.setattr(optimizer, "check_text_content", unexpected_moderation)

    with app.app_context(), pytest.raises(AppException) as raised:
        optimizer.optimize_learner_profile(
            app,
            user_id="profile-optimize-invalid-input",
            learner_profile=learner_profile,
        )

    assert raised.value.code == 2001
    assert moderated is False

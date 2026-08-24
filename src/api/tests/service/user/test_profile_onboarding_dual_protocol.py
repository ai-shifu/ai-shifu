"""Verify legacy and canonical profile-onboarding protocol isolation."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Never

import pytest
from flaskr.dao import db
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.models import UserInfo, UserOnboardingState
from flaskr.service.user.repository import create_user_entity

VALID_GUIDED_FLOW = (
    "?[%{{learning_goal}}...What would you most like to learn right now?]"
)
LEGACY_NONASSIGNMENT_FLOW = "Welcome.\n\n---\n\n?[Continue]"
LEGACY_UNSAFE_ASSIGNMENT_FLOW = (
    "Welcome.\n\n---\n\n?[%{{job role}}...What kind of work do you do?]"
)
LEGACY_UNSAFE_PROJECTED_FLOW = (
    "Welcome.\n\n---\n\n"
    "?[%{{__profile_onboarding_legacy_answer_0}}...What kind of work do you do?]"
)
LEGACY_DISTINCT_BUTTON_FLOW = "?[%{{sys_user_style}} Short//brief | Detailed//full]"
LEGACY_DISTINCT_BUTTON_PROJECTED_FLOW = "?[%{{sys_user_style}} brief | full]"


def _parse_retiring_web_step(content: str) -> dict[str, object]:
    """Mirror the retired frontend parser's assignment and choice rules."""
    interaction_match = re.fullmatch(r"\?\[([\s\S]*?)\]", content)
    assert interaction_match is not None
    step_match = re.fullmatch(
        r"%\{\{\s*([^}\s]+)\s*\}\}\s*([\s\S]*)",
        interaction_match.group(1),
    )
    assert step_match is not None
    variable_name = step_match.group(1).strip()
    rest = step_match.group(2).strip()
    is_text_input = rest.startswith("...")
    prompt = rest[3:].strip() if is_text_input else rest
    options = (
        [option.strip() for option in rest.split("|") if option.strip()]
        if not is_text_input and "|" in rest
        else []
    )
    return {
        "variable": variable_name,
        "options": options,
        "prompt": "" if len(options) > 1 else prompt,
        "type": "choice" if len(options) > 1 else "text",
    }


def _create_user(user_bid: str, *, learner_profile: str = "") -> None:
    create_user_entity(
        user_bid=user_bid,
        identify=user_bid,
        nickname="Test learner",
        language="en-US",
        learner_profile=learner_profile,
    )
    db.session.commit()


def _set_config(monkeypatch: object, payload: dict) -> None:
    from flaskr.service.common import profile_onboarding as config_module

    monkeypatch.setattr(
        config_module,
        "get_config",
        lambda *_args, **_kwargs: payload,
    )


def test_legacy_projection_replaces_assigned_unsafe_variable_names() -> None:
    from flaskr.service.profile.onboarding import (
        _project_legacy_profile_onboarding_markdownflow,
    )
    from flaskr.service.profile_research.api import (
        validate_profile_research_document,
    )

    projected = _project_legacy_profile_onboarding_markdownflow(
        LEGACY_UNSAFE_ASSIGNMENT_FLOW
    )

    assert projected == LEGACY_UNSAFE_PROJECTED_FLOW
    assert validate_profile_research_document(projected)["variables"] == [
        "__profile_onboarding_legacy_answer_0"
    ]


def test_legacy_projection_replaces_raw_names_normalized_by_official_parser() -> None:
    from flaskr.service.profile.onboarding import (
        _project_legacy_profile_onboarding_markdownflow,
    )

    projected = _project_legacy_profile_onboarding_markdownflow(
        "?[%{{ job }}...What kind of work do you do?]"
    )

    assert projected == (
        "?[%{{__profile_onboarding_legacy_answer_0}}...What kind of work do you do?]"
    )


def test_legacy_projection_preserves_every_byte_around_changed_interactions() -> None:
    from flaskr.service.profile.onboarding import (
        _project_legacy_profile_onboarding_markdownflow,
    )

    interaction = "?[%{{job role}} Teacher//teacher | Student//student]"
    document = (
        "!===\nKeep `---` exactly as written.\n!===\n"
        "\n  ---  \n\n"
        "Adjacent intro before the question.\n"
        f"{interaction}\n"
        "Trailing content stays adjacent.\n"
    )

    projected = _project_legacy_profile_onboarding_markdownflow(document)

    assert projected == document.replace(
        interaction,
        "?[%{{__profile_onboarding_legacy_answer_0}} teacher | student]",
    )


def test_legacy_projection_uses_official_button_values_as_legacy_choices() -> None:
    from flaskr.service.profile.onboarding import (
        _project_legacy_profile_onboarding_markdownflow,
    )
    from markdown_flow import InteractionParser

    projected = _project_legacy_profile_onboarding_markdownflow(
        LEGACY_DISTINCT_BUTTON_FLOW
    )

    assert projected == LEGACY_DISTINCT_BUTTON_PROJECTED_FLOW
    assert InteractionParser().parse(projected)["buttons"] == [
        {"display": "brief", "value": "brief"},
        {"display": "full", "value": "full"},
    ]
    assert _parse_retiring_web_step(projected) == {
        "variable": "sys_user_style",
        "options": ["brief", "full"],
        "prompt": "",
        "type": "choice",
    }


def test_legacy_projection_rebuilds_explicit_same_value_buttons() -> None:
    from flaskr.service.profile.onboarding import (
        _project_legacy_profile_onboarding_markdownflow,
    )

    projected = _project_legacy_profile_onboarding_markdownflow(
        "?[%{{sys_user_style}} Short//Short | Detailed//Detailed]"
    )

    assert projected == "?[%{{sys_user_style}} Short | Detailed]"
    assert _parse_retiring_web_step(projected)["options"] == [
        "Short",
        "Detailed",
    ]


def test_legacy_projection_drops_unsupported_button_free_text_question() -> None:
    from flaskr.service.profile.onboarding import (
        _project_legacy_profile_onboarding_markdownflow,
    )

    projected = _project_legacy_profile_onboarding_markdownflow(
        "?[%{{sys_user_style}} Short//brief | Detailed//full | ...Other style?]"
    )

    assert projected == LEGACY_DISTINCT_BUTTON_PROJECTED_FLOW
    legacy_step = _parse_retiring_web_step(projected)
    assert legacy_step["options"] == ["brief", "full"]
    assert all("Other style?" not in option for option in legacy_step["options"])


def test_legacy_projection_isolates_values_the_old_parser_would_trim() -> None:
    from flaskr.service.profile.onboarding import (
        _project_legacy_profile_onboarding_markdownflow,
    )

    document = (
        "?[%{{__profile_onboarding_legacy_answer_0}}...Reserved]"
        "\n\n---\n\n"
        "?[%{{sys_user_style}} Short// brief | Detailed//full]"
    )

    projected = _project_legacy_profile_onboarding_markdownflow(document)

    assert projected == (
        "?[%{{__profile_onboarding_legacy_answer_0}}...Reserved]"
        "\n\n---\n\n"
        "?[%{{__profile_onboarding_legacy_answer_0_1}} brief | full]"
    )
    legacy_step = _parse_retiring_web_step(projected.split("\n\n---\n\n")[1])
    assert legacy_step["variable"] == "__profile_onboarding_legacy_answer_0_1"
    assert legacy_step["options"] == ["brief", "full"]


def test_legacy_projection_matches_ecmascript_button_value_trimming() -> None:
    from flaskr.service.profile.onboarding import (
        _project_legacy_profile_onboarding_markdownflow,
        _strip_retiring_web_whitespace,
    )

    assert _strip_retiring_web_whitespace("\ufeff\tbrief\u3000\u2029") == "brief"
    preserved_value = "\u0085brief\u0085"
    assert _strip_retiring_web_whitespace(preserved_value) == preserved_value

    projected = _project_legacy_profile_onboarding_markdownflow(
        "?[%{{sys_user_style}} Short//\u0085brief | Detailed//full]"
    )

    assert projected == "?[%{{sys_user_style}} \u0085brief | full]"


def test_legacy_projection_handles_mixed_interactions_without_collisions() -> None:
    from flaskr.service.profile.onboarding import (
        _project_legacy_profile_onboarding_markdownflow,
    )
    from flaskr.service.profile_research.api import (
        validate_profile_research_document,
    )

    document = (
        "Welcome.\n\n---\n\n"
        "?[%{{__profile_onboarding_legacy_answer_0}}...Assigned question]\n\n---\n\n"
        "?[%{{learning_goal}}...Safe assigned question]\n\n---\n\n"
        "?[%{{job role}} Teacher//teacher | Student//student]\n\n---\n\n"
        "?[Continue//continue | Later//later]"
    )

    projected = _project_legacy_profile_onboarding_markdownflow(document)

    assert projected == (
        "Welcome.\n\n---\n\n"
        "?[%{{__profile_onboarding_legacy_answer_0}}...Assigned question]\n\n---\n\n"
        "?[%{{learning_goal}}...Safe assigned question]\n\n---\n\n"
        "?[%{{__profile_onboarding_legacy_answer_0_1}}"
        " teacher | student]\n\n---\n\n"
        "?[%{{__profile_onboarding_legacy_answer_1}} continue | later]"
    )
    assert set(validate_profile_research_document(projected)["variables"]) == {
        "__profile_onboarding_legacy_answer_0",
        "learning_goal",
        "__profile_onboarding_legacy_answer_0_1",
        "__profile_onboarding_legacy_answer_1",
    }


def test_legacy_button_projection_completion_keeps_protocol_storage_isolated(
    app: object, monkeypatch: object, test_client: object
) -> None:
    from flaskr.service.common.profile_onboarding import (
        PROFILE_ONBOARDING_STATE_KEY,
    )
    from flaskr.service.profile.onboarding import get_profile_onboarding_status

    document = (
        f"{LEGACY_DISTINCT_BUTTON_FLOW}\n\n---\n\n?[Continue//continue | Later//later]"
    )
    config = {
        "enabled": True,
        "markdownflow": document,
        "revision": 12,
    }
    _set_config(monkeypatch, config)
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id="protocol-button-values",
            language="en-US",
            is_operator=False,
        ),
    )

    with app.app_context():
        _create_user("protocol-button-values")
        fresh = get_profile_onboarding_status(
            app,
            user_id="protocol-button-values",
        )

    response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "skipped": False,
            "variables": {
                "sys_user_style": "brief",
                "__profile_onboarding_legacy_answer_0": "continue",
            },
        },
    )

    with app.app_context():
        user = UserInfo.query.filter_by(user_bid="protocol-button-values").one()
        values = {
            row.key: row.value
            for row in VariableValue.query.filter_by(
                user_bid="protocol-button-values",
                deleted=0,
            ).all()
        }
        v2_state = UserOnboardingState.query.filter_by(
            user_bid="protocol-button-values"
        ).first()

    body = response.get_json(force=True)
    assert body["code"] == 0
    assert body["data"]["variables"] == {"sys_user_style": "brief"}
    assert user.learner_profile == ""
    assert values["sys_user_style"] == "brief"
    assert set(values) == {"sys_user_style", PROFILE_ONBOARDING_STATE_KEY}
    assert v2_state is None

    assert fresh["markdownflow"] == (
        f"{LEGACY_DISTINCT_BUTTON_PROJECTED_FLOW}\n\n---\n\n"
        "?[%{{__profile_onboarding_legacy_answer_0}} continue | later]"
    )
    assert fresh["profile_v2"]["guided_available"] is True
    assert config["markdownflow"] == document


def test_legacy_trimmed_button_projection_cannot_write_system_profile(
    app: object, monkeypatch: object, test_client: object
) -> None:
    from flaskr.service.common.profile_onboarding import (
        PROFILE_ONBOARDING_STATE_KEY,
    )
    from flaskr.service.profile.onboarding import get_profile_onboarding_status

    document = "?[%{{sys_user_style}} Short// brief | Detailed//full]"
    _set_config(
        monkeypatch,
        {
            "enabled": True,
            "markdownflow": document,
            "revision": 13,
        },
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id="protocol-spaced-button-value",
            language="en-US",
            is_operator=False,
        ),
    )

    with app.app_context():
        _create_user("protocol-spaced-button-value")
        fresh = get_profile_onboarding_status(
            app,
            user_id="protocol-spaced-button-value",
        )

    assert fresh["markdownflow"] == (
        "?[%{{__profile_onboarding_legacy_answer_0}} brief | full]"
    )
    legacy_step = _parse_retiring_web_step(fresh["markdownflow"])
    synthetic_variable = str(legacy_step["variable"])

    response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "skipped": False,
            "variables": {synthetic_variable: "brief"},
        },
    )

    with app.app_context():
        values = {
            row.key: row.value
            for row in VariableValue.query.filter_by(
                user_bid="protocol-spaced-button-value",
                deleted=0,
            ).all()
        }

    body = response.get_json(force=True)
    assert body["code"] == 0
    assert body["data"]["variables"] == {}
    assert set(values) == {PROFILE_ONBOARDING_STATE_KEY}


def test_legacy_projection_failure_keeps_v2_guided_flow_available(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile import onboarding as onboarding_service

    def raise_projection_error(_document: str) -> str:
        msg = "projection failed"
        raise RuntimeError(msg)

    _set_config(
        monkeypatch,
        {
            "enabled": True,
            "markdownflow": LEGACY_NONASSIGNMENT_FLOW,
            "revision": 9,
        },
    )
    monkeypatch.setattr(
        onboarding_service,
        "_project_legacy_profile_onboarding_markdownflow",
        raise_projection_error,
    )

    with app.app_context():
        _create_user("legacy-projection-failure")
        status = onboarding_service.get_profile_onboarding_status(
            app,
            user_id="legacy-projection-failure",
        )

    assert status["enabled"] is True
    assert status["should_show"] is True
    assert status["markdownflow"] == LEGACY_NONASSIGNMENT_FLOW
    assert status["profile_v2"]["guided_available"] is True
    assert status["profile_v2"]["should_show"] is True
    assert status["profile_v2"]["presentation"] == "blocking"


def test_fenced_markdownflow_remains_available_when_legacy_projection_cannot_map_it(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile.onboarding import get_profile_onboarding_status

    document = (
        "Here is an example.\n\n"
        "```python\nprint('hello')\n```\n\n"
        "---\n\n"
        "?[%{{learning_goal}}...What would you like to learn?]"
    )
    _set_config(
        monkeypatch,
        {
            "enabled": True,
            "markdownflow": document,
            "revision": 10,
        },
    )

    with app.app_context():
        _create_user("fenced-profile-onboarding")
        status = get_profile_onboarding_status(
            app,
            user_id="fenced-profile-onboarding",
        )

    assert status["enabled"] is True
    assert status["markdownflow"] == document
    assert status["profile_v2"]["guided_available"] is True
    assert status["profile_v2"]["presentation"] == "blocking"


def test_dual_get_contract_covers_fresh_legacy_canonical_v2_and_fail_open(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.common.profile_onboarding import (
        PROFILE_ONBOARDING_SCENE_KEY,
        PROFILE_ONBOARDING_STATE_KEY,
        PROFILE_ONBOARDING_VERSION,
    )
    from flaskr.service.profile.onboarding import (
        complete_profile_onboarding,
        get_profile_onboarding_status,
    )

    enabled_config = {
        "enabled": True,
        "markdownflow": VALID_GUIDED_FLOW,
        "document_prompt": "Keep the result concise.",
        "revision": 9,
    }
    _set_config(monkeypatch, enabled_config)

    with app.app_context():
        _create_user("dual-fresh")
        _create_user("dual-legacy")
        _create_user("dual-canonical", learner_profile="Prefers concise diagrams.")
        _create_user("dual-v2")
        _create_user("dual-disabled")
        _create_user("dual-broken")

        complete_profile_onboarding(
            app,
            user_id="dual-legacy",
            skipped=True,
            variables={},
        )
        db.session.add(
            UserOnboardingState(
                user_bid="dual-v2",
                scene_key=PROFILE_ONBOARDING_SCENE_KEY,
                version=PROFILE_ONBOARDING_VERSION,
                status="skipped",
                trigger_source="skipped",
            )
        )
        db.session.commit()

        fresh = get_profile_onboarding_status(app, user_id="dual-fresh")
        legacy = get_profile_onboarding_status(app, user_id="dual-legacy")
        canonical = get_profile_onboarding_status(app, user_id="dual-canonical")
        v2 = get_profile_onboarding_status(app, user_id="dual-v2")

        enabled_config.update(enabled=False)
        disabled = get_profile_onboarding_status(app, user_id="dual-disabled")
        enabled_config.update(enabled=True, markdownflow="Plain Markdown only")
        broken = get_profile_onboarding_status(app, user_id="dual-broken")

        legacy_state = VariableValue.query.filter_by(
            user_bid="dual-legacy",
            key=PROFILE_ONBOARDING_STATE_KEY,
            deleted=0,
        ).one()

    assert fresh["enabled"] is True
    assert fresh["should_show"] is True
    assert fresh["contract_version"] == PROFILE_ONBOARDING_VERSION
    assert fresh["profile_v2"]["presentation"] == "blocking"
    assert fresh["profile_v2"]["should_show"] is True
    assert fresh["profile_v2"]["config_revision"] == 9

    assert legacy["should_show"] is False
    assert legacy["profile_v2"]["presentation"] == "non_blocking"
    assert legacy["profile_v2"]["should_show"] is True
    assert legacy["profile_v2"]["legacy_handled"] is True
    assert json.loads(legacy_state.value)["version"] == 9

    for handled in (canonical, v2):
        assert handled["should_show"] is False
        assert handled["profile_v2"]["handled"] is True
        assert handled["profile_v2"]["should_show"] is False
        assert handled["profile_v2"]["presentation"] == "hidden"

    for unavailable in (disabled, broken):
        assert unavailable["enabled"] is False
        assert unavailable["should_show"] is False
        assert unavailable["profile_v2"]["guided_available"] is False
        assert unavailable["profile_v2"]["should_show"] is False
        assert unavailable["profile_v2"]["presentation"] == "hidden"


def test_legacy_projection_completion_writes_only_the_legacy_sentinel(
    app: object, monkeypatch: object, test_client: object
) -> None:
    from flaskr.service.common.profile_onboarding import (
        PROFILE_ONBOARDING_STATE_KEY,
    )
    from flaskr.service.profile.onboarding import get_profile_onboarding_status

    _set_config(
        monkeypatch,
        {
            "enabled": True,
            "markdownflow": LEGACY_UNSAFE_ASSIGNMENT_FLOW,
            "revision": 10,
        },
    )
    moderated_values = []
    monkeypatch.setattr(
        "flaskr.service.profile.onboarding.check_text_content",
        lambda _app, _user_id, value: moderated_values.append(value) or True,
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id="protocol-arbitrary-only",
            language="en-US",
            is_operator=False,
        ),
    )

    with app.app_context():
        _create_user("protocol-arbitrary-only")
        fresh = get_profile_onboarding_status(
            app,
            user_id="protocol-arbitrary-only",
        )

    response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "skipped": False,
            "variables": {
                "__profile_onboarding_legacy_answer_0": "Teacher",
                "job role": "Teacher",
            },
        },
    )

    with app.app_context():
        user = UserInfo.query.filter_by(user_bid="protocol-arbitrary-only").one()
        values = {
            row.key: row.value
            for row in VariableValue.query.filter_by(
                user_bid="protocol-arbitrary-only",
                deleted=0,
            ).all()
        }
        v2_state = UserOnboardingState.query.filter_by(
            user_bid="protocol-arbitrary-only"
        ).first()
        handled = get_profile_onboarding_status(
            app,
            user_id="protocol-arbitrary-only",
        )

    body = response.get_json(force=True)
    assert body["code"] == 0
    assert body["data"]["variables"] == {}
    assert moderated_values == []
    assert user.learner_profile == ""
    assert set(values) == {PROFILE_ONBOARDING_STATE_KEY}
    assert json.loads(values[PROFILE_ONBOARDING_STATE_KEY])["version"] == 10
    assert v2_state is None

    assert fresh["should_show"] is True
    assert fresh["markdownflow"] == LEGACY_UNSAFE_PROJECTED_FLOW
    assert fresh["contract_version"] == "profile-v2"
    assert fresh["profile_v2"]["guided_available"] is True
    assert fresh["profile_v2"]["should_show"] is True
    assert fresh["profile_v2"]["presentation"] == "blocking"
    assert handled["should_show"] is False
    assert handled["profile_v2"]["should_show"] is True
    assert handled["profile_v2"]["legacy_handled"] is True
    assert handled["profile_v2"]["presentation"] == "non_blocking"


def test_legacy_complete_filters_unknown_variables_before_moderation_and_storage(
    app: object, monkeypatch: object, test_client: object
) -> None:
    from flaskr.service.common.profile_onboarding import (
        PROFILE_ONBOARDING_STATE_KEY,
    )

    _set_config(
        monkeypatch,
        {
            "enabled": True,
            "markdownflow": VALID_GUIDED_FLOW,
            "revision": 11,
        },
    )
    moderated_values = []
    monkeypatch.setattr(
        "flaskr.service.profile.onboarding.check_text_content",
        lambda _app, _user_id, value: moderated_values.append(value) or True,
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id="protocol-arbitrary-and-system",
            language="en-US",
            is_operator=False,
        ),
    )

    with app.app_context():
        _create_user("protocol-arbitrary-and-system")

    response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "skipped": False,
            "variables": {
                "learning_goal": "This must be discarded.",
                "sys_user_nickname": "Legacy learner",
            },
        },
    )

    with app.app_context():
        user = UserInfo.query.filter_by(user_bid="protocol-arbitrary-and-system").one()
        values = {
            row.key: row.value
            for row in VariableValue.query.filter_by(
                user_bid="protocol-arbitrary-and-system",
                deleted=0,
            ).all()
        }
        v2_state = UserOnboardingState.query.filter_by(
            user_bid="protocol-arbitrary-and-system"
        ).first()

    body = response.get_json(force=True)
    assert body["code"] == 0
    assert body["data"]["variables"] == {"sys_user_nickname": "Legacy learner"}
    assert moderated_values == ["Legacy learner"]
    assert set(values) == {"sys_user_nickname", PROFILE_ONBOARDING_STATE_KEY}
    assert values["sys_user_nickname"] == "Legacy learner"
    assert json.loads(values[PROFILE_ONBOARDING_STATE_KEY])["version"] == 11
    assert "learning_goal" not in values
    assert user.learner_profile == ""
    assert v2_state is None


def test_complete_routes_keep_legacy_and_v2_persistence_strictly_isolated(
    app: object, monkeypatch: object, test_client: object
) -> None:
    from flaskr.service.common.profile_onboarding import (
        PROFILE_ONBOARDING_SCENE_KEY,
        PROFILE_ONBOARDING_STATE_KEY,
        PROFILE_ONBOARDING_VERSION,
    )

    _set_config(
        monkeypatch,
        {
            "enabled": True,
            "markdownflow": VALID_GUIDED_FLOW,
            "revision": 4,
        },
    )
    monkeypatch.setattr(
        "flaskr.service.profile.onboarding.check_text_content",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    active_user = {"user_id": "protocol-legacy"}
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id=active_user["user_id"],
            language="en-US",
            is_operator=False,
        ),
    )

    with app.app_context():
        _create_user("protocol-legacy")
        _create_user("protocol-v2")
        _create_user("protocol-mixed")

    legacy_response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "skipped": False,
            "variables": {
                "sys_user_nickname": "Legacy learner",
                "sys_user_background": "Legacy background",
            },
        },
    )
    active_user["user_id"] = "protocol-v2"
    v2_response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "learner_profile": "Prefers short examples and practical exercises.",
            "trigger_source": "guided",
        },
    )
    active_user["user_id"] = "protocol-mixed"
    mixed_response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "skipped": False,
            "learner_profile": "This payload must never be written.",
            "trigger_source": "guided",
        },
    )

    assert legacy_response.get_json(force=True)["code"] == 0
    assert v2_response.get_json(force=True)["code"] == 0
    assert mixed_response.get_json(force=True)["code"] != 0

    with app.app_context():
        legacy_user = UserInfo.query.filter_by(user_bid="protocol-legacy").one()
        legacy_values = {
            row.key: row.value
            for row in VariableValue.query.filter_by(
                user_bid="protocol-legacy",
                deleted=0,
            ).all()
        }
        legacy_v2_state = UserOnboardingState.query.filter_by(
            user_bid="protocol-legacy",
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_VERSION,
        ).first()

        v2_user = UserInfo.query.filter_by(user_bid="protocol-v2").one()
        v2_values = VariableValue.query.filter_by(
            user_bid="protocol-v2",
            deleted=0,
        ).all()
        v2_state = UserOnboardingState.query.filter_by(
            user_bid="protocol-v2",
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_VERSION,
        ).one()

        mixed_user = UserInfo.query.filter_by(user_bid="protocol-mixed").one()
        mixed_values = VariableValue.query.filter_by(
            user_bid="protocol-mixed",
            deleted=0,
        ).all()
        mixed_state = UserOnboardingState.query.filter_by(
            user_bid="protocol-mixed"
        ).first()

    assert legacy_user.learner_profile == ""
    assert legacy_v2_state is None
    assert legacy_values["sys_user_nickname"] == "Legacy learner"
    assert legacy_values["sys_user_background"] == "Legacy background"
    assert PROFILE_ONBOARDING_STATE_KEY in legacy_values

    assert v2_user.learner_profile == (
        "Prefers short examples and practical exercises."
    )
    assert v2_state.status == "completed"
    assert v2_state.trigger_source == "guided"
    assert v2_values == []

    assert mixed_user.learner_profile == ""
    assert mixed_values == []
    assert mixed_state is None


def test_status_fails_open_when_profile_config_cannot_be_loaded(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile import onboarding as onboarding_module

    def raise_unavailable_config() -> Never:
        msg = "config unavailable"
        raise RuntimeError(msg)

    monkeypatch.setattr(
        onboarding_module,
        "load_profile_onboarding_config_payload",
        raise_unavailable_config,
    )

    with app.app_context():
        _create_user("protocol-config-unavailable")
        status = onboarding_module.get_profile_onboarding_status(
            app,
            user_id="protocol-config-unavailable",
        )

    assert status["enabled"] is False
    assert status["should_show"] is False
    assert status["profile_v2"]["guided_available"] is False
    assert status["profile_v2"]["should_show"] is False
    assert status["profile_v2"]["presentation"] == "hidden"


def test_late_v2_skip_never_downgrades_a_completed_profile(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile.onboarding import (
        complete_profile_onboarding_v2,
        skip_profile_onboarding_v2,
    )

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        _create_user("protocol-late-skip")
        completed = complete_profile_onboarding_v2(
            app,
            user_id="protocol-late-skip",
            learner_profile="Keep the completed profile.",
            trigger_source="guided",
        )
        skipped = skip_profile_onboarding_v2(user_id="protocol-late-skip")
        state = UserOnboardingState.query.filter_by(user_bid="protocol-late-skip").one()

    assert completed["status"] == "completed"
    assert skipped["status"] == "completed"
    assert skipped["skipped"] is False
    assert state.status == "completed"
    assert state.trigger_source == "guided"


def test_v2_skip_locks_user_then_state_before_deciding_status(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile import onboarding as onboarding_module

    lock_reads: list[tuple[str, bool]] = []
    original_load_user = onboarding_module.load_learner_profile_user
    original_load_state = onboarding_module.load_learner_profile_state

    def load_user(user_id: str, *, for_update: bool = False) -> object:
        lock_reads.append(("user", for_update))
        return original_load_user(user_id, for_update=for_update)

    def load_state(user_id: str, *, for_update: bool = False) -> object:
        lock_reads.append(("state", for_update))
        return original_load_state(user_id, for_update=for_update)

    with app.app_context():
        user_id = "protocol-skip-lock-order"
        _create_user(user_id, learner_profile="Keep the completed profile.")
        monkeypatch.setattr(
            onboarding_module,
            "load_learner_profile_user",
            load_user,
        )
        monkeypatch.setattr(
            onboarding_module,
            "load_learner_profile_state",
            load_state,
        )

        result = onboarding_module.skip_profile_onboarding_v2(user_id=user_id)

    assert lock_reads[:2] == [("user", True), ("state", True)]
    assert result["status"] == "completed"
    assert result["skipped"] is False


def test_v2_complete_accepts_dormant_canonical_pasted_trigger(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile.onboarding import complete_profile_onboarding_v2

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        _create_user("protocol-dormant-pasted")
        completed = complete_profile_onboarding_v2(
            app,
            user_id="protocol-dormant-pasted",
            learner_profile="Imported canonical profile.",
            trigger_source="pasted",
        )
        state = UserOnboardingState.query.filter_by(
            user_bid="protocol-dormant-pasted"
        ).one()

    assert completed["status"] == "completed"
    assert completed["trigger_source"] == "pasted"
    assert state.status == "completed"
    assert state.trigger_source == "pasted"


def test_v2_complete_atomically_saves_optional_nickname_semantics(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile.onboarding import complete_profile_onboarding_v2

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        _create_user("protocol-nickname-preserve")
        _create_user("protocol-nickname-clear")
        _create_user("protocol-nickname-replace")

        preserved = complete_profile_onboarding_v2(
            app,
            user_id="protocol-nickname-preserve",
            learner_profile="Keep my existing display name.",
            trigger_source="guided",
        )
        cleared = complete_profile_onboarding_v2(
            app,
            user_id="protocol-nickname-clear",
            learner_profile="Do not use a display name.",
            trigger_source="guided",
            nickname="",
        )
        replaced = complete_profile_onboarding_v2(
            app,
            user_id="protocol-nickname-replace",
            learner_profile="Call me River.",
            trigger_source="guided",
            nickname="River",
        )

        users = {
            user.user_bid: user
            for user in UserInfo.query.filter(
                UserInfo.user_bid.in_(
                    {
                        "protocol-nickname-preserve",
                        "protocol-nickname-clear",
                        "protocol-nickname-replace",
                    }
                )
            ).all()
        }
        states = {
            state.user_bid: state
            for state in UserOnboardingState.query.filter(
                UserOnboardingState.user_bid.in_(users)
            ).all()
        }

    assert preserved["nickname"] == "Test learner"
    assert cleared["nickname"] == ""
    assert replaced["nickname"] == "River"
    assert users["protocol-nickname-preserve"].nickname == "Test learner"
    assert users["protocol-nickname-clear"].nickname == ""
    assert users["protocol-nickname-replace"].nickname == "River"
    assert all(state.status == "completed" for state in states.values())
    assert all(state.trigger_source == "guided" for state in states.values())


def test_v2_complete_rolls_back_profile_nickname_and_state_together(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile.onboarding import complete_profile_onboarding_v2

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        user_id = "protocol-nickname-atomic-failure"
        _create_user(user_id, learner_profile="Existing profile.")
        original_commit = db.session.commit

        def fail_commit() -> Never:
            msg = "database unavailable"
            raise RuntimeError(msg)

        monkeypatch.setattr(db.session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="database unavailable"):
            complete_profile_onboarding_v2(
                app,
                user_id=user_id,
                learner_profile="Replacement profile.",
                trigger_source="guided",
                nickname="Replacement name",
            )
        monkeypatch.setattr(db.session, "commit", original_commit)

        user = UserInfo.query.filter_by(user_bid=user_id).one()
        state = UserOnboardingState.query.filter_by(user_bid=user_id).first()

    assert user.learner_profile == "Existing profile."
    assert user.nickname == "Test learner"
    assert state is None


def test_late_v2_skip_reconstructs_completed_state_before_session_cleanup(
    app: object, monkeypatch: object, test_client: object
) -> None:
    user_id = "protocol-profile-without-state"
    session_id = "0123456789abcdef0123456789abcdef"

    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id=user_id,
            language="en-US",
            is_operator=False,
        ),
    )

    with app.app_context():
        _create_user(user_id, learner_profile="Keep this canonical profile.")
        assert UserOnboardingState.query.filter_by(user_bid=user_id).first() is None

    cleanup_observations: list[tuple[str, str, str]] = []

    def observe_cleanup(_app: object, *, user_bid: str, session_id: str | None) -> None:
        # Force a fresh ORM session so cleanup can only observe committed state.
        db.session.remove()
        state = UserOnboardingState.query.filter_by(user_bid=user_bid).one()
        cleanup_observations.append((user_bid, session_id or "", state.status))

    monkeypatch.setattr(
        "flaskr.route.user._delete_profile_onboarding_session",
        observe_cleanup,
    )

    response = test_client.post(
        "/api/user/profile-onboarding/skip",
        headers={"Token": "token"},
        json={"session_id": session_id},
    )

    data = response.get_json(force=True)
    assert data["code"] == 0
    assert data["data"]["status"] == "completed"
    assert data["data"]["completed"] is True
    assert data["data"]["skipped"] is False
    assert data["data"]["trigger_source"] == "settings"
    assert cleanup_observations == [(user_id, session_id, "completed")]

    with app.app_context():
        state = UserOnboardingState.query.filter_by(user_bid=user_id).one()
        assert state.status == "completed"
        assert state.trigger_source == "settings"

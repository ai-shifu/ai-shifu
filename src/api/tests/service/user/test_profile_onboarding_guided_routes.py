import json
from types import SimpleNamespace

import pytest
from flaskr.service.common.profile_onboarding import (
    PROFILE_ONBOARDING_DOCUMENT_PROMPT_MAX_CODEPOINTS,
)
from flaskr.service.profile_research.api import (
    ProfileResearchSessionBusy,
)

_SESSION_ID_1 = "0123456789abcdef0123456789abcdef"
_SESSION_ID_2 = "abcdef0123456789abcdef0123456789"


def _authenticate(monkeypatch, *, is_operator: bool = True) -> SimpleNamespace:
    user = SimpleNamespace(
        user_id="profile-route-user",
        language="zh-CN",
        is_operator=is_operator,
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: user,
        raising=False,
    )
    return user


def _data(response):
    body = response.get_json(force=True)
    assert body["code"] == 0
    return body["data"]


def _markdownflow_for_preview_config_size(*, target_bytes: int) -> str:
    from flaskr.service.common import profile_onboarding as module

    markdownflow_prefix = "?[Continue]\n\n---\n\n"
    payload = module.build_profile_onboarding_config_payload(
        enabled=False,
        markdownflow=markdownflow_prefix,
        document_prompt="",
        revision=6,
        updated_by="profile-route-user",
    )
    base_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    remaining_bytes = target_bytes - base_size
    assert remaining_bytes >= 0
    return (
        markdownflow_prefix
        + "测" * (remaining_bytes // 3)
        + "x" * (remaining_bytes % 3)
    )


def test_profile_onboarding_status_merges_config_and_v2_state(monkeypatch, test_client):
    user = _authenticate(monkeypatch)
    expected = {
        "enabled": True,
        "should_show": False,
        "markdownflow": "A valid snapshot",
        "allowed_variable_keys": ["sys_user_nickname"],
        "current_values": {"sys_user_nickname": "小明"},
        "contract_version": "profile-v2",
        "profile_v2": {
            "enabled": True,
            "should_show": True,
            "presentation": "non_blocking",
            "legacy_handled": True,
            "has_learner_profile": False,
            "learner_profile_updated_at": None,
            "max_length": 1000,
            "config_revision": 7,
            "guided_available": True,
        },
    }
    monkeypatch.setattr(
        "flaskr.route.user.get_profile_onboarding_status",
        lambda app, user_id: expected if user_id == user.user_id else {},
    )

    response = test_client.get(
        "/api/user/profile-onboarding", headers={"Token": "token"}
    )

    assert _data(response) == expected


def test_profile_onboarding_status_disabled_kill_switch_hides_collection(
    monkeypatch, test_client
):
    _authenticate(monkeypatch)
    monkeypatch.setattr(
        "flaskr.route.user.get_profile_onboarding_status",
        lambda app, user_id: {
            "enabled": False,
            "should_show": False,
            "contract_version": "profile-v2",
            "profile_v2": {
                "enabled": False,
                "should_show": False,
                "presentation": "hidden",
                "guided_available": False,
                "has_learner_profile": True,
            },
        },
    )

    data = _data(
        test_client.get("/api/user/profile-onboarding", headers={"Token": "token"})
    )

    assert data["profile_v2"]["enabled"] is False
    assert data["profile_v2"]["should_show"] is False
    assert data["profile_v2"]["presentation"] == "hidden"
    assert data["profile_v2"]["guided_available"] is False
    assert data["profile_v2"]["has_learner_profile"] is True


def test_profile_onboarding_complete_and_skip_delegate_strict_payloads(
    monkeypatch, test_client
):
    user = _authenticate(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "flaskr.route.user.complete_profile_onboarding_v2",
        lambda app, **kwargs: calls.append(("complete", kwargs)) or {"completed": True},
    )
    monkeypatch.setattr(
        "flaskr.route.user.skip_profile_onboarding_v2",
        lambda **kwargs: calls.append(("skip", kwargs)) or {"skipped": True},
    )
    monkeypatch.setattr(
        "flaskr.service.profile_research.api.delete_profile_research_session",
        lambda app, **kwargs: calls.append(("delete", kwargs)),
    )

    complete = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "learner_profile": "称呼我小明。",
            "trigger_source": "guided",
            "session_id": _SESSION_ID_1,
        },
    )
    skipped = test_client.post(
        "/api/user/profile-onboarding/skip",
        headers={"Token": "token"},
        json={"session_id": _SESSION_ID_2},
    )

    assert _data(complete) == {"completed": True}
    assert _data(skipped) == {"skipped": True}
    assert calls == [
        (
            "complete",
            {
                "user_id": user.user_id,
                "learner_profile": "称呼我小明。",
                "trigger_source": "guided",
            },
        ),
        (
            "delete",
            {
                "user_bid": user.user_id,
                "session_id": _SESSION_ID_1,
                "expected_purpose": "profile-onboarding",
            },
        ),
        ("skip", {"user_id": user.user_id}),
        (
            "delete",
            {
                "user_bid": user.user_id,
                "session_id": _SESSION_ID_2,
                "expected_purpose": "profile-onboarding",
            },
        ),
    ]


@pytest.mark.parametrize("nickname", ["小明", ""])
def test_profile_onboarding_complete_forwards_explicit_nickname(
    monkeypatch, test_client, nickname
):
    user = _authenticate(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "flaskr.route.user.complete_profile_onboarding_v2",
        lambda app, **kwargs: calls.append(("complete", kwargs)) or {"completed": True},
    )
    monkeypatch.setattr(
        "flaskr.route.user._delete_profile_onboarding_session",
        lambda app, **kwargs: calls.append(("cleanup", kwargs)),
    )

    response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "learner_profile": "称呼我小明。",
            "trigger_source": "guided",
            "session_id": _SESSION_ID_1,
            "nickname": nickname,
        },
    )

    assert _data(response) == {"completed": True}
    assert calls == [
        (
            "complete",
            {
                "user_id": user.user_id,
                "learner_profile": "称呼我小明。",
                "trigger_source": "guided",
                "nickname": nickname,
            },
        ),
        (
            "cleanup",
            {"user_bid": user.user_id, "session_id": _SESSION_ID_1},
        ),
    ]


def test_v2_mutations_do_not_commit_again_after_durable_service_and_cleanup(
    monkeypatch, test_client
):
    user = _authenticate(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "flaskr.route.user.complete_profile_onboarding_v2",
        lambda app, **kwargs: calls.append(("complete", kwargs)) or {"completed": True},
    )
    monkeypatch.setattr(
        "flaskr.route.user.skip_profile_onboarding_v2",
        lambda **kwargs: calls.append(("skip", kwargs)) or {"skipped": True},
    )
    monkeypatch.setattr(
        "flaskr.route.user._delete_profile_onboarding_session",
        lambda app, **kwargs: calls.append(("cleanup", kwargs)),
    )

    def fail_late_commit():
        raise RuntimeError("route must not commit after the v2 UoW")

    monkeypatch.setattr("flaskr.route.user.db.session.commit", fail_late_commit)

    complete = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "learner_profile": "Durably saved profile.",
            "trigger_source": "guided",
            "session_id": _SESSION_ID_1,
        },
    )
    skipped = test_client.post(
        "/api/user/profile-onboarding/skip",
        headers={"Token": "token"},
        json={"session_id": _SESSION_ID_2},
    )

    assert _data(complete) == {"completed": True}
    assert _data(skipped) == {"skipped": True}
    assert calls == [
        (
            "complete",
            {
                "user_id": user.user_id,
                "learner_profile": "Durably saved profile.",
                "trigger_source": "guided",
            },
        ),
        (
            "cleanup",
            {"user_bid": user.user_id, "session_id": _SESSION_ID_1},
        ),
        ("skip", {"user_id": user.user_id}),
        (
            "cleanup",
            {"user_bid": user.user_id, "session_id": _SESSION_ID_2},
        ),
    ]


def test_legacy_complete_keeps_its_route_owned_commit(monkeypatch, test_client):
    _authenticate(monkeypatch)
    commits = []
    monkeypatch.setattr(
        "flaskr.route.user.complete_profile_onboarding",
        lambda app, **kwargs: {"completed": True, "skipped": kwargs["skipped"]},
    )
    monkeypatch.setattr(
        "flaskr.route.user.db.session.commit",
        lambda: commits.append("commit"),
    )

    response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={"skipped": True},
    )

    assert _data(response) == {"completed": True, "skipped": True}
    assert commits == ["commit"]


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/user/profile-onboarding/complete",
            {
                "learner_profile": "profile",
                "trigger_source": "guided",
                "session_id": "a" * 33,
            },
        ),
        (
            "/api/user/profile-onboarding/complete",
            {
                "learner_profile": "profile",
                "trigger_source": "guided",
                "session_id": "g" * 32,
            },
        ),
        (
            "/api/user/profile-onboarding/skip",
            {"session_id": "a" * 100_000},
        ),
    ],
)
def test_profile_onboarding_rejects_invalid_session_id_before_mutation(
    monkeypatch, test_client, path, payload
):
    _authenticate(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "flaskr.route.user.complete_profile_onboarding_v2",
        lambda app, **kwargs: calls.append(("complete", kwargs)),
    )
    monkeypatch.setattr(
        "flaskr.route.user.skip_profile_onboarding_v2",
        lambda **kwargs: calls.append(("skip", kwargs)),
    )
    monkeypatch.setattr(
        "flaskr.route.user._delete_profile_onboarding_session",
        lambda app, **kwargs: calls.append(("delete", kwargs)),
    )

    response = test_client.post(path, headers={"Token": "token"}, json=payload)

    assert response.get_json(force=True)["code"] != 0
    assert calls == []


def test_profile_onboarding_complete_ignores_session_cleanup_failure(
    monkeypatch, test_client
):
    _authenticate(monkeypatch)
    monkeypatch.setattr(
        "flaskr.route.user.complete_profile_onboarding_v2",
        lambda app, **kwargs: {"completed": True},
    )

    def raise_cleanup_failure(app, **kwargs):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(
        "flaskr.service.profile_research.api.delete_profile_research_session",
        raise_cleanup_failure,
    )

    response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "learner_profile": "profile",
            "trigger_source": "guided",
            "session_id": _SESSION_ID_1,
        },
    )

    assert _data(response) == {"completed": True}


def test_profile_onboarding_skip_ignores_busy_session_cleanup(monkeypatch, test_client):
    _authenticate(monkeypatch)
    monkeypatch.setattr(
        "flaskr.route.user.skip_profile_onboarding_v2",
        lambda **kwargs: {"skipped": True},
    )

    def raise_busy_session(app, **kwargs):
        raise ProfileResearchSessionBusy("busy")

    monkeypatch.setattr(
        "flaskr.service.profile_research.api.delete_profile_research_session",
        raise_busy_session,
    )

    response = test_client.post(
        "/api/user/profile-onboarding/skip",
        headers={"Token": "token"},
        json={"session_id": _SESSION_ID_2},
    )

    assert _data(response) == {"skipped": True}


def test_profile_onboarding_session_start_snapshots_config_and_language(
    monkeypatch, test_client
):
    user = _authenticate(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "flaskr.route.user.get_profile_onboarding_config",
        lambda: {
            "enabled": True,
            "markdownflow": "  ?[Continue]  ",
            "document_prompt": "  summary prompt  ",
            "revision": 12,
        },
    )
    monkeypatch.setattr(
        "flaskr.route.user.get_profile_onboarding_status",
        lambda app, user_id: {
            "profile_v2": {
                "guided_available": True,
                "handled": False,
                "should_show": True,
                "has_learner_profile": False,
            },
        },
    )
    monkeypatch.setattr(
        "flaskr.service.profile_research.api.start_profile_research_session",
        lambda app, **kwargs: (
            calls.append(kwargs)
            or {"session_id": "session-started", "config_revision": 12}
        ),
    )

    response = test_client.post(
        "/api/user/profile-onboarding/session",
        headers={"Token": "token"},
        json={"language": "zh_cn", "intent": "onboarding"},
    )

    assert _data(response) == {
        "session_id": "session-started",
        "config_revision": 12,
    }
    assert calls == [
        {
            "user_bid": user.user_id,
            "document": "?[Continue]",
            "document_prompt": "summary prompt",
            "purpose": "profile-onboarding",
            "config_revision": 12,
            "output_language": "zh-CN",
        }
    ]


@pytest.mark.parametrize("language", ["unsupported", "x" * 10_000])
def test_profile_onboarding_session_start_rejects_unsupported_language(
    monkeypatch, test_client, language
):
    _authenticate(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "flaskr.route.user.get_profile_onboarding_config",
        lambda: {
            "enabled": True,
            "markdownflow": "?[continue]",
            "document_prompt": "",
            "revision": 1,
        },
    )
    monkeypatch.setattr(
        "flaskr.route.user.get_profile_onboarding_status",
        lambda app, user_id: {
            "profile_v2": {
                "guided_available": True,
                "handled": False,
                "should_show": True,
                "has_learner_profile": False,
            },
        },
    )
    monkeypatch.setattr(
        "flaskr.service.profile_research.api.start_profile_research_session",
        lambda app, **kwargs: calls.append(kwargs) or {"session_id": "session-1"},
    )

    response = test_client.post(
        "/api/user/profile-onboarding/session",
        headers={"Token": "token"},
        json={"language": language, "intent": "onboarding"},
    )

    assert response.get_json(force=True)["code"] != 0
    assert calls == []


def test_profile_onboarding_session_start_respects_collection_kill_switch(
    monkeypatch, test_client
):
    _authenticate(monkeypatch)
    monkeypatch.setattr(
        "flaskr.route.user.get_profile_onboarding_config",
        lambda: {
            "enabled": False,
            "markdownflow": "guided flow",
            "revision": 12,
        },
    )

    response = test_client.post(
        "/api/user/profile-onboarding/session",
        headers={"Token": "token"},
        json={},
    )

    assert response.get_json(force=True)["code"] != 0


@pytest.mark.parametrize(
    ("intent", "state", "expected_allowed"),
    [
        (
            "onboarding",
            {
                "handled": False,
                "should_show": True,
                "has_learner_profile": False,
            },
            True,
        ),
        (
            "onboarding",
            {
                "handled": True,
                "should_show": False,
                "has_learner_profile": True,
            },
            False,
        ),
        (
            "settings",
            {
                "handled": True,
                "should_show": False,
                "has_learner_profile": False,
            },
            True,
        ),
        (
            "settings",
            {
                "handled": False,
                "should_show": True,
                "has_learner_profile": True,
            },
            True,
        ),
        (
            "settings",
            {
                "handled": False,
                "should_show": True,
                "has_learner_profile": False,
            },
            False,
        ),
    ],
)
def test_profile_onboarding_session_start_enforces_intent_eligibility(
    monkeypatch,
    test_client,
    intent,
    state,
    expected_allowed,
):
    _authenticate(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "flaskr.route.user.get_profile_onboarding_config",
        lambda: {
            "enabled": True,
            "markdownflow": "?[继续]",
            "document_prompt": "",
            "revision": 1,
        },
    )
    monkeypatch.setattr(
        "flaskr.route.user.get_profile_onboarding_status",
        lambda app, user_id: {
            "profile_v2": {"guided_available": True, **state},
        },
    )
    monkeypatch.setattr(
        "flaskr.service.profile_research.api.start_profile_research_session",
        lambda app, **kwargs: calls.append(kwargs) or {"session_id": "session-1"},
    )

    response = test_client.post(
        "/api/user/profile-onboarding/session",
        headers={"Token": "token"},
        json={"intent": intent},
    )
    body = response.get_json(force=True)

    if expected_allowed:
        assert body["code"] == 0
        assert len(calls) == 1
    else:
        assert body["code"] != 0
        assert calls == []


def test_profile_onboarding_session_start_maps_busy_error(monkeypatch, test_client):
    _authenticate(monkeypatch)
    monkeypatch.setattr(
        "flaskr.route.user.get_profile_onboarding_config",
        lambda: {
            "enabled": True,
            "markdownflow": "?[继续]",
            "revision": 1,
        },
    )
    monkeypatch.setattr(
        "flaskr.route.user.get_profile_onboarding_status",
        lambda app, user_id: {
            "profile_v2": {
                "guided_available": True,
                "handled": False,
                "should_show": True,
                "has_learner_profile": False,
            },
        },
    )

    def raise_busy_error(app, **kwargs):
        raise ProfileResearchSessionBusy("busy")

    monkeypatch.setattr(
        "flaskr.service.profile_research.api.start_profile_research_session",
        raise_busy_error,
    )

    response = test_client.post(
        "/api/user/profile-onboarding/session",
        headers={"Token": "token"},
        json={"intent": "onboarding"},
    )

    assert response.get_json(force=True)["code"] == 4013


def test_profile_onboarding_session_run_streams_with_owner_and_purpose_scope(
    monkeypatch, test_client
):
    from flaskr.route.common import make_common_response

    user = _authenticate(monkeypatch)
    calls = []

    def fake_stream(app, **kwargs):
        calls.append(kwargs)
        yield {"type": "done"}

    monkeypatch.setattr(
        "flaskr.service.profile_research.api.stream_profile_research_session",
        fake_stream,
    )
    monkeypatch.setattr(
        "flaskr.service.profile_research.api.build_profile_research_sse_response",
        lambda app, event_iter_factory, log_context: make_common_response(
            {
                "events": list(event_iter_factory()),
                "log_context": log_context,
            }
        ),
    )

    response = test_client.post(
        f"/api/user/profile-onboarding/session/{_SESSION_ID_1}/run",
        headers={"Token": "token"},
        json={
            "user_input": {"preferred_name": ["小明"]},
            "expected_block_index": 2,
            "request_id": "learner-step-2",
        },
    )

    assert _data(response) == {
        "events": [{"type": "done"}],
        "log_context": "learner profile onboarding",
    }
    assert calls == [
        {
            "user_bid": user.user_id,
            "session_id": _SESSION_ID_1,
            "user_input": {"preferred_name": ["小明"]},
            "expected_purpose": "profile-onboarding",
            "expected_block_index": 2,
            "request_id": "learner-step-2",
        }
    ]


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/user/profile-onboarding/session", []),
        ("/api/user/profile-onboarding/session", {"language": 123}),
        ("/api/user/profile-onboarding/session", {"intent": "unsupported"}),
        ("/api/user/profile-onboarding/session", {"unexpected": True}),
        (
            f"/api/user/profile-onboarding/session/{_SESSION_ID_1}/run",
            {"user_input": "not-an-object"},
        ),
        (
            f"/api/user/profile-onboarding/session/{_SESSION_ID_1}/run",
            {"user_input": {"name": "not-a-list"}},
        ),
        (
            f"/api/user/profile-onboarding/session/{_SESSION_ID_1}/run",
            {"user_input": {"name": [1]}},
        ),
        (
            f"/api/user/profile-onboarding/session/{_SESSION_ID_1}/run",
            {"unexpected": True},
        ),
        (
            f"/api/user/profile-onboarding/session/{_SESSION_ID_1}/run",
            {"expected_block_index": 0},
        ),
        (
            f"/api/user/profile-onboarding/session/{_SESSION_ID_1}/run",
            {"request_id": "step-without-index"},
        ),
        (
            f"/api/user/profile-onboarding/session/{_SESSION_ID_1}/run",
            {"expected_block_index": True, "request_id": "step"},
        ),
        (
            f"/api/user/profile-onboarding/session/{_SESSION_ID_1}/run",
            {"expected_block_index": -1, "request_id": "step"},
        ),
        (
            f"/api/user/profile-onboarding/session/{_SESSION_ID_1}/run",
            {"expected_block_index": 0, "request_id": ""},
        ),
        (
            "/api/user/profile-onboarding/session/too-short/run",
            {},
        ),
        (
            f"/api/user/profile-onboarding/session/{'g' * 32}/run",
            {},
        ),
        ("/api/user/profile-onboarding/complete", {}),
        ("/api/user/profile-onboarding/complete", []),
        (
            "/api/user/profile-onboarding/complete",
            {"learner_profile": 123, "trigger_source": "guided"},
        ),
        (
            "/api/user/profile-onboarding/complete",
            {
                "learner_profile": "profile",
                "trigger_source": "guided",
                "session_id": "",
            },
        ),
        (
            "/api/user/profile-onboarding/complete",
            {
                "skipped": False,
                "learner_profile": "mixed",
                "trigger_source": "guided",
            },
        ),
        (
            "/api/user/profile-onboarding/complete",
            {
                "learner_profile": "profile",
                "trigger_source": "guided",
                "session_id": None,
            },
        ),
        ("/api/user/profile-onboarding/skip", {"session_id": 1}),
        ("/api/user/profile-onboarding/skip", {"unexpected": True}),
    ],
)
def test_profile_onboarding_mutations_reject_invalid_shapes(
    monkeypatch, test_client, path, payload
):
    _authenticate(monkeypatch)
    response = test_client.post(path, headers={"Token": "token"}, json=payload)
    assert response.get_json(force=True)["code"] != 0


@pytest.mark.parametrize("trigger_source", ["unknown", False, [], {}])
def test_profile_onboarding_complete_rejects_invalid_trigger_source_as_param_error(
    monkeypatch, test_client, trigger_source
):
    _authenticate(monkeypatch)

    response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={"learner_profile": "profile", "trigger_source": trigger_source},
    )

    assert response.get_json(force=True)["code"] == 2001


@pytest.mark.parametrize(
    "payload",
    [
        {
            "learner_profile": "profile",
            "trigger_source": "guided",
            "nickname": None,
        },
        {
            "learner_profile": "profile",
            "trigger_source": "guided",
            "nickname": 123,
        },
        {"skipped": True, "nickname": "legacy must reject this field"},
        {
            "skipped": False,
            "learner_profile": "mixed",
            "trigger_source": "guided",
            "nickname": "mixed",
        },
        {
            "learner_profile": "profile",
            "trigger_source": "guided",
            "nickname": "valid",
            "unknown": True,
        },
    ],
)
def test_profile_onboarding_complete_rejects_invalid_nickname_contract_without_writes(
    monkeypatch, test_client, payload
):
    _authenticate(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "flaskr.route.user.complete_profile_onboarding",
        lambda app, **kwargs: calls.append(("legacy", kwargs)),
    )
    monkeypatch.setattr(
        "flaskr.route.user.complete_profile_onboarding_v2",
        lambda app, **kwargs: calls.append(("v2", kwargs)),
    )
    monkeypatch.setattr(
        "flaskr.route.user._delete_profile_onboarding_session",
        lambda app, **kwargs: calls.append(("cleanup", kwargs)),
    )

    response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json=payload,
    )

    assert response.get_json(force=True)["code"] == 2001
    assert calls == []


def test_learner_profile_routes_delegate(monkeypatch, test_client):
    user = _authenticate(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "flaskr.route.user.get_learner_profile",
        lambda **kwargs: calls.append(("get", kwargs)) or {"learner_profile": "old"},
    )
    monkeypatch.setattr(
        "flaskr.route.user.replace_learner_profile",
        lambda app, **kwargs: (
            calls.append(("put", kwargs))
            or {"learner_profile": kwargs["learner_profile"]}
        ),
    )
    monkeypatch.setattr(
        "flaskr.route.user.clear_learner_profile",
        lambda **kwargs: calls.append(("delete", kwargs)) or {"learner_profile": ""},
    )

    fetched = test_client.get("/api/user/learner-profile", headers={"Token": "token"})
    updated = test_client.put(
        "/api/user/learner-profile",
        headers={"Token": "token"},
        json={"learner_profile": "new profile"},
    )
    cleared = test_client.delete(
        "/api/user/learner-profile", headers={"Token": "token"}
    )

    assert _data(fetched) == {"learner_profile": "old"}
    assert _data(updated) == {"learner_profile": "new profile"}
    assert _data(cleared) == {"learner_profile": ""}
    assert calls == [
        ("get", {"user_id": user.user_id}),
        (
            "put",
            {
                "user_id": user.user_id,
                "learner_profile": "new profile",
                "nickname": None,
            },
        ),
        ("delete", {"user_id": user.user_id}),
    ]


@pytest.mark.parametrize(
    "payload",
    [None, [], {"learner_profile": 123}, {"learner_profile": "ok", "x": 1}],
)
def test_learner_profile_update_rejects_invalid_shapes(
    monkeypatch, test_client, payload
):
    _authenticate(monkeypatch)
    kwargs = {"headers": {"Token": "token"}}
    if payload is not None:
        kwargs["json"] = payload
    response = test_client.put("/api/user/learner-profile", **kwargs)
    assert response.get_json(force=True)["code"] != 0


def test_operator_profile_onboarding_config_routes_delegate(monkeypatch, test_client):
    user = _authenticate(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.route.get_operator_profile_onboarding_config",
        lambda app: {"enabled": False, "config_revision": 3},
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.route.update_operator_profile_onboarding_config",
        lambda app, **kwargs: (
            calls.append(kwargs)
            or {"enabled": kwargs["payload"]["enabled"], "config_revision": 4}
        ),
    )

    fetched = test_client.get(
        "/api/shifu/admin/operations/profile-onboarding",
        headers={"Token": "token"},
    )
    updated = test_client.post(
        "/api/shifu/admin/operations/profile-onboarding",
        headers={"Token": "token"},
        json={
            "enabled": True,
            "markdownflow": "flow",
            "document_prompt": "prompt",
        },
    )

    assert _data(fetched) == {"enabled": False, "config_revision": 3}
    assert _data(updated) == {"enabled": True, "config_revision": 4}
    assert calls == [
        {
            "payload": {
                "enabled": True,
                "markdownflow": "flow",
                "document_prompt": "prompt",
            },
            "operator_user_bid": user.user_id,
        }
    ]


def test_operator_profile_onboarding_preview_start_is_isolated_and_purpose_scoped(
    monkeypatch, test_client
):
    user = _authenticate(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.route.get_operator_profile_onboarding_config",
        lambda app: {"config_revision": 5},
    )
    monkeypatch.setattr(
        "flaskr.service.profile_research.api.start_profile_research_session",
        lambda app, **kwargs: (
            calls.append(kwargs)
            or {"session_id": "preview-session", "purpose": kwargs["purpose"]}
        ),
    )

    response = test_client.post(
        "/api/shifu/admin/operations/profile-onboarding/preview",
        headers={"Token": "token"},
        json={
            "markdownflow": "  unsaved editor flow  ",
            "document_prompt": "  unsaved prompt  ",
            "language": "fr_fr",
        },
    )

    assert _data(response) == {
        "session_id": "preview-session",
        "purpose": "profile-onboarding-preview",
    }
    assert calls == [
        {
            "user_bid": user.user_id,
            "document": "unsaved editor flow",
            "document_prompt": "unsaved prompt",
            "purpose": "profile-onboarding-preview",
            "config_revision": 5,
            "output_language": "fr-FR",
        }
    ]


def test_operator_profile_onboarding_preview_rejects_unanswerable_interaction(
    monkeypatch, test_client
):
    _authenticate(monkeypatch)
    saved_sessions = []
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.route.get_operator_profile_onboarding_config",
        lambda app: {"config_revision": 5},
    )
    monkeypatch.setattr(
        "flaskr.service.profile_research.runtime._ProfileResearchSessionStore.save",
        lambda _store, session: saved_sessions.append(session),
    )

    response = test_client.post(
        "/api/shifu/admin/operations/profile-onboarding/preview",
        headers={"Token": "token"},
        json={"markdownflow": "?[]"},
    )

    assert response.get_json(force=True)["code"] != 0
    assert saved_sessions == []


def test_operator_profile_onboarding_preview_rejects_oversized_button_values(
    monkeypatch, test_client
):
    _authenticate(monkeypatch)
    saved_sessions = []
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.route.get_operator_profile_onboarding_config",
        lambda app: {"config_revision": 5},
    )
    monkeypatch.setattr(
        "flaskr.service.profile_research.runtime._ProfileResearchSessionStore.save",
        lambda _store, session: saved_sessions.append(session),
    )

    response = test_client.post(
        "/api/shifu/admin/operations/profile-onboarding/preview",
        headers={"Token": "token"},
        json={
            "markdownflow": f"?[Short//{'x' * 4_001} | Detailed//full]",
        },
    )

    assert response.get_json(force=True)["code"] != 0
    assert saved_sessions == []


def test_operator_profile_onboarding_preview_rejects_unsavable_utf8_payload(
    monkeypatch, test_client
):
    from flaskr.service.common import profile_onboarding as module

    _authenticate(monkeypatch)
    saved_sessions = []
    monkeypatch.setattr(module, "_now_iso", lambda: "2026-08-16T00:00:00Z")
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.route.get_operator_profile_onboarding_config",
        lambda app: {
            "config_revision": 5,
            "version": 50,
            "allowed_variable_keys": ["compatibility-only"],
        },
    )
    monkeypatch.setattr(
        "flaskr.service.profile_research.runtime._ProfileResearchSessionStore.save",
        lambda _store, session: saved_sessions.append(session),
    )
    markdownflow = _markdownflow_for_preview_config_size(
        target_bytes=module.PROFILE_ONBOARDING_CONFIG_MAX_UTF8_BYTES
    )

    response = test_client.post(
        "/api/shifu/admin/operations/profile-onboarding/preview",
        headers={"Token": "token"},
        json={"markdownflow": markdownflow + "测"},
    )

    assert response.get_json(force=True)["code"] != 0
    assert saved_sessions == []


def test_operator_profile_onboarding_preview_accepts_exact_publish_size(
    monkeypatch, test_client
):
    from flaskr.service.common import profile_onboarding as module

    _authenticate(monkeypatch)
    saved_sessions = []
    monkeypatch.setattr(module, "_now_iso", lambda: "2026-08-16T00:00:00Z")
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.route.get_operator_profile_onboarding_config",
        lambda app: {"config_revision": 5, "version": 50},
    )
    monkeypatch.setattr(
        "flaskr.service.profile_research.runtime._ProfileResearchSessionStore.save",
        lambda _store, session: saved_sessions.append(session),
    )
    markdownflow = _markdownflow_for_preview_config_size(
        target_bytes=module.PROFILE_ONBOARDING_CONFIG_MAX_UTF8_BYTES
    )

    response = test_client.post(
        "/api/shifu/admin/operations/profile-onboarding/preview",
        headers={"Token": "token"},
        json={"markdownflow": markdownflow},
    )

    assert response.get_json(force=True)["code"] == 0
    assert len(saved_sessions) == 1


def test_operator_profile_onboarding_preview_rejects_oversized_document_prompt(
    monkeypatch, test_client
):
    _authenticate(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.route.get_operator_profile_onboarding_config",
        lambda app: {"config_revision": 5},
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.route.create_operator_profile_onboarding_preview_session",
        lambda app, **kwargs: calls.append(kwargs),
    )

    response = test_client.post(
        "/api/shifu/admin/operations/profile-onboarding/preview",
        headers={"Token": "token"},
        json={
            "markdownflow": "?[Continue]",
            "document_prompt": "x"
            * (PROFILE_ONBOARDING_DOCUMENT_PROMPT_MAX_CODEPOINTS + 1),
        },
    )

    assert response.get_json(force=True)["code"] != 0
    assert calls == []


def test_operator_profile_onboarding_preview_run_enforces_owner_and_purpose(
    monkeypatch, test_client
):
    from flaskr.route.common import make_common_response

    user = _authenticate(monkeypatch)
    calls = []

    def fake_stream(app, **kwargs):
        calls.append(kwargs)
        yield {"type": "done"}

    monkeypatch.setattr(
        "flaskr.service.profile_research.api.stream_profile_research_session",
        fake_stream,
    )
    monkeypatch.setattr(
        "flaskr.service.profile_research.api.build_profile_research_sse_response",
        lambda app, event_iter_factory, log_context: make_common_response(
            {
                "events": list(event_iter_factory()),
                "log_context": log_context,
            }
        ),
    )

    response = test_client.post(
        f"/api/shifu/admin/operations/profile-onboarding/preview/{_SESSION_ID_2}/run",
        headers={"Token": "token"},
        json={
            "user_input": {"experience": ["三年"]},
            "expected_block_index": 4,
            "request_id": "operator-step-4",
        },
    )

    assert _data(response) == {
        "events": [{"type": "done"}],
        "log_context": "operator profile onboarding preview",
    }
    assert calls == [
        {
            "user_bid": user.user_id,
            "session_id": _SESSION_ID_2,
            "user_input": {"experience": ["三年"]},
            "expected_purpose": "profile-onboarding-preview",
            "expected_block_index": 4,
            "request_id": "operator-step-4",
        }
    ]


def test_operator_profile_onboarding_preview_start_maps_busy_error(
    monkeypatch, test_client
):
    _authenticate(monkeypatch)
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.route.get_operator_profile_onboarding_config",
        lambda app: {"config_revision": 5},
    )

    def raise_busy_error(app, **kwargs):
        raise ProfileResearchSessionBusy("busy")

    monkeypatch.setattr(
        "flaskr.service.profile_research.api.start_profile_research_session",
        raise_busy_error,
    )

    response = test_client.post(
        "/api/shifu/admin/operations/profile-onboarding/preview",
        headers={"Token": "token"},
        json={"markdownflow": "?[继续]"},
    )

    assert response.get_json(force=True)["code"] == 4013


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"enabled": True, "markdownflow": "flow", "revision": 4},
    ],
)
def test_operator_profile_onboarding_config_rejects_invalid_shapes(
    monkeypatch, test_client, payload
):
    _authenticate(monkeypatch)
    kwargs = {"headers": {"Token": "token"}}
    if payload is not None:
        kwargs["json"] = payload
    response = test_client.post(
        "/api/shifu/admin/operations/profile-onboarding", **kwargs
    )
    assert response.get_json(force=True)["code"] != 0


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/shifu/admin/operations/profile-onboarding/preview",
            [],
        ),
        (
            "/api/shifu/admin/operations/profile-onboarding/preview",
            {"markdownflow": ""},
        ),
        (
            "/api/shifu/admin/operations/profile-onboarding/preview",
            {"markdownflow": "flow", "document_prompt": 3},
        ),
        (
            "/api/shifu/admin/operations/profile-onboarding/preview",
            {"markdownflow": "flow", "language": False},
        ),
        (
            "/api/shifu/admin/operations/profile-onboarding/preview",
            {"markdownflow": "flow", "language": "unsupported"},
        ),
        (
            f"/api/shifu/admin/operations/profile-onboarding/preview/{_SESSION_ID_2}/run",
            {"user_input": {"name": []}},
        ),
        (
            f"/api/shifu/admin/operations/profile-onboarding/preview/{_SESSION_ID_2}/run",
            {"user_input": {"name": [1]}},
        ),
        (
            f"/api/shifu/admin/operations/profile-onboarding/preview/{_SESSION_ID_2}/run",
            {"unexpected": True},
        ),
        (
            f"/api/shifu/admin/operations/profile-onboarding/preview/{_SESSION_ID_2}/run",
            {"expected_block_index": 0},
        ),
        (
            f"/api/shifu/admin/operations/profile-onboarding/preview/{_SESSION_ID_2}/run",
            {"request_id": "step-without-index"},
        ),
        (
            f"/api/shifu/admin/operations/profile-onboarding/preview/{_SESSION_ID_2}/run",
            {"expected_block_index": False, "request_id": "step"},
        ),
        (
            f"/api/shifu/admin/operations/profile-onboarding/preview/{_SESSION_ID_2}/run",
            {"expected_block_index": 0, "request_id": " "},
        ),
        (
            "/api/shifu/admin/operations/profile-onboarding/preview/too-short/run",
            {},
        ),
        (
            f"/api/shifu/admin/operations/profile-onboarding/preview/{'g' * 32}/run",
            {},
        ),
    ],
)
def test_operator_profile_onboarding_preview_rejects_invalid_shapes(
    monkeypatch, test_client, path, payload
):
    _authenticate(monkeypatch)
    response = test_client.post(path, headers={"Token": "token"}, json=payload)
    assert response.get_json(force=True)["code"] != 0


def test_operator_profile_onboarding_config_requires_operator(monkeypatch, test_client):
    _authenticate(monkeypatch, is_operator=False)
    response = test_client.get(
        "/api/shifu/admin/operations/profile-onboarding",
        headers={"Token": "token"},
    )
    assert response.get_json(force=True)["code"] != 0

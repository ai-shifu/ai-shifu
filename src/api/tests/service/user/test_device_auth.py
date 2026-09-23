"""Verify the device authorization flow used by command-line clients."""

import json

import pytest
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import device_auth
from flaskr.service.user.device_auth import (
    STATUS_APPROVED,
    STATUS_DENIED,
    STATUS_PENDING,
    approve_device_authorization,
    create_device_authorization,
    deny_device_authorization,
    format_user_code,
    get_device_authorization,
    normalize_user_code,
    poll_device_authorization,
    record_new_user_skill_attribution,
)
from flaskr.service.user.models import UserSkillAttribution

USER_ID = "test-user-bid-0001"


def _start(app: object) -> dict:
    return create_device_authorization(
        app,
        device_name="MacBook-Pro",
        device_os="macOS 15",
        client_version="1.2.6",
        client_ip="203.0.113.7",
    )


def test_full_flow_issues_token_after_approval(app: object) -> None:
    with app.test_request_context():
        started = _start(app)

        pending = get_device_authorization(app, user_code=started["user_code"])
        assert pending["device_name"] == "MacBook-Pro"
        assert pending["device_os"] == "macOS 15"

        waiting = poll_device_authorization(app, device_code=started["device_code"])
        assert waiting["status"] == STATUS_PENDING
        assert waiting["token"] == ""

        approve_device_authorization(
            app, user_code=started["user_code"], user_id=USER_ID
        )

        issued = poll_device_authorization(app, device_code=started["device_code"])
        assert issued["status"] == STATUS_APPROVED
        assert issued["token"]


def test_verification_url_never_carries_the_device_code(app: object) -> None:
    """The device code is the CLI's secret; leaking it would leak the token."""
    with app.test_request_context():
        started = _start(app)

        assert started["device_code"] not in started["verification_uri_complete"]
        assert started["device_code"] not in started["verification_uri"]
        assert started["user_code"] in started["verification_uri_complete"]


def test_new_user_attribution_is_resolved_from_pending_device_request(
    app: object,
) -> None:
    handoff_id = "123e4567-e89b-12d3-a456-426614174001"
    with app.test_request_context():
        started = create_device_authorization(
            app,
            registration_attribution={
                "host_platform": "doubao",
                "skill_id": "ai-shifu-course-creator",
                "skill_version": "2.0.0",
                "handoff_id": handoff_id,
            },
        )
        pending = get_device_authorization(app, user_code=started["user_code"])
        assert pending["registration_attribution"] == {
            "host_platform": "doubao",
            "skill_id": "ai-shifu-course-creator",
            "skill_version": "2.0.0",
        }
        assert handoff_id not in json.dumps(pending)
        with unit_of_work():
            record_new_user_skill_attribution(
                app, user_code=started["user_code"], user_id=USER_ID
            )
        approve_device_authorization(
            app, user_code=started["user_code"], user_id=USER_ID
        )

        saved = UserSkillAttribution.query.filter_by(user_bid=USER_ID).one()
        assert saved.host_platform == "doubao"
        assert saved.skill_id == "ai-shifu-course-creator"
        assert saved.handoff_id == handoff_id


def test_pending_device_without_skill_attribution_keeps_existing_shape(
    app: object,
) -> None:
    with app.test_request_context():
        started = _start(app)

        pending = get_device_authorization(app, user_code=started["user_code"])

        assert "registration_attribution" not in pending


def test_existing_first_touch_attribution_is_not_replaced(app: object) -> None:
    user_id = "test-user-bid-0002"
    with app.test_request_context():
        first = create_device_authorization(
            app,
            registration_attribution={
                "host_platform": "direct",
                "skill_id": "ai-shifu-course-creator",
                "skill_version": "1.0.0",
                "handoff_id": "123e4567-e89b-12d3-a456-426614174002",
            },
        )
        second = create_device_authorization(
            app,
            registration_attribution={
                "host_platform": "codex",
                "skill_id": "ai-shifu-course-creator",
                "skill_version": "1.1.0",
                "handoff_id": "123e4567-e89b-12d3-a456-426614174003",
            },
        )
        with unit_of_work():
            record_new_user_skill_attribution(
                app, user_code=first["user_code"], user_id=user_id
            )
        with unit_of_work():
            record_new_user_skill_attribution(
                app, user_code=second["user_code"], user_id=user_id
            )
        approve_device_authorization(app, user_code=first["user_code"], user_id=user_id)
        approve_device_authorization(
            app, user_code=second["user_code"], user_id=user_id
        )

        saved = UserSkillAttribution.query.filter_by(user_bid=user_id).one()
        assert saved.host_platform == "direct"


def test_denied_handoff_does_not_persist_new_user_attribution(app: object) -> None:
    denied_user_id = "test-user-bid-denied"
    with app.test_request_context():
        started = create_device_authorization(
            app,
            registration_attribution={
                "host_platform": "direct",
                "skill_id": "ai-shifu-course-creator",
                "skill_version": "1.0.0",
                "handoff_id": "123e4567-e89b-12d3-a456-426614174004",
            },
        )
        record_new_user_skill_attribution(
            app, user_code=started["user_code"], user_id=denied_user_id
        )
        deny_device_authorization(app, user_code=started["user_code"])

        assert (
            UserSkillAttribution.query.filter_by(user_bid=denied_user_id).count() == 0
        )


def test_approval_finalizes_cache_before_attribution_can_wait(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.test_request_context():
        started = create_device_authorization(
            app,
            registration_attribution={
                "host_platform": "direct",
                "skill_id": "ai-shifu-course-creator",
                "skill_version": "1.0.0",
                "handoff_id": "123e4567-e89b-12d3-a456-426614174006",
            },
        )
        record_new_user_skill_attribution(
            app, user_code=started["user_code"], user_id=USER_ID
        )

        def delayed_persistence(**_kwargs: object) -> None:
            with pytest.raises(AppError):
                deny_device_authorization(app, user_code=started["user_code"])

        monkeypatch.setattr(
            device_auth, "_add_first_user_attribution", delayed_persistence
        )
        approve_device_authorization(
            app, user_code=started["user_code"], user_id=USER_ID
        )

        result = poll_device_authorization(app, device_code=started["device_code"])
        assert result["status"] == STATUS_APPROVED


def test_repeated_approval_recovers_attribution_persistence_failure(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = "test-user-bid-retry-approval"
    with app.test_request_context():
        started = create_device_authorization(
            app,
            registration_attribution={
                "host_platform": "direct",
                "skill_id": "ai-shifu-course-creator",
                "skill_version": "1.0.0",
                "handoff_id": "123e4567-e89b-12d3-a456-426614174005",
            },
        )
        record_new_user_skill_attribution(
            app, user_code=started["user_code"], user_id=user_id
        )
        original = device_auth._add_first_user_attribution

        def fail_once(**_kwargs: object) -> None:
            error_message = "database unavailable"
            raise RuntimeError(error_message)

        monkeypatch.setattr(device_auth, "_add_first_user_attribution", fail_once)
        with pytest.raises(RuntimeError, match="database unavailable"):
            approve_device_authorization(
                app, user_code=started["user_code"], user_id=user_id
            )
        waiting = poll_device_authorization(app, device_code=started["device_code"])
        assert waiting["status"] == STATUS_PENDING
        assert waiting["token"] == ""

        monkeypatch.setattr(device_auth, "_add_first_user_attribution", original)
        approve_device_authorization(
            app, user_code=started["user_code"], user_id=user_id
        )
        assert UserSkillAttribution.query.filter_by(user_bid=user_id).count() == 1
        collected = poll_device_authorization(app, device_code=started["device_code"])
        assert collected["status"] == STATUS_APPROVED
        assert collected["token"]


def test_registration_attribution_rejects_approval_by_another_user(
    app: object,
) -> None:
    registered_user_id = "test-user-bid-registration-owner"
    with app.test_request_context():
        started = create_device_authorization(
            app,
            registration_attribution={
                "host_platform": "direct",
                "skill_id": "ai-shifu-course-creator",
                "skill_version": "1.0.0",
                "handoff_id": "123e4567-e89b-12d3-a456-426614174007",
            },
        )
        record_new_user_skill_attribution(
            app,
            user_code=started["user_code"],
            user_id=registered_user_id,
        )

        with pytest.raises(AppError) as mismatch:
            approve_device_authorization(
                app,
                user_code=started["user_code"],
                user_id="test-user-bid-different-approver",
            )
        assert (
            mismatch.value.code == ERROR_CODE["server.user.deviceAuthAccountMismatch"]
        )
        waiting = poll_device_authorization(
            app,
            device_code=started["device_code"],
        )
        assert waiting["status"] == STATUS_PENDING

        approve_device_authorization(
            app,
            user_code=started["user_code"],
            user_id=registered_user_id,
        )
        collected = poll_device_authorization(
            app,
            device_code=started["device_code"],
        )
        assert collected["status"] == STATUS_APPROVED
        assert collected["token"]


def test_token_can_only_be_collected_once(app: object) -> None:
    with app.test_request_context():
        started = _start(app)
        approve_device_authorization(
            app, user_code=started["user_code"], user_id=USER_ID
        )
        assert poll_device_authorization(app, device_code=started["device_code"])[
            "token"
        ]

        with pytest.raises(AppError):
            poll_device_authorization(app, device_code=started["device_code"])


def test_denied_request_stops_the_client(app: object) -> None:
    with app.test_request_context():
        started = _start(app)
        deny_device_authorization(app, user_code=started["user_code"])

        result = poll_device_authorization(app, device_code=started["device_code"])
        assert result["status"] == STATUS_DENIED
        assert result["token"] == ""


def test_request_cannot_be_approved_twice(app: object) -> None:
    with app.test_request_context():
        started = _start(app)
        approve_device_authorization(
            app, user_code=started["user_code"], user_id=USER_ID
        )

        with pytest.raises(AppError):
            approve_device_authorization(
                app, user_code=started["user_code"], user_id=USER_ID
            )


def test_unknown_pairing_code_is_rejected(app: object) -> None:
    with app.test_request_context(), pytest.raises(AppError):
        get_device_authorization(app, user_code="XXX-XXX")


def test_pairing_code_guessing_is_rate_limited(app: object) -> None:
    with app.test_request_context():
        attacker_ip = "198.51.100.9"
        max_attempts = int(app.config.get("DEVICE_AUTH_MAX_LOOKUP_ATTEMPTS", 10))

        for _ in range(max_attempts):
            with pytest.raises(AppError):
                get_device_authorization(
                    app, user_code="AAA-AAA", client_ip=attacker_ip
                )

        # A valid code must now be refused too: the IP is out of attempts.
        started = _start(app)
        with pytest.raises(AppError):
            get_device_authorization(
                app, user_code=started["user_code"], client_ip=attacker_ip
            )


def test_a_valid_lookup_does_not_refill_the_guess_budget(app: object) -> None:
    """A code the attacker legitimately holds must not reset their budget.

    The final lookup uses a *valid* code on purpose: an unknown code is refused
    either way, so it could not tell a spent budget apart from a fresh one.
    """
    with app.test_request_context():
        attacker_ip = "198.51.100.21"
        max_attempts = int(app.config.get("DEVICE_AUTH_MAX_LOOKUP_ATTEMPTS", 10))
        own_request = _start(app)
        other_request = _start(app)

        # Spend every attempt but one, then succeed with a code they do hold.
        for _ in range(max_attempts - 1):
            with pytest.raises(AppError):
                get_device_authorization(
                    app, user_code="AAA-AAA", client_ip=attacker_ip
                )
        get_device_authorization(
            app, user_code=own_request["user_code"], client_ip=attacker_ip
        )

        # The budget is spent, so even a valid code must now be refused.
        with pytest.raises(AppError):
            get_device_authorization(
                app, user_code=other_request["user_code"], client_ip=attacker_ip
            )


def test_opening_requests_is_rate_limited(app: object) -> None:
    """Starting a request is unauthenticated, so it cannot be unbounded."""
    with app.test_request_context():
        client_ip = "198.51.100.42"
        max_requests = int(app.config.get("DEVICE_AUTH_MAX_REQUESTS", 20))

        for _ in range(max_requests):
            create_device_authorization(app, device_name="flood", client_ip=client_ip)

        with pytest.raises(AppError) as refused:
            create_device_authorization(app, device_name="flood", client_ip=client_ip)
        assert refused.value.code == ERROR_CODE["server.user.deviceAuthTooManyRequests"]


def test_a_decided_request_cannot_be_decided_again(app: object) -> None:
    """Conflicting decisions must not both succeed."""
    with app.test_request_context():
        started = _start(app)
        deny_device_authorization(app, user_code=started["user_code"])

        with pytest.raises(AppError):
            approve_device_authorization(
                app, user_code=started["user_code"], user_id=USER_ID
            )


def test_pairing_code_is_accepted_in_any_readable_form(app: object) -> None:
    with app.test_request_context():
        started = _start(app)
        typed_by_hand = started["user_code"].replace("-", "").lower()

        pending = get_device_authorization(app, user_code=typed_by_hand)
        assert pending["user_code"] == started["user_code"]


def test_user_code_helpers_round_trip() -> None:
    assert normalize_user_code(" ac4-7hk ") == "AC47HK"
    assert format_user_code("AC47HK") == "AC4-7HK"


def test_approval_requires_a_user(app: object) -> None:
    with app.test_request_context():
        started = _start(app)
        with pytest.raises(AppError):
            approve_device_authorization(
                app, user_code=started["user_code"], user_id=""
            )


def test_authorize_route_returns_pairing_material(test_client: object) -> None:
    response = test_client.post(
        "/api/user/device/authorize",
        data=json.dumps({"device_name": "CI runner", "device_os": "Linux"}),
        content_type="application/json",
    )
    body = response.get_json(force=True)

    assert response.status_code == 200
    assert body["code"] == 0
    assert body["data"]["user_code"]
    assert body["data"]["device_code"]
    assert body["data"]["interval"] >= 1


def test_token_route_reports_pending_without_erroring(test_client: object) -> None:
    started = test_client.post(
        "/api/user/device/authorize",
        data=json.dumps({}),
        content_type="application/json",
    ).get_json(force=True)["data"]

    response = test_client.post(
        "/api/user/device/token",
        data=json.dumps({"device_code": started["device_code"]}),
        content_type="application/json",
    )
    body = response.get_json(force=True)

    assert response.status_code == 200
    assert body["code"] == 0
    assert body["data"]["status"] == STATUS_PENDING

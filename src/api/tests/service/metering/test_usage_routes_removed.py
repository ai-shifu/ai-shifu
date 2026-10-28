"""Keep the removed cross-tenant usage-summary route from coming back."""

from types import SimpleNamespace

import pytest
from flask import Flask
from flask.testing import FlaskClient

USAGE_SUMMARY_PATH = "/api/metering/usage-summary"


def test_full_app_registers_no_metering_routes(app: Flask) -> None:
    # create_app loads every @inject route registrar, so a reintroduced
    # metering route would show up here even without an explicit import.
    metering_rules = sorted(
        rule.rule
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/metering")
    )

    assert metering_rules == []


def test_signed_in_learner_cannot_read_usage_summary(
    test_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    learner = SimpleNamespace(
        user_id="learner-1",
        is_creator=False,
        is_operator=False,
        language="en-US",
    )
    monkeypatch.setattr("flaskr.route.user.validate_user", lambda _app, _token: learner)

    response = test_client.get(
        USAGE_SUMMARY_PATH,
        query_string={"user_bid": "another-user", "shifu_bid": "another-course"},
        headers={"Token": "learner-token"},
    )

    # The HTTPException handler reports routing errors in the JSON envelope.
    payload = response.get_json(silent=True) or {}
    assert payload.get("code") == 404, response.get_data(as_text=True)[:200]
    assert "llm" not in str(payload.get("data"))

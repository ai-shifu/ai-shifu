"""Protect credentials and transcripts across shared HTTP middleware."""

from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from flask import Flask, Request, Response, jsonify, request
from flaskr.common.http import init_sensitive_body_policy, sensitive_body
from flaskr.common.log import init_log
from werkzeug.test import EnvironBuilder


@pytest.fixture
def body_policy_app(tmp_path: Path) -> Iterator[Flask]:
    app = Flask("sensitive-body-policy-test")
    app.testing = True
    app.config["LOGGING_PATH"] = str(tmp_path / "request.log")
    # Match production: the logger must not parse a sensitive body, then the
    # policy limits any authentication/context hook that parses JSON next.
    init_log(app)
    init_sensitive_body_policy(app)
    app.logger.propagate = True

    @app.before_request
    def simulate_shared_auth_body_parser() -> None:
        if request.is_json:
            request.get_json(silent=True)

    @app.post("/sensitive")
    @sensitive_body(max_bytes=1024)
    def sensitive_endpoint() -> Response:
        return jsonify(
            ephemeral_token="auth_tokens/private-token",
            history="private earlier question",
        )

    @app.post("/ordinary")
    def ordinary_endpoint() -> Response:
        return jsonify(result="ordinary response")

    yield app
    for handler in list(app.logger.handlers):
        app.logger.removeHandler(handler)
        handler.close()


def test_sensitive_bodies_are_not_logged_or_cached(
    body_policy_app: Flask, caplog: pytest.LogCaptureFixture
) -> None:
    response = body_policy_app.test_client().post(
        "/sensitive",
        json={
            "turns": [
                {
                    "user_transcript": "private learner question",
                    "played_answer_transcript": "private model answer",
                }
            ]
        },
    )
    assert response.json["ephemeral_token"] == "auth_tokens/private-token"
    assert response.headers["Cache-Control"] == "no-store"
    assert "Request body: <sensitive body omitted>" in caplog.text
    assert "Response: <sensitive body omitted>" in caplog.text
    for private_value in (
        "auth_tokens/private-token",
        "private earlier question",
        "private learner question",
        "private model answer",
    ):
        assert private_value not in caplog.text


@pytest.mark.parametrize("known_length", [True, False])
def test_size_limit_precedes_shared_auth_parsing(
    body_policy_app: Flask, known_length: bool, caplog: pytest.LogCaptureFixture
) -> None:
    body = BytesIO(b'{"private":"' + b"x" * 4096 + b'"}')
    environment = EnvironBuilder(
        path="/sensitive", method="POST", content_type="application/json"
    ).get_environ()
    environment["wsgi.input"] = body
    environment["wsgi.input_terminated"] = True
    if known_length:
        environment["CONTENT_LENGTH"] = str(len(body.getvalue()))
    else:
        environment.pop("CONTENT_LENGTH", None)
    response = body_policy_app.test_client().open(Request(environment))
    assert response.status_code == 413
    assert body.tell() == (0 if known_length else 1025)
    assert response.headers["Cache-Control"] == "no-store"
    assert "private" not in caplog.text


def test_sensitive_policy_preserves_a_stricter_global_body_limit(
    body_policy_app: Flask,
) -> None:
    body_policy_app.config["MAX_CONTENT_LENGTH"] = 10
    response = body_policy_app.test_client().post("/sensitive", json={"text": "x" * 20})
    assert response.status_code == 413


def test_other_routes_keep_existing_logging_and_body_limits(
    body_policy_app: Flask, caplog: pytest.LogCaptureFixture
) -> None:
    response = body_policy_app.test_client().post(
        "/ordinary", json={"text": "ordinary request", "padding": "x" * 2048}
    )
    assert response.status_code == 200
    assert "ordinary request" in caplog.text
    assert "ordinary response" in caplog.text
    assert "Cache-Control" not in response.headers


def test_unmatched_routes_do_not_require_body_policy(body_policy_app: Flask) -> None:
    assert body_policy_app.test_client().get("/not-found").status_code == 404

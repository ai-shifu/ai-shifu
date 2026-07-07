from types import SimpleNamespace

from flask import Flask, jsonify

import flaskr.route.user as user_route
from flaskr.i18n import clear_language, get_current_language
from flaskr.route.user import register_user_handler


def test_authenticated_request_prefers_accept_language_for_runtime_context(
    monkeypatch,
):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test"
    monkeypatch.setattr(
        user_route,
        "validate_user",
        lambda _app, _token: SimpleNamespace(user_id="user-1", language="en-US"),
    )
    register_user_handler(app, "/api/user")

    @app.route("/runtime-language")
    def runtime_language():
        return jsonify({"language": get_current_language()})

    try:
        response = app.test_client().get(
            "/runtime-language",
            headers={"Token": "token", "Accept-Language": "zh-CN,zh;q=0.9"},
        )
        assert response.status_code == 200
        assert response.get_json() == {"language": "zh-CN"}
    finally:
        clear_language()


def test_authenticated_request_normalizes_accept_language_for_runtime_context(
    monkeypatch,
):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test"
    monkeypatch.setattr(
        user_route,
        "validate_user",
        lambda _app, _token: SimpleNamespace(user_id="user-1", language="en-US"),
    )
    register_user_handler(app, "/api/user")

    @app.route("/runtime-language")
    def runtime_language():
        return jsonify({"language": get_current_language()})

    try:
        response = app.test_client().get(
            "/runtime-language",
            headers={"Token": "token", "Accept-Language": "zh-cn,zh;q=0.9"},
        )
        assert response.status_code == 200
        assert response.get_json() == {"language": "zh-CN"}
    finally:
        clear_language()


def test_authenticated_request_reads_json_payload_language_for_runtime_context(
    monkeypatch,
):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test"
    monkeypatch.setattr(
        user_route,
        "validate_user",
        lambda _app, _token: SimpleNamespace(user_id="user-1", language="en-US"),
    )
    register_user_handler(app, "/api/user")

    @app.route("/runtime-language", methods=["POST"])
    def runtime_language():
        return jsonify({"language": get_current_language()})

    try:
        response = app.test_client().post(
            "/runtime-language",
            headers={"Token": "token"},
            json={"language": "fr"},
        )
        assert response.status_code == 200
        assert response.get_json() == {"language": "fr-FR"}
    finally:
        clear_language()

from pathlib import Path

from flask import Flask

from flaskr.i18n import _translations, load_translations
from flaskr.route.common import register_common_handler


def _shared_i18n_root() -> Path:
    return Path(__file__).resolve().parents[3] / "i18n"


def test_common_handler_returns_translated_operation_failed_for_unhandled_exceptions(
    monkeypatch,
):
    monkeypatch.setenv("SHARED_I18N_ROOT", str(_shared_i18n_root()))
    app = Flask(__name__)
    load_translations(app)
    register_common_handler(app)

    @app.route("/boom")
    def _boom():
        raise RuntimeError("unexpected failure")

    with app.test_client() as client:
        response = client.get("/boom")

    assert response.status_code == 200
    assert response.get_json() == {
        "code": -1,
        "message": _translations["en-US"]["server.common.operationFailed"],
    }


def test_common_handler_uses_request_language_for_unhandled_exceptions(monkeypatch):
    monkeypatch.setenv("SHARED_I18N_ROOT", str(_shared_i18n_root()))
    app = Flask(__name__)
    load_translations(app)
    register_common_handler(app)

    @app.route("/boom-zh")
    def _boom_zh():
        raise RuntimeError("unexpected failure")

    with app.test_client() as client:
        response = client.get(
            "/boom-zh",
            headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "code": -1,
        "message": _translations["zh-CN"]["server.common.operationFailed"],
    }

    with app.test_client() as client:
        response = client.get(
            "/boom-zh",
            headers={"Accept-Language": "zh-cn,zh;q=0.9,en;q=0.8"},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "code": -1,
        "message": _translations["zh-CN"]["server.common.operationFailed"],
    }

    with app.test_client() as client:
        response = client.get(
            "/boom-zh",
            headers={"Accept-Language": "zh"},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "code": -1,
        "message": _translations["zh-CN"]["server.common.operationFailed"],
    }


def test_common_handler_uses_json_language_for_patch_requests(monkeypatch):
    monkeypatch.setenv("SHARED_I18N_ROOT", str(_shared_i18n_root()))
    app = Flask(__name__)
    load_translations(app)
    register_common_handler(app)

    @app.route("/boom-patch", methods=["PATCH"])
    def _boom_patch():
        raise RuntimeError("unexpected failure")

    with app.test_client() as client:
        response = client.patch(
            "/boom-patch",
            json={"language": "zh-cn"},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "code": -1,
        "message": _translations["zh-CN"]["server.common.operationFailed"],
    }

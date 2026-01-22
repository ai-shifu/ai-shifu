import os
import pytest
from types import SimpleNamespace
import flaskr.dao as dao
import flaskr.service.config.funcs as config_funcs

_dummy_lock = SimpleNamespace(
    acquire=lambda *args, **kwargs: False, release=lambda *args, **kwargs: None
)


@pytest.mark.usefixtures("app")
class TestProfileRoutes:
    # Avoid real Redis in app init
    os.environ["REDIS_HOST"] = ""
    os.environ["REDIS_PORT"] = ""
    dao.init_redis = lambda _app: None  # type: ignore
    config_funcs.redis = SimpleNamespace(
        get=lambda _key: None,
        set=lambda *args, **kwargs: None,
        lock=lambda *args, **kwargs: _dummy_lock,
    )

    def _mock_request_user(self, monkeypatch):
        monkeypatch.setattr(
            "flaskr.service.profile.routes.request",
            SimpleNamespace(user=SimpleNamespace(user_id="test-user")),
            raising=False,
        )

    def test_hide_unused_profile_items_requires_parent(self, monkeypatch, test_client):
        self._mock_request_user(monkeypatch)
        resp = test_client.post("/api/profiles/hide-unused-profile-items", json={})
        assert resp.status_code == 200
        assert resp.json["code"] != 0

    def test_hide_unused_profile_items_ok(self, monkeypatch, test_client):
        called = {}

        def fake_hide(_app_ctx, parent_id, user_id):
            called["parent_id"] = parent_id
            called["user_id"] = user_id
            return [
                {
                    "profile_key": "k1",
                    "profile_scope": "user",
                    "profile_type": "text",
                    "profile_id": "pid",
                }
            ]

        monkeypatch.setattr(
            "flaskr.service.profile.routes.hide_unused_profile_items", fake_hide
        )
        self._mock_request_user(monkeypatch)

        resp = test_client.post(
            "/api/profiles/hide-unused-profile-items",
            json={"parent_id": "shifu_1"},
        )

        assert resp.status_code == 200
        assert resp.json["code"] == 0
        assert called["parent_id"] == "shifu_1"

    def test_update_profile_hidden_state_requires_parent(
        self, monkeypatch, test_client
    ):
        self._mock_request_user(monkeypatch)
        resp = test_client.post(
            "/api/profiles/update-profile-hidden-state",
            json={"profile_keys": ["k1"], "hidden": True},
        )
        assert resp.status_code == 200
        assert resp.json["code"] != 0

    def test_update_profile_hidden_state_ok(self, monkeypatch, test_client):
        called = {}

        def fake_update(_app_ctx, parent_id, profile_keys, hidden, user_id):
            called["parent_id"] = parent_id
            called["profile_keys"] = profile_keys
            called["hidden"] = hidden
            called["user_id"] = user_id
            return [
                {
                    "profile_key": "k1",
                    "profile_scope": "user",
                    "profile_type": "text",
                    "profile_id": "pid",
                    "is_hidden": int(hidden),
                }
            ]

        monkeypatch.setattr(
            "flaskr.service.profile.routes.update_profile_item_hidden_state",
            fake_update,
        )
        self._mock_request_user(monkeypatch)

        resp = test_client.post(
            "/api/profiles/update-profile-hidden-state",
            json={"parent_id": "shifu_1", "profile_keys": ["k1"], "hidden": True},
        )

        assert resp.status_code == 200
        assert resp.json["code"] == 0
        assert called["parent_id"] == "shifu_1"
        assert called["profile_keys"] == ["k1"]
        assert called["hidden"] is True

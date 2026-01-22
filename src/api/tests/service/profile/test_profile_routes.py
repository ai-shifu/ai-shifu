import pytest


@pytest.mark.usefixtures("app", "client")
class TestProfileRoutes:
    def test_hide_unused_profile_items_requires_parent(self, client):
        resp = client.post("/api/profiles/hide-unused-profile-items", json={})
        assert resp.status_code == 400

    def test_hide_unused_profile_items_ok(self, monkeypatch, client, app):
        called = {}

        def fake_hide(app_ctx, parent_id, user_id):
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

        with app.test_request_context():
            resp = client.post(
                "/api/profiles/hide-unused-profile-items",
                json={"parent_id": "shifu_1"},
            )

        assert resp.status_code == 200
        assert resp.json["code"] == 0
        assert called["parent_id"] == "shifu_1"

    def test_update_profile_hidden_state_requires_parent(self, client):
        resp = client.post(
            "/api/profiles/update-profile-hidden-state",
            json={"profile_keys": ["k1"], "hidden": True},
        )
        assert resp.status_code == 400

    def test_update_profile_hidden_state_ok(self, monkeypatch, client, app):
        called = {}

        def fake_update(app_ctx, parent_id, profile_keys, hidden, user_id):
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

        with app.test_request_context():
            resp = client.post(
                "/api/profiles/update-profile-hidden-state",
                json={"parent_id": "shifu_1", "profile_keys": ["k1"], "hidden": True},
            )

        assert resp.status_code == 200
        assert resp.json["code"] == 0
        assert called["parent_id"] == "shifu_1"
        assert called["profile_keys"] == ["k1"]
        assert called["hidden"] is True

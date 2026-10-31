"""Verify profile HTTP route behavior."""

from types import SimpleNamespace

import flaskr.service.config.funcs as config_funcs
import pytest

_dummy_lock = SimpleNamespace(
    acquire=lambda *_args, **_kwargs: False,
    release=lambda *_args, **_kwargs: None,
)


@pytest.fixture(autouse=True)
def _stub_profile_config_cache(monkeypatch: object) -> None:
    monkeypatch.setattr(
        config_funcs,
        "redis",
        SimpleNamespace(
            get=lambda _key: None,
            set=lambda *_args, **_kwargs: None,
            lock=lambda *_args, **_kwargs: _dummy_lock,
        ),
    )


@pytest.mark.usefixtures("app")
class TestProfileRoutes:
    """Verify profile routes behavior."""

    def _mock_request_user(self, monkeypatch: object) -> None:
        dummy_user = SimpleNamespace(user_id="test-user", language="en-US")
        monkeypatch.setattr(
            "flaskr.route.user.validate_user",
            lambda _app, _token: dummy_user,
            raising=False,
        )

    def test_unimplemented_profile_item_route_is_not_registered(
        self, app: object, monkeypatch: object, test_client: object
    ) -> None:
        self._mock_request_user(monkeypatch)
        path = "/api/profiles/get-profile-item"

        assert path not in {rule.rule for rule in app.url_map.iter_rules()}
        response = test_client.post(path, json={"profile_id": "profile_1"})
        payload = response.get_json(silent=True) or {}
        assert payload.get("code") == 404

    @pytest.mark.parametrize(
        ("suffix", "request_payload"),
        [
            (
                "add-profile-item-quick",
                {"parent_id": "shifu_1", "profile_key": "goal"},
            ),
            (
                "save-profile-item",
                {
                    "parent_id": "shifu_1",
                    "profile_id": "profile_1",
                    "profile_key": "goal",
                    "profile_type": "text",
                },
            ),
            ("delete-profile-item", {"profile_id": "profile_1"}),
        ],
    )
    def test_manual_definition_write_routes_are_not_registered(
        self,
        app: object,
        monkeypatch: object,
        test_client: object,
        suffix: str,
        request_payload: dict[str, str],
    ) -> None:
        self._mock_request_user(monkeypatch)
        path = f"/api/profiles/{suffix}"

        assert path not in {rule.rule for rule in app.url_map.iter_rules()}
        response = test_client.post(path, json=request_payload)

        assert response.is_json
        assert response.get_json()["code"] == 404

    @pytest.mark.parametrize("query", ["", "&type=all", "&type=text", "&type=option"])
    def test_get_profile_item_definitions_has_no_type_filter(
        self, monkeypatch: object, test_client: object, query: str
    ) -> None:
        called = {}
        definition = {
            "profile_key": "What would you like to learn?",
            "profile_scope": "user",
            "profile_type": "text",
            "profile_type_str": "Text",
            "profile_id": "pid",
        }

        def fake_get_definitions(_app_ctx: object, parent_id: object) -> object:
            called["parent_id"] = parent_id
            return [definition]

        monkeypatch.setattr(
            "flaskr.service.profile.routes.get_profile_item_definition_list",
            fake_get_definitions,
        )
        self._mock_request_user(monkeypatch)

        resp = test_client.get(
            "/api/profiles/get-profile-item-definitions?parent_id=shifu_1" + query
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert called == {"parent_id": "shifu_1"}
        assert payload["data"] == [definition]

    def test_hide_unused_profile_items_requires_parent(
        self, monkeypatch: object, test_client: object
    ) -> None:
        self._mock_request_user(monkeypatch)
        resp = test_client.post("/api/profiles/hide-unused-profile-items", json={})
        payload = resp.get_json(force=True)
        assert resp.status_code == 200
        assert payload["code"] != 0

    def test_hide_unused_profile_items_ok(
        self, monkeypatch: object, test_client: object
    ) -> None:
        called = {}

        def fake_hide(_app_ctx: object, parent_id: object, user_id: object) -> object:
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
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert called["parent_id"] == "shifu_1"

    def test_update_profile_hidden_state_requires_parent(
        self, monkeypatch: object, test_client: object
    ) -> None:
        self._mock_request_user(monkeypatch)
        resp = test_client.post(
            "/api/profiles/update-profile-hidden-state",
            json={"profile_keys": ["k1"], "hidden": True},
        )
        payload = resp.get_json(force=True)
        assert resp.status_code == 200
        assert payload["code"] != 0

    def test_update_profile_hidden_state_ok(
        self, monkeypatch: object, test_client: object
    ) -> None:
        called = {}

        def fake_update(
            _app_ctx: object,
            parent_id: object,
            profile_keys: object,
            hidden: object,
            user_id: object,
        ) -> object:
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
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert called["parent_id"] == "shifu_1"
        assert called["profile_keys"] == ["k1"]
        assert called["hidden"] is True

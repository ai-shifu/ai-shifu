def test_profile_item(app):
    with app.app_context():
        from flaskr.service.profile.profile_manage import add_profile_item_quick

        add_profile_item_quick(app, "12333", "test22", "123")


def test_save_profile_item(test_client, app, token):
    json_data = {
        "profile_id": None,
        "parent_id": "b8e9efc6f62e4bed81b6dca5e5ce2385",
        "profile_key": "test22333",
        "profile_type": "text",
        "profile_remark": "test22",
    }
    response = test_client.post(
        "/api/profiles/save-profile-item",
        json=json_data,
        headers={
            "Token": token,
            "Content-Type": "application/json",
        },
    )
    app.logger.info(response.json)


def test_save_profile_item_option(test_client, app, token):
    json_data = {
        "profile_id": None,
        "parent_id": "b8e9efc6f62e4bed81b6dca5e5ce2385",
        "profile_key": "test2233",
        "profile_type": "option",
        "profile_remark": "test22343",
        "profile_items": [
            {
                "value": "test22",
                "name": "test22",
            }
        ],
    }
    response = test_client.post(
        "/api/profiles/save-profile-item",
        json=json_data,
        headers={
            "Token": token,
            "Content-Type": "application/json",
        },
    )
    app.logger.info(response.json)


def test_get_profile_list_api(test_client, app, token):
    response = test_client.get(
        "/api/profiles/get-profile-item-definitions?parent_id=b8e9efc6f62e4bed81b6dca5e5ce2385",
        headers={
            "Token": token,
            "Content-Type": "application/json",
        },
    )
    app.logger.info(response.data)


def test_get_profile_list(app):
    with app.app_context():
        from flaskr.service.profile.profile_manage import (
            get_profile_item_definition_list,
        )
        from flaskr.route.common import make_common_response

        profile_item_definition_list = get_profile_item_definition_list(
            app, "b8e9efc6f62e4bed81b6dca5e5ce2385"
        )
        app.logger.info(make_common_response(profile_item_definition_list))


def test_get_profile_item_defination_option_list(test_client, app, token):
    response = test_client.get(
        "/api/profiles/get-profile-item-definition-option-list?parent_id=b8e9efc6f62e4bed81b6dca5e5ce2385",
        headers={
            "Token": token,
            "Content-Type": "application/json",
        },
    )
    app.logger.info(response.data)


def test_delete_profile_item(test_client, app, token):
    import json

    response = test_client.get(
        "/api/profiles/get-profile-item-definitions?parent_id=b8e9efc6f62e4bed81b6dca5e5ce2385",
        headers={
            "Token": token,
            "Content-Type": "application/json",
        },
    )
    app.logger.info(response.data)
    profile_item_definition_list = json.loads(response.data).get("data")
    original_length = len(profile_item_definition_list)
    profile_id = profile_item_definition_list[0].get("profile_id")
    response = test_client.post(
        "/api/profiles/delete-profile-item",
        json={"profile_id": profile_id},
        headers={
            "Token": token,
            "Content-Type": "application/json",
        },
    )
    app.logger.info(response.data)

    response = test_client.get(
        "/api/profiles/get-profile-item-definitions?parent_id=b8e9efc6f62e4bed81b6dca5e5ce2385",
        headers={
            "Token": token,
            "Content-Type": "application/json",
        },
    )
    app.logger.info(response.data)
    profile_item_definition_list = json.loads(response.data).get("data")
    assert len(profile_item_definition_list) == original_length - 1


def test_hide_unused_profile_items_no_unused(monkeypatch):
    from flask import Flask
    from flaskr.service.profile import profile_manage

    calls = []

    def fake_get_unused(app, parent_id):
        calls.append(("unused", parent_id))
        return []

    def fake_get_defs(app, parent_id=None):
        calls.append(("defs", parent_id))
        return ["defs"]

    monkeypatch.setattr(
        profile_manage, "get_unused_profile_keys", fake_get_unused, raising=True
    )
    monkeypatch.setattr(
        profile_manage,
        "get_profile_item_definition_list",
        fake_get_defs,
        raising=True,
    )

    app = Flask(__name__)
    result = profile_manage.hide_unused_profile_items(app, "shifu_bid", "user_bid")

    assert result == ["defs"]
    assert ("unused", "shifu_bid") in calls
    assert ("defs", "shifu_bid") in calls


def test_hide_unused_profile_items_updates_hidden(monkeypatch):
    from flask import Flask
    from flaskr.service.profile import profile_manage

    calls = []

    def fake_get_unused(app, parent_id):
        calls.append(("unused", parent_id))
        return ["v1", "v2"]

    def fake_update(app, parent_id, profile_keys, hidden, user_id):
        calls.append(("update", parent_id, tuple(profile_keys), hidden, user_id))
        return ["updated"]

    monkeypatch.setattr(
        profile_manage, "get_unused_profile_keys", fake_get_unused, raising=True
    )
    monkeypatch.setattr(
        profile_manage,
        "update_profile_item_hidden_state",
        fake_update,
        raising=True,
    )

    app = Flask(__name__)
    result = profile_manage.hide_unused_profile_items(app, "shifu_bid", "user_bid")

    assert result == ["updated"]
    assert ("unused", "shifu_bid") in calls
    assert ("update", "shifu_bid", ("v1", "v2"), True, "user_bid") in calls

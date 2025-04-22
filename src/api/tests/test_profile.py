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
            "X-API-MODE": "admin",
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
            "X-API-MODE": "admin",
        },
    )
    app.logger.info(response.json)


def test_get_profile_list_api(test_client, app, token):
    response = test_client.get(
        "/api/profiles/get-profile-item-definitions?parent_id=b8e9efc6f62e4bed81b6dca5e5ce2385",
        headers={
            "Token": token,
            "Content-Type": "application/json",
            "X-API-MODE": "admin",
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
            "X-API-MODE": "admin",
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
            "X-API-MODE": "admin",
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
            "X-API-MODE": "admin",
        },
    )
    app.logger.info(response.data)

    response = test_client.get(
        "/api/profiles/get-profile-item-definitions?parent_id=b8e9efc6f62e4bed81b6dca5e5ce2385",
        headers={
            "Token": token,
            "Content-Type": "application/json",
            "X-API-MODE": "admin",
        },
    )
    app.logger.info(response.data)
    profile_item_definition_list = json.loads(response.data).get("data")
    assert len(profile_item_definition_list) == original_length - 1

def test_profile_item(app):
    with app.app_context():
        from flaskr.service.profile.profile_manage import add_profile_item_quick

        add_profile_item_quick(app, "12333", "test22", "123")


def test_save_profile_item(test_client, app, token):
    token = ""
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


def test_get_profile_list(test_client, app, token):
    response = test_client.get(
        "/api/profiles/get-profile-item-definations?parent_id=b8e9efc6f62e4bed81b6dca5e5ce2385",
        headers={
            "Token": token,
            "Content-Type": "application/json",
            "X-API-MODE": "admin",
        },
    )
    app.logger.info(response.json)


def test_get_profile_item_defination_option_list(test_client, app, token):
    response = test_client.get(
        "/api/profiles/get-profile-item-defination-option-list?parent_id=b8e9efc6f62e4bed81b6dca5e5ce2385",
        headers={
            "Token": token,
            "Content-Type": "application/json",
            "X-API-MODE": "admin",
        },
    )
    app.logger.info(response.json)

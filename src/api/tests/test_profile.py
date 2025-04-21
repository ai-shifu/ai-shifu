def test_profile_item(app):
    with app.app_context():
        from flaskr.service.profile.profile_manage import add_profile_item_quick

        add_profile_item_quick(app, "12333", "test22", "123")


def test_get_profile_item_defination_list(app):
    with app.app_context():
        from flaskr.service.profile.profile_manage import (
            get_profile_item_defination_list,
        )
        from flaskr.route.common import make_common_response

        data = get_profile_item_defination_list(app, "b8e9efc6f62e4bed81b6dca5e5ce2385")
        app.logger.info(make_common_response(data))

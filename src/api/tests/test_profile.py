from flaskr.service.profile.profile_manage import (
    add_profile_item_quick,
    get_profile_item_definition_list,
)


def test_add_profile_item_quick_creates_definition(app):
    with app.app_context():
        definition = add_profile_item_quick(
            app,
            parent_id="course-1",
            key="favorite_color",
            user_id="user-1",
        )
        assert definition.profile_key == "favorite_color"

        definitions = get_profile_item_definition_list(app, "course-1")
        assert any(item.profile_key == "favorite_color" for item in definitions)

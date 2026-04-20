import flaskr.service.profile.profile_manage as profile_manage
from flaskr.service.profile.profile_manage import (
    add_profile_item_quick,
    get_profile_item_definition_list,
    hide_unused_profile_items,
    get_profile_variable_usage,
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


def test_hide_unused_profile_items_no_unused(monkeypatch):
    calls = []

    def fake_get_unused(_app, parent_id):
        calls.append(("unused", parent_id))
        return []

    def fake_get_defs(_app, parent_id=None):
        calls.append(("defs", parent_id))
        return ["defs"]

    monkeypatch.setattr(profile_manage, "get_unused_profile_keys", fake_get_unused)
    monkeypatch.setattr(
        profile_manage, "get_profile_item_definition_list", fake_get_defs
    )

    result = hide_unused_profile_items(
        app=None, parent_id="shifu_bid", user_id="user_bid"
    )

    assert result == ["defs"]
    assert ("unused", "shifu_bid") in calls
    assert ("defs", "shifu_bid") in calls


def test_hide_unused_profile_items_updates_hidden(monkeypatch):
    calls = []

    def fake_get_unused(_app, parent_id):
        calls.append(("unused", parent_id))
        return ["v1", "v2"]

    def fake_update(_app, parent_id, profile_keys, hidden, user_id):
        calls.append(("update", parent_id, tuple(profile_keys), hidden, user_id))
        return ["updated"]

    monkeypatch.setattr(profile_manage, "get_unused_profile_keys", fake_get_unused)
    monkeypatch.setattr(profile_manage, "update_profile_item_hidden_state", fake_update)

    result = hide_unused_profile_items(
        app=None, parent_id="shifu_bid", user_id="user_bid"
    )

    assert result == ["updated"]
    assert ("unused", "shifu_bid") in calls
    assert ("update", "shifu_bid", ("v1", "v2"), True, "user_bid") in calls


def test_get_profile_variable_usage_groups_keys(monkeypatch):
    calls = []

    def fake_get_defs(_app, parent_id=None, _type="all"):
        calls.append(("defs", parent_id))
        return [
            # system key should be ignored
            object.__class__(
                "obj", (), {"profile_scope": "system", "profile_key": "sys1"}
            ),
            object.__class__("obj", (), {"profile_scope": "user", "profile_key": "k1"}),
            object.__class__("obj", (), {"profile_scope": "user", "profile_key": "k2"}),
        ]

    def fake_collect(_app, parent_id):
        calls.append(("collect", parent_id))
        return {"k2"}

    monkeypatch.setattr(
        profile_manage, "get_profile_item_definition_list", fake_get_defs
    )
    monkeypatch.setattr(profile_manage, "_collect_used_variables", fake_collect)

    result = get_profile_variable_usage(app=None, parent_id="shifu_bid")

    assert result == {"used_keys": ["k2"], "unused_keys": ["k1"]}
    assert ("defs", "shifu_bid") in calls
    assert ("collect", "shifu_bid") in calls

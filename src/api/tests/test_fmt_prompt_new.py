def test_fmt_prompt_replaces_double_braces(app, monkeypatch):
    from flaskr.service.learn import utils_v2

    monkeypatch.setattr(
        utils_v2,
        "get_user_profiles",
        lambda _app, _user_id, _course_id: {"nickname": "Alice"},
    )

    with app.app_context():
        prompt = "Hello, {{nickname}}!"
        fmt_prompt = utils_v2.get_fmt_prompt(app, "user-1", "course-1", prompt)
        assert fmt_prompt == "Hello, Alice!"


def test_fmt_prompt_ignores_invalid_variable_names(app, monkeypatch):
    from flaskr.service.learn import utils_v2

    monkeypatch.setattr(
        utils_v2,
        "get_user_profiles",
        lambda _app, _user_id, _course_id: {"user_name": "Alice"},
    )

    with app.app_context():
        prompt = "Hello, {user.name}!"
        fmt_prompt = utils_v2.get_fmt_prompt(app, "user-1", "course-1", prompt)
        assert fmt_prompt == "Hello, {user.name}!"

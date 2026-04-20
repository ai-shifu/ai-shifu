def test_fmt_prompt_replaces_known_variables(app, monkeypatch):
    from flaskr.service.learn import utils_v2

    monkeypatch.setattr(
        utils_v2,
        "get_user_profiles",
        lambda _app, _user_id, _course_id: {"nickname": "Alice"},
    )

    with app.app_context():
        prompt = "Hello, {nickname}!"
        fmt_prompt = utils_v2.get_fmt_prompt(app, "user-1", "course-1", prompt)
        assert fmt_prompt == "Hello, Alice!"


def test_fmt_prompt_keeps_unknown_variables(app, monkeypatch):
    from flaskr.service.learn import utils_v2

    monkeypatch.setattr(
        utils_v2,
        "get_user_profiles",
        lambda _app, _user_id, _course_id: {"nickname": "Alice"},
    )

    with app.app_context():
        prompt = "Hello, {unknown}!"
        fmt_prompt = utils_v2.get_fmt_prompt(app, "user-1", "course-1", prompt)
        assert fmt_prompt == "Hello, {unknown}!"


def test_fmt_prompt_uses_input_when_template_empty(app, monkeypatch):
    from flaskr.service.learn import utils_v2

    monkeypatch.setattr(
        utils_v2,
        "get_user_profiles",
        lambda _app, _user_id, _course_id: {},
    )

    with app.app_context():
        fmt_prompt = utils_v2.get_fmt_prompt(
            app, "user-1", "course-1", "", input="fallback-input"
        )
        assert fmt_prompt == "fallback-input"

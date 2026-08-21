"""Verify prompt variables resolve without mutating learner profiles."""


def test_fmt_prompt_replaces_known_variables(app, monkeypatch) -> None:
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


def test_fmt_prompt_keeps_unknown_variables(app, monkeypatch) -> None:
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


def test_fmt_prompt_uses_input_when_template_empty(app, monkeypatch) -> None:
    from flaskr.service.learn import utils_v2

    monkeypatch.setattr(
        utils_v2,
        "get_user_profiles",
        lambda _app, _user_id, _course_id: {},
    )

    with app.app_context():
        fmt_prompt = utils_v2.get_fmt_prompt(
            app, "user-1", "course-1", "", user_input="fallback-input"
        )
        assert fmt_prompt == "fallback-input"


def test_fmt_prompt_prefers_request_overrides_without_mutating_profiles(
    app, monkeypatch
) -> None:
    from flaskr.service.learn import utils_v2

    stored_profiles = {
        "nickname": "Alice",
        "language": "zh-CN",
        "sys_user_language": "zh-CN",
    }
    monkeypatch.setattr(
        utils_v2,
        "get_user_profiles",
        lambda _app, _user_id, _course_id: stored_profiles,
    )

    with app.app_context():
        fmt_prompt = utils_v2.get_fmt_prompt(
            app,
            "user-1",
            "course-1",
            "Hello {nickname}; {language}; {sys_user_language}",
            profile_overrides={
                "language": "fr-FR",
                "sys_user_language": "fr-FR",
            },
        )

    assert fmt_prompt == "Hello Alice; fr-FR; fr-FR"
    assert stored_profiles == {
        "nickname": "Alice",
        "language": "zh-CN",
        "sys_user_language": "zh-CN",
    }

def test_check_text_returns_unconfigured_for_yidun(app):
    from flaskr.api.check import check_text, CHECK_RESULT_UNCONF

    with app.app_context():
        app.config["CHECK_PROVIDER"] = "yidun"
        result = check_text(app, "data-id", "hello", "user-1")
        assert result.check_result == CHECK_RESULT_UNCONF
        assert result.provider == "yidun"

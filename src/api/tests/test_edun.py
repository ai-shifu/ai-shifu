def test_check_text_returns_unconfigured_for_yidun(app):
    from flaskr.api.check import check_text, CHECK_RESULT_UNCONF

    with app.app_context():
        app.config["CHECK_PROVIDER"] = "yidun"
        result = check_text(app, "data-id", "hello", "user-1")
        assert result.check_result == CHECK_RESULT_UNCONF
        assert result.provider == "yidun"


def test_yidun_check_uses_configured_timeout(app, monkeypatch):
    from flaskr.api.check import CHECK_RESULT_PASS, yidun as yidun_module

    captured = {}

    class _Resp:
        def json(self):
            return {"code": 200, "result": {"antispam": {"suggestion": 0, "label": 100}}}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(yidun_module, "YIDUN_SECRET_ID", "sid")
    monkeypatch.setattr(yidun_module, "YIDUN_SECRET_KEY", "skey")
    monkeypatch.setattr(yidun_module, "YIDUN_BUSINESS_ID", "bid")
    monkeypatch.setitem(app.config, "NETEASE_YIDUN_TIMEOUT_SECONDS", 3.5)
    monkeypatch.setattr(yidun_module.requests, "post", fake_post)

    result = yidun_module.yidun_check(app, "data-id", "hello", "user-1")

    assert result.check_result == CHECK_RESULT_PASS
    assert result.provider == "yidun"
    assert captured["url"] == yidun_module.URL
    assert captured["timeout"] == 3.5


def test_ilivedata_check_uses_configured_timeout(app, monkeypatch):
    from flaskr.api.check import CHECK_RESULT_PASS, ilivedata as ilivedata_module

    captured = {}

    class _Resp:
        def read(self):
            return b'{"errorCode":0,"textSpam":{"result":0,"tags":[]}}'

    def fake_urlopen(req, timeout=None):
        captured["host"] = req.full_url
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setitem(app.config, "ILIVEDATA_PID", "pid")
    monkeypatch.setitem(app.config, "ILIVEDATA_SECRET_KEY", "secret")
    monkeypatch.setitem(app.config, "ILIVEDATA_TIMEOUT_SECONDS", 4.0)
    monkeypatch.setattr(ilivedata_module, "urlopen", fake_urlopen)

    result = ilivedata_module.ilivedata_check(app, "data-id", "hello", "user-1")

    assert result.check_result == CHECK_RESULT_PASS
    assert result.provider == "ilivedata"
    assert captured["host"] == ilivedata_module.endpoint_url
    assert captured["timeout"] == 4.0

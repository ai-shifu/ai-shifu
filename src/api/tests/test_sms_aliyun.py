from types import SimpleNamespace

from flask import Flask

from flaskr.api.sms import aliyun


def test_query_sms_template_list_caps_page_size_at_provider_limit(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, _config):
            pass

        def query_sms_template_list_with_options(self, request, _runtime):
            captured["page_index"] = request.page_index
            captured["page_size"] = request.page_size
            return SimpleNamespace(body=SimpleNamespace(code="OK"))

    monkeypatch.setattr(aliyun, "Dysmsapi20170525Client", FakeClient)

    app = Flask(__name__)
    app.config["ALIBABA_CLOUD_SMS_ACCESS_KEY_ID"] = "ak"
    app.config["ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET"] = "sk"

    aliyun.query_sms_template_list_ali(app, page_index=0, page_size=100)

    assert captured == {"page_index": 1, "page_size": 50}

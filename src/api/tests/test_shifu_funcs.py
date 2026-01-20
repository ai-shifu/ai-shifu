from flaskr.service.shifu import shifu_publish_funcs


def test_run_summary_with_error_handling_logs_and_continues(app, monkeypatch):
    called = {"apply": False, "summary": False}

    def fake_apply(_snapshot):
        called["apply"] = True

    def fake_summary(_app, _shifu_id):
        called["summary"] = True
        raise RuntimeError("boom")

    monkeypatch.setattr(shifu_publish_funcs, "apply_shifu_context_snapshot", fake_apply)
    monkeypatch.setattr(shifu_publish_funcs, "get_shifu_summary", fake_summary)

    # Should not raise even if summary generation fails
    shifu_publish_funcs._run_summary_with_error_handling(app, "shifu-1")

    assert called["apply"] is True
    assert called["summary"] is True

from types import SimpleNamespace

from flaskr.service.shifu import shifu_outline_funcs, shifu_publish_funcs


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


def test_build_outline_tree_warns_once_for_orphan_nodes(app, monkeypatch, caplog):
    items = [
        SimpleNamespace(outline_item_bid="root", position="01"),
        SimpleNamespace(outline_item_bid="child", position="0101"),
        SimpleNamespace(outline_item_bid="orphan", position="0702"),
        SimpleNamespace(outline_item_bid="orphan2", position="0703"),
    ]

    monkeypatch.setattr(
        shifu_outline_funcs, "__get_existing_outline_items", lambda _: items
    )

    tree = shifu_outline_funcs.build_outline_tree(app, "shifu-1")

    assert [node.position for node in tree] == ["01"]
    assert [node.position for node in tree[0].children] == ["0101"]
    assert "Skipped 2 orphan outline nodes without parent" in caplog.text
    assert "Parent node not found" not in caplog.text

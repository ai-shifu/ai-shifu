"""Verify study records remain empty before learner progress."""

from flaskr.service.learn.learn_funcs import get_learn_record


def test_get_learn_record_empty_when_no_progress(app):
    record = get_learn_record(
        app, "shifu-empty", "outline-empty", "user-empty", preview_mode=False
    )
    assert record.records == []

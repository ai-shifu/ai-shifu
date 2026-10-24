"""Unit-of-work behavior for the B4 learn call sites (lesson feedback race)."""

from __future__ import annotations

import uuid

from flaskr import dao
from flaskr.service.learn import lesson_feedback
from flaskr.service.learn.models import LearnLessonFeedback


def test_lesson_feedback_reapplies_after_losing_the_insert_race(
    app: object, monkeypatch: object
) -> None:
    user_bid = uuid.uuid4().hex[:32]
    shifu_bid = uuid.uuid4().hex[:32]
    outline_bid = uuid.uuid4().hex[:32]
    monkeypatch.setattr(
        lesson_feedback, "_resolve_progress_record_bid", lambda *_a: "progress-1"
    )
    monkeypatch.setattr(
        lesson_feedback, "_sync_feedback_to_generated_block", lambda *_a: None
    )
    original_add = dao.db.session.add
    state = {"raced": False}

    def racing_add(instance: object) -> None:
        # A concurrent submission wins the unique active row before our commit.
        if isinstance(instance, LearnLessonFeedback) and not state["raced"]:
            state["raced"] = True
            with dao.db.engine.begin() as connection:
                connection.execute(
                    LearnLessonFeedback.__table__.insert().values(
                        bid="winner-bid",
                        lesson_feedback_bid="winner-bid",
                        shifu_bid=shifu_bid,
                        outline_item_bid=outline_bid,
                        progress_record_bid="progress-1",
                        user_bid=user_bid,
                        score=1,
                        comment="winner",
                        mode="",
                        deleted=0,
                    )
                )
        original_add(instance)

    with app.app_context():
        monkeypatch.setattr(dao.db.session, "add", racing_add)
        result = lesson_feedback.submit_lesson_feedback(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            score=5,
            comment="mine",
            mode=None,
        )
        monkeypatch.undo()
        dao.db.session.expire_all()
        rows = LearnLessonFeedback.query.filter_by(
            user_bid=user_bid, shifu_bid=shifu_bid, outline_item_bid=outline_bid
        ).all()

    assert state["raced"] is True
    assert result["lesson_feedback_bid"] == "winner-bid"
    assert [(row.lesson_feedback_bid, row.score, row.comment) for row in rows] == [
        ("winner-bid", 5, "mine")
    ]

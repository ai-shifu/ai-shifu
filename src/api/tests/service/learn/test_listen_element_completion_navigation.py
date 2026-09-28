"""Keep completed 2.0 lessons navigable when their persisted elements lack a tail control."""

from __future__ import annotations

import uuid

import pytest
from flaskr.dao import db
from flaskr.service.learn import listen_element_history as history
from flaskr.service.learn.learn_dtos import (
    BlockType,
    ElementDTO,
    ElementType,
    LearnElementRecordDTO,
    LikeStatus,
)
from flaskr.service.learn.legacy_record_builder import (
    LegacyGeneratedBlockRecord,
    LegacyLearnRecord,
)
from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.order.consts import LEARN_STATUS_COMPLETED, LEARN_STATUS_IN_PROGRESS


def _element(
    content: str, *, interaction: bool = False, block_bid: str = ""
) -> ElementDTO:
    return ElementDTO(
        element_bid=uuid.uuid4().hex,
        element_index=0,
        role="ui" if interaction else "teacher",
        element_type=ElementType.INTERACTION if interaction else ElementType.TEXT,
        element_type_code=105 if interaction else 112,
        content=content,
        generated_block_bid=block_bid,
    )


@pytest.mark.parametrize("already_persisted", [False, True])
@pytest.mark.parametrize("has_successor", [False, True])
def test_completed_element_history_has_one_next_lesson_control(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    already_persisted: bool,
    has_successor: bool,
) -> None:
    """Only a current successor permits one control, including for older completions."""
    user_bid = uuid.uuid4().hex
    shifu_bid = uuid.uuid4().hex
    outline_bid = uuid.uuid4().hex
    progress_bid = uuid.uuid4().hex
    navigation_bid = uuid.uuid4().hex
    button = "?[Next lesson//_sys_next_chapter]"
    content = _element("Last lesson paragraph")
    persisted = [
        content,
        *(
            [_element(button, interaction=True, block_bid=navigation_bid)]
            if already_persisted
            else []
        ),
    ]
    fallback_calls: list[str | None] = []

    def _fallback(selected_bid: str | None) -> LegacyLearnRecord:
        fallback_calls.append(selected_bid)
        return LegacyLearnRecord(
            records=[
                LegacyGeneratedBlockRecord(
                    generated_block_bid=navigation_bid,
                    content=button,
                    like_status=LikeStatus.NONE,
                    block_type=BlockType.INTERACTION,
                    user_input="",
                )
            ]
            if has_successor
            else []
        )

    monkeypatch.setattr(history, "_query_element_rows", lambda **_k: ([], {}, {}))
    monkeypatch.setattr(
        history, "_merge_progress_elements", lambda **_k: (persisted, None)
    )
    with app.app_context():
        db.session.add(
            LearnProgressRecord(
                progress_record_bid=progress_bid,
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
                user_bid=user_bid,
                status=LEARN_STATUS_COMPLETED,
                block_position=0,
            )
        )
        db.session.commit()
        try:
            result = history.get_listen_element_record(
                app=app,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                user_bid=user_bid,
                build_record_from_legacy=lambda _record: LearnElementRecordDTO(
                    elements=[_element(button, interaction=True)]
                ),
                load_fallback_record=_fallback,
            )
            assert sum(
                "_sys_next_chapter" in e.content for e in result.elements
            ) == int(has_successor)
            assert fallback_calls == [progress_bid]
        finally:
            LearnProgressRecord.query.filter_by(user_bid=user_bid).delete()
            db.session.commit()


def test_incomplete_latest_attempt_does_not_inherit_previous_navigation(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A completed older attempt cannot advance a newer attempt still in progress."""
    user_bid = uuid.uuid4().hex
    shifu_bid = uuid.uuid4().hex
    outline_bid = uuid.uuid4().hex
    old_bid = uuid.uuid4().hex
    latest_bid = uuid.uuid4().hex
    button = "?[Next lesson//_sys_next_chapter]"
    monkeypatch.setattr(history, "_query_element_rows", lambda **_k: ([], {}, {}))
    monkeypatch.setattr(
        history,
        "_merge_progress_elements",
        lambda **_k: (
            [_element("New attempt"), _element(button, interaction=True)],
            None,
        ),
    )
    with app.app_context():
        db.session.add_all(
            [
                LearnProgressRecord(
                    progress_record_bid=old_bid,
                    shifu_bid=shifu_bid,
                    outline_item_bid=outline_bid,
                    user_bid=user_bid,
                    status=LEARN_STATUS_COMPLETED,
                    block_position=0,
                ),
                LearnProgressRecord(
                    progress_record_bid=latest_bid,
                    shifu_bid=shifu_bid,
                    outline_item_bid=outline_bid,
                    user_bid=user_bid,
                    status=LEARN_STATUS_IN_PROGRESS,
                    block_position=1,
                ),
            ]
        )
        db.session.commit()
        try:
            result = history.get_listen_element_record(
                app=app,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                user_bid=user_bid,
                build_record_from_legacy=lambda _record: LearnElementRecordDTO(),
                load_fallback_record=lambda _bid: pytest.fail(
                    "An incomplete attempt must not load navigation"
                ),
            )
            assert [element.content for element in result.elements] == ["New attempt"]
        finally:
            LearnProgressRecord.query.filter_by(user_bid=user_bid).delete()
            db.session.commit()

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
from flaskr.service.order.consts import LEARN_STATUS_COMPLETED


def _element(content: str, *, interaction: bool = False) -> ElementDTO:
    return ElementDTO(
        element_bid=uuid.uuid4().hex,
        element_index=0,
        role="ui" if interaction else "teacher",
        element_type=ElementType.INTERACTION if interaction else ElementType.TEXT,
        element_type_code=105 if interaction else 112,
        content=content,
    )


@pytest.mark.parametrize("already_persisted", [False, True])
def test_completed_element_history_has_one_next_lesson_control(
    app: object, monkeypatch: pytest.MonkeyPatch, already_persisted: bool
) -> None:
    """Older completions recover the control; new ones keep their persisted copy."""
    user_bid = uuid.uuid4().hex
    shifu_bid = uuid.uuid4().hex
    outline_bid = uuid.uuid4().hex
    button = "?[Next lesson//_sys_next_chapter]"
    content = _element("Last lesson paragraph")
    persisted = [
        content,
        *([_element(button, interaction=True)] if already_persisted else []),
    ]
    fallback_calls: list[bool] = []

    def _fallback() -> LegacyLearnRecord:
        fallback_calls.append(True)
        return LegacyLearnRecord(
            records=[
                LegacyGeneratedBlockRecord(
                    generated_block_bid=uuid.uuid4().hex,
                    content=button,
                    like_status=LikeStatus.NONE,
                    block_type=BlockType.INTERACTION,
                    user_input="",
                )
            ]
        )

    monkeypatch.setattr(history, "_query_element_rows", lambda **_k: ([], {}, {}))
    monkeypatch.setattr(
        history, "_merge_progress_elements", lambda **_k: (persisted, None)
    )
    with app.app_context():
        db.session.add(
            LearnProgressRecord(
                progress_record_bid=uuid.uuid4().hex,
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
            assert sum("_sys_next_chapter" in e.content for e in result.elements) == 1
            assert len(fallback_calls) == (0 if already_persisted else 1)
        finally:
            LearnProgressRecord.query.filter_by(user_bid=user_bid).delete()
            db.session.commit()

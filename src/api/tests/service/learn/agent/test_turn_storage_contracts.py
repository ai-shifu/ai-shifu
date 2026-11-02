"""Keep committed turn anchors durable and retire only abandoned empty blocks."""

import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import in_unit_of_work, unit_of_work
from flaskr.service.learn.agent import lesson_record, run_agent
from flaskr.service.learn.elements.run_adapter import ListenElementRunAdapter
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    LearnStatus,
    OutlineItemUpdateDTO,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_LOCKED,
    LEARN_STATUS_NOT_STARTED,
)
from flaskr.service.shifu.models import LogPublishedStruct, PublishedOutlineItem
from flaskr.service.shifu.shifu_history_manager import HistoryItem

from tests.common.fixtures.model_factories import make_progress_record


@pytest.fixture
def identity(app: object) -> object:
    key = uuid.uuid4().hex
    yield SimpleNamespace(app=app, user=key, course=key, lesson=key)
    with app.app_context(), unit_of_work():
        LearnGeneratedElement.query.filter_by(user_bid=key).delete()
        LearnGeneratedBlock.query.filter_by(user_bid=key).delete()
        LearnProgressRecord.query.filter_by(user_bid=key).delete()
        LogPublishedStruct.query.filter_by(shifu_bid=key).delete()
        PublishedOutlineItem.query.filter_by(shifu_bid=key).delete()


@pytest.fixture
def published_lesson(identity: object) -> int:
    with identity.app.app_context(), unit_of_work():
        lesson = PublishedOutlineItem(
            shifu_bid=identity.course,
            outline_item_bid=identity.lesson,
            title="The published lesson",
        )
        db.session.add(lesson)
        db.session.flush()
        lesson_id = lesson.id
        structure = HistoryItem(
            bid=identity.course,
            id=0,
            type="shifu",
            children=[HistoryItem(bid=identity.lesson, id=lesson_id, type="outline")],
        )
        db.session.add(
            LogPublishedStruct(
                struct_bid=uuid.uuid4().hex,
                shifu_bid=identity.course,
                struct=structure.to_json(),
            )
        )
    return lesson_id


def _open_result(
    identity: object, block: str
) -> tuple[str, OutlineItemUpdateDTO | None]:
    return run_agent._open_turn(
        identity.app,
        user_bid=identity.user,
        shifu_bid=identity.course,
        outline_bid=identity.lesson,
        generated_block_bid=block,
        position=3,
    )


def _open(identity: object, block: str) -> str:
    progress, _update = _open_result(identity, block)
    return progress


@pytest.mark.usefixtures("published_lesson")
def test_first_open_returns_directory_update_after_progress_and_block_commit(
    identity: object,
) -> None:
    block_bid = uuid.uuid4().hex
    progress, update = _open_result(identity, block_bid)

    assert not in_unit_of_work()
    assert update is not None
    assert update.__json__() == {
        "outline_bid": identity.lesson,
        "title": "The published lesson",
        "status": LearnStatus.IN_PROGRESS.value,
        "has_children": False,
    }
    # A fresh app context must find the rows, rather than only uncommitted session state.
    with identity.app.app_context():
        record = LearnProgressRecord.query.filter_by(progress_record_bid=progress).one()
        block = LearnGeneratedBlock.query.filter_by(generated_block_bid=block_bid).one()
        assert record.status == LEARN_STATUS_IN_PROGRESS
        assert block.progress_record_bid == progress

    repeated_progress, repeated_update = _open_result(identity, uuid.uuid4().hex)
    assert repeated_progress == progress
    assert repeated_update is None


def test_start_update_uses_the_published_structure_revision_title(
    identity: object, published_lesson: int
) -> None:
    with identity.app.app_context(), unit_of_work():
        newer = PublishedOutlineItem(
            shifu_bid=identity.course,
            outline_item_bid=identity.lesson,
            title="A newer row outside the published structure",
        )
        db.session.add(newer)
        db.session.flush()
        assert newer.id > published_lesson

    _progress, update = _open_result(identity, uuid.uuid4().hex)

    assert update is not None
    assert update.title == "The published lesson"


@pytest.mark.parametrize(
    ("initial_status", "expected_status", "notifies"),
    [
        (LEARN_STATUS_NOT_STARTED, LEARN_STATUS_IN_PROGRESS, True),
        (LEARN_STATUS_LOCKED, LEARN_STATUS_IN_PROGRESS, True),
        (LEARN_STATUS_IN_PROGRESS, LEARN_STATUS_IN_PROGRESS, False),
        (LEARN_STATUS_COMPLETED, LEARN_STATUS_COMPLETED, False),
    ],
)
@pytest.mark.usefixtures("published_lesson")
def test_open_notifies_only_when_progress_starts_and_preserves_completion(
    identity: object,
    initial_status: int,
    expected_status: int,
    notifies: bool,
) -> None:
    progress_bid = uuid.uuid4().hex
    with identity.app.app_context(), unit_of_work():
        db.session.add(
            make_progress_record(
                progress_record_bid=progress_bid,
                user_bid=identity.user,
                shifu_bid=identity.course,
                outline_item_bid=identity.lesson,
                status=initial_status,
            )
        )

    progress, update = _open_result(identity, uuid.uuid4().hex)

    assert progress == progress_bid
    assert (update is not None) == notifies
    if update is not None:
        assert update.status == LearnStatus.IN_PROGRESS
    with identity.app.app_context():
        record = LearnProgressRecord.query.filter_by(
            progress_record_bid=progress_bid
        ).one()
        assert record.status == expected_status


@pytest.mark.parametrize("unavailable", ["structure", "hidden", "deleted"])
def test_missing_directory_metadata_does_not_prevent_opening_the_turn(
    identity: object, published_lesson: int, unavailable: str
) -> None:
    with identity.app.app_context(), unit_of_work():
        if unavailable == "structure":
            LogPublishedStruct.query.filter_by(shifu_bid=identity.course).delete()
        else:
            lesson = PublishedOutlineItem.query.filter_by(id=published_lesson).one()
            setattr(lesson, unavailable, 1)

    block_bid = uuid.uuid4().hex
    progress, update = _open_result(identity, block_bid)

    assert update is None
    with identity.app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(
                progress_record_bid=progress, status=LEARN_STATUS_IN_PROGRESS
            ).count()
            == 1
        )
        assert (
            LearnGeneratedBlock.query.filter_by(
                generated_block_bid=block_bid, progress_record_bid=progress
            ).count()
            == 1
        )


def test_open_turn_commits_block_and_reuses_progress_before_streaming(
    identity: object,
) -> None:
    first, second = uuid.uuid4().hex, uuid.uuid4().hex
    progress = _open(identity, first)
    assert _open(identity, second) == progress
    with identity.app.app_context():
        db.session.expire_all()
        records = LearnProgressRecord.query.filter_by(user_bid=identity.user).all()
        assert len(records) == 1
        assert records[0].status == LEARN_STATUS_IN_PROGRESS
        blocks = (
            LearnGeneratedBlock.query.filter_by(user_bid=identity.user)
            .order_by(LearnGeneratedBlock.id)
            .all()
        )
        assert [block.generated_block_bid for block in blocks] == [first, second]
        assert all(block.progress_record_bid == progress for block in blocks)
        assert all(
            block.position == 3 and block.generated_content == "" for block in blocks
        )


@pytest.mark.parametrize(
    "initial_status", [None, LEARN_STATUS_NOT_STARTED, LEARN_STATUS_LOCKED]
)
@pytest.mark.usefixtures("published_lesson")
def test_failure_staging_turn_rolls_back_progress_and_block_together(
    identity: object,
    monkeypatch: pytest.MonkeyPatch,
    initial_status: int | None,
) -> None:
    if initial_status is not None:
        with identity.app.app_context(), unit_of_work():
            db.session.add(
                make_progress_record(
                    progress_record_bid=uuid.uuid4().hex,
                    user_bid=identity.user,
                    shifu_bid=identity.course,
                    outline_item_bid=identity.lesson,
                    status=initial_status,
                )
            )
    stage = run_agent.stage_turn_block

    def fail_after_stage(**kwargs: object) -> None:
        stage(**kwargs)
        db.session.flush()
        message = "turn staging interrupted"
        raise RuntimeError(message)

    monkeypatch.setattr(run_agent, "stage_turn_block", fail_after_stage)
    with pytest.raises(RuntimeError, match="staging interrupted"):
        _open(identity, uuid.uuid4().hex)
    with identity.app.app_context():
        records = LearnProgressRecord.query.filter_by(user_bid=identity.user).all()
        if initial_status is None:
            assert records == []
        else:
            assert len(records) == 1
            assert records[0].status == initial_status
        assert LearnGeneratedBlock.query.filter_by(user_bid=identity.user).count() == 0


@pytest.mark.usefixtures("published_lesson")
def test_disconnect_after_start_update_retires_block_before_content_runs(
    identity: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_agent, "_load_or_start", Mock(return_value=(Mock(), False)))
    stream_turn = Mock()
    monkeypatch.setattr(run_agent, "_stream_turn", stream_turn)
    stream = run_agent.run_agent_lesson(
        identity.app,
        engine=object(),
        script="Lesson",
        user_bid=identity.user,
        shifu_bid=identity.course,
        outline_bid=identity.lesson,
    )
    adapter = ListenElementRunAdapter(
        identity.app,
        shifu_bid=identity.course,
        outline_bid=identity.lesson,
        user_bid=identity.user,
        persist_only_final=True,
    )
    adapted = iter(adapter.process(stream))

    with identity.app.app_context():
        event = next(adapted)
        # The stream owner commits the adapter's snapshot after receiving each event.
        with unit_of_work():
            db.session.flush()

    assert event.type == GeneratedType.OUTLINE_ITEM_UPDATE.value
    assert event.event_type == GeneratedType.OUTLINE_ITEM_UPDATE.value
    assert event.run_event_seq == 1
    assert event.generated_block_bid is None
    assert event.content.__json__() == {
        "outline_bid": identity.lesson,
        "title": "The published lesson",
        "status": LearnStatus.IN_PROGRESS.value,
        "has_children": False,
    }
    assert not in_unit_of_work()
    with identity.app.app_context():
        assert (
            LearnProgressRecord.query.filter_by(
                user_bid=identity.user, status=LEARN_STATUS_IN_PROGRESS
            ).count()
            == 1
        )
        assert (
            LearnGeneratedBlock.query.filter_by(
                user_bid=identity.user, deleted=0
            ).count()
            == 1
        )

    stream.close()
    adapted.close()

    stream_turn.assert_not_called()
    with identity.app.app_context():
        block = LearnGeneratedBlock.query.filter_by(user_bid=identity.user).one()
        assert block.deleted == 1
        assert block.status == 0
        record = LearnProgressRecord.query.filter_by(user_bid=identity.user).one()
        assert record.status == LEARN_STATUS_IN_PROGRESS
        assert record.deleted == 0


@pytest.mark.parametrize("content", ["", " \n", "completed turn text"])
def test_retirement_is_idempotent_and_preserves_completed_turns(
    identity: object,
    content: str,
) -> None:
    bid = uuid.uuid4().hex
    _open(identity, bid)
    with identity.app.app_context(), unit_of_work():
        lesson_record.record_turn_content(generated_block_bid=bid, content=content)
    for _ in range(2):
        run_agent._retire_block(identity.app, generated_block_bid=bid)
    with identity.app.app_context():
        db.session.expire_all()
        block = LearnGeneratedBlock.query.filter_by(generated_block_bid=bid).one()
        assert block.generated_content == content
        assert block.deleted == int(not content.strip())
        assert block.status == int(bool(content.strip()))
        assert (
            LearnProgressRecord.query.filter_by(user_bid=identity.user).one().deleted
            == 0
        )


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("failure", ["provider", "disconnect"])
def test_unfinished_agent_turn_retires_reserved_block_and_preview_writes_no_progress(
    identity: object,
    monkeypatch: pytest.MonkeyPatch,
    preview: bool,
    failure: str,
) -> None:
    monkeypatch.setattr(run_agent, "_load_or_start", Mock(return_value=(Mock(), False)))
    provider_error = RuntimeError("provider failed")

    def stream_turn(_app: object, **kwargs: object) -> object:
        yield RunMarkdownFlowDTO(
            outline_bid=identity.lesson,
            generated_block_bid=kwargs["generated_block_bid"],
            type=GeneratedType.CONTENT,
            content="Partial content",
        )
        raise provider_error

    monkeypatch.setattr(run_agent, "_stream_turn", stream_turn)
    stream = run_agent.run_agent_lesson(
        identity.app,
        engine=object(),
        script="Lesson",
        user_bid=identity.user,
        shifu_bid=identity.course,
        outline_bid=identity.lesson,
        preview_mode=preview,
    )
    event = next(stream)
    with identity.app.app_context():
        assert LearnGeneratedBlock.query.filter_by(
            user_bid=identity.user, deleted=0
        ).count() == int(not preview)
    if failure == "disconnect":
        stream.close()
    else:
        with pytest.raises(RuntimeError) as raised:
            next(stream)
        assert raised.value is provider_error
    with identity.app.app_context():
        db.session.expire_all()
        blocks = LearnGeneratedBlock.query.filter_by(user_bid=identity.user).all()
        if preview:
            assert blocks == []
            assert (
                LearnProgressRecord.query.filter_by(user_bid=identity.user).count() == 0
            )
        else:
            assert len(blocks) == 1
            assert blocks[0].generated_block_bid == event.generated_block_bid
            assert blocks[0].deleted == 1
            assert blocks[0].status == 0


def test_retirement_database_failure_does_not_replace_original_provider_error(
    identity: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = RuntimeError("provider interrupted")
    monkeypatch.setattr(run_agent, "_load_or_start", Mock(return_value=(Mock(), False)))
    monkeypatch.setattr(run_agent, "_stream_turn", Mock(side_effect=original))
    retire = Mock(side_effect=RuntimeError("cleanup database unavailable"))
    monkeypatch.setattr(run_agent, "retire_unused_block", retire)
    with pytest.raises(RuntimeError) as raised:
        list(
            run_agent.run_agent_lesson(
                identity.app,
                engine=object(),
                script="Lesson",
                user_bid=identity.user,
                shifu_bid=identity.course,
                outline_bid=identity.lesson,
            )
        )
    assert raised.value is original
    retire.assert_called_once()


def test_absent_progress_cannot_be_claimed_for_writing(identity: object) -> None:
    with identity.app.app_context():
        assert (
            lesson_record.claim_for_writing(
                user_bid=identity.user,
                shifu_bid=identity.course,
                outline_bid=identity.lesson,
                progress_record_bid="",
            )
            is None
        )

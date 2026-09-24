"""Keep committed turn anchors durable and retire only abandoned empty blocks."""

import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import lesson_record, run_agent
from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS


@pytest.fixture
def identity(app: object) -> object:
    key = uuid.uuid4().hex
    yield SimpleNamespace(app=app, user=key, course=key, lesson=key)
    with app.app_context(), unit_of_work():
        LearnGeneratedBlock.query.filter_by(user_bid=key).delete()
        LearnProgressRecord.query.filter_by(user_bid=key).delete()


def _open(identity: object, block: str) -> str:
    return run_agent._open_turn(
        identity.app,
        user_bid=identity.user,
        shifu_bid=identity.course,
        outline_bid=identity.lesson,
        generated_block_bid=block,
        position=3,
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


def test_failure_staging_turn_rolls_back_new_progress_and_block_together(
    identity: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        assert LearnProgressRecord.query.filter_by(user_bid=identity.user).count() == 0
        assert LearnGeneratedBlock.query.filter_by(user_bid=identity.user).count() == 0


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

"""Failure-path tests for the /run persistence recorder (B6 PR2).

The recorder replaces ~20 mid-flow ``db.session.flush()`` sites with per-step
``unit_of_work()`` boundaries. These tests pin the semantics that motivated
the change:

- a mid-step failure rolls the step back whole, so no dirty flushed rows can
  ride into a later commit (the flush-then-fail dirty-row class);
- a block-finalize failure leaves the streamed-but-unfinalized block state
  untouched (no durable half-block, no cursor advance);
- a simulated client disconnect mid-stream (producer-level rollback, see
  ``runscript_v2.run_script_inner``) discards the staged block while every
  previously completed step stays durable, so the resume path re-runs from
  the last finalized block.
"""

import pytest
from flask import Flask

import flaskr.dao as dao
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.learn.run.recorder import RunRecorder
from flaskr.service.order.consts import (
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_NOT_STARTED,
)

USER_BID = "user-recorder-0001"
SHIFU_BID = "shifu-recorder-0001"
OUTLINE_BID = "outline-recorder-0001"


@pytest.fixture
def recorder_app() -> Flask:
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _seed_attend(progress_record_bid: str = "progress-recorder-0001"):
    attend = LearnProgressRecord(
        progress_record_bid=progress_record_bid,
        shifu_bid=SHIFU_BID,
        outline_item_bid=OUTLINE_BID,
        user_bid=USER_BID,
        status=LEARN_STATUS_NOT_STARTED,
        block_position=3,
    )
    dao.db.session.add(attend)
    dao.db.session.commit()
    return attend


def _build_block(bid: str, position: int) -> LearnGeneratedBlock:
    return LearnGeneratedBlock(
        generated_block_bid=bid,
        progress_record_bid="progress-recorder-0001",
        user_bid=USER_BID,
        outline_item_bid=OUTLINE_BID,
        shifu_bid=SHIFU_BID,
        position=position,
        generated_content="",
        block_content_conf="mdflow",
        status=1,
    )


def _fail_next_flush(monkeypatch, exc: Exception) -> None:
    """Make the next explicit ``db.session.flush()`` raise ``exc``."""
    real_flush = dao.db.session.flush
    state = {"fired": False}

    def _boom(*args, **kwargs):
        if not state["fired"]:
            state["fired"] = True
            raise exc
        return real_flush(*args, **kwargs)

    monkeypatch.setattr(dao.db.session, "flush", _boom)


def test_failed_pointer_step_rolls_back_whole(recorder_app, monkeypatch):
    """Mid-step failure: the flip is neither durable nor left dirty in the
    session, so a later unrelated commit cannot persist it (dirty-row fix)."""
    attend = _seed_attend()
    recorder = RunRecorder(recorder_app)

    _fail_next_flush(monkeypatch, RuntimeError("boom mid step"))
    with pytest.raises(RuntimeError, match="boom mid step"):
        recorder.update_progress_pointer(
            attend, status=LEARN_STATUS_IN_PROGRESS, block_position=9
        )
    monkeypatch.undo()

    # Not durable.
    row = LearnProgressRecord.query.filter(
        LearnProgressRecord.progress_record_bid == "progress-recorder-0001"
    ).one()
    assert row.status == LEARN_STATUS_NOT_STARTED
    assert row.block_position == 3

    # Not dirty either: a later unrelated step commit must not resurrect it.
    other = _build_block("gb-unrelated-0001", 0)
    recorder.save_generated_block(other)
    row = LearnProgressRecord.query.filter(
        LearnProgressRecord.progress_record_bid == "progress-recorder-0001"
    ).one()
    assert row.status == LEARN_STATUS_NOT_STARTED
    assert row.block_position == 3


def test_failed_placeholder_batch_rolls_back_all_records(recorder_app, monkeypatch):
    """The placeholder batch is one step: on failure no partial rows remain."""
    recorder = RunRecorder(recorder_app)
    records = [
        LearnProgressRecord(
            progress_record_bid=f"progress-batch-{index}",
            shifu_bid=SHIFU_BID,
            outline_item_bid=OUTLINE_BID,
            user_bid=USER_BID,
            status=LEARN_STATUS_NOT_STARTED,
            block_position=0,
        )
        for index in range(2)
    ]

    _fail_next_flush(monkeypatch, RuntimeError("boom in batch"))
    with pytest.raises(RuntimeError, match="boom in batch"):
        recorder.save_new_progress_records(records)
    monkeypatch.undo()

    assert (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.progress_record_bid.like("progress-batch-%")
        ).count()
        == 0
    )


def test_failed_finalize_leaves_staged_block_state_uncorrupted(
    recorder_app, monkeypatch
):
    """Block-finalize failure: neither the staged block nor the cursor
    advance survives — the pre-stream state is fully restored."""
    attend = _seed_attend()
    recorder = RunRecorder(recorder_app)

    # Stage the block exactly as run_inner does before streaming: session
    # add + flush, no unit of work.
    staged = _build_block("gb-staged-0001", 3)
    dao.db.session.add(staged)
    dao.db.session.flush()

    _fail_next_flush(monkeypatch, RuntimeError("boom in finalize"))
    with pytest.raises(RuntimeError, match="boom in finalize"):
        recorder.finalize_streamed_block(
            staged,
            "streamed content",
            attend,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=4,
        )
    monkeypatch.undo()

    # No durable half-block, no durable cursor advance.
    assert (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid == "gb-staged-0001"
        ).count()
        == 0
    )
    row = LearnProgressRecord.query.filter(
        LearnProgressRecord.progress_record_bid == "progress-recorder-0001"
    ).one()
    assert row.status == LEARN_STATUS_NOT_STARTED
    assert row.block_position == 3

    # The rollback also cleared the staged row from the session: a later
    # step commit cannot persist the half-finalized block.
    recorder.save_generated_block(_build_block("gb-unrelated-0002", 0))
    assert (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid == "gb-staged-0001"
        ).count()
        == 0
    )


def test_disconnect_mid_stream_resumes_from_last_finalized_block(recorder_app):
    """Session-level model of a mid-stream disconnect: block N finalized
    (durable step), block N+1 staged when the session rolls back — the same
    add/flush/rollback sequence the producer's GeneratorExit handler in
    ``runscript_v2`` performs, exercised here directly against the recorder
    session rather than through the generator chain. The re-run must see
    block N and the advanced cursor, and no trace of block N+1. An
    end-to-end test driving the real generator ``.close()`` through
    ``run_script_inner`` is a PR3 follow-up (see the B6 ExecPlan)."""
    attend = _seed_attend()
    recorder = RunRecorder(recorder_app)

    # Step: block 3 streamed fully and finalized.
    finalized = _build_block("gb-finalized-0003", 3)
    dao.db.session.add(finalized)
    dao.db.session.flush()
    recorder.finalize_streamed_block(
        finalized,
        "block three content",
        attend,
        status=LEARN_STATUS_IN_PROGRESS,
        block_position=4,
    )

    # Block 4 starts streaming: staged only, then the client disconnects and
    # the producer rolls the session back.
    staged = _build_block("gb-staged-0004", 4)
    dao.db.session.add(staged)
    dao.db.session.flush()
    dao.db.session.rollback()

    # Resume-path reads: the finalized step survived, the staged block did
    # not, so the next run re-generates block 4 from the same cursor.
    row = LearnProgressRecord.query.filter(
        LearnProgressRecord.progress_record_bid == "progress-recorder-0001"
    ).one()
    assert row.status == LEARN_STATUS_IN_PROGRESS
    assert row.block_position == 4
    finalized_row = LearnGeneratedBlock.query.filter(
        LearnGeneratedBlock.generated_block_bid == "gb-finalized-0003"
    ).one()
    assert finalized_row.generated_content == "block three content"
    assert (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid == "gb-staged-0004"
        ).count()
        == 0
    )


def test_commit_pending_step_makes_collaborator_writes_durable(recorder_app):
    """The transitional ask-path step commits rows staged elsewhere."""
    recorder = RunRecorder(recorder_app)
    staged = _build_block("gb-ask-0001", 0)
    dao.db.session.add(staged)
    dao.db.session.flush()

    recorder.commit_pending_step()
    dao.db.session.rollback()  # a later rollback must not undo the step

    assert (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid == "gb-ask-0001"
        ).count()
        == 1
    )

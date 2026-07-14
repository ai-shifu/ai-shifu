"""End-to-end client-disconnect test for the /run generator (B7).

Deferred from B6-PR3: drive the REAL generator ``.close()`` path instead of
modeling the producer's add/flush/rollback at session level (that model lives
in ``test_run_recorder.py``).

Production shape: ``runscript_v2.run_script`` consumes ``run_script_inner``
from a producer thread and calls ``res.close()`` in its ``finally`` block when
the client disconnects. Closing the generator raises ``GeneratorExit`` at the
paused ``yield`` inside ``run_script_inner``, whose ``except GeneratorExit``
handler rolls the session back — discarding rows that were only *staged*
(plain ``db.session.add()``/``flush()``, no ``unit_of_work()``) for the
in-flight streamed block, while every previously committed recorder step
stays durable.

The tests here drive ``run_script_inner`` directly: it IS the generator that
the production wrapper closes, and the thread/queue wrapper in ``run_script``
makes deterministic mid-stream closing impossible from the outside (the
producer thread free-runs against a fast fake LLM). The setup mirrors the
producer thread: caller-owned app context + ``manage_app_context=False``.

Seeding and the deterministic fake LLM are reused from the golden harness
(``tests/golden/conftest.py``); importing the fixture objects registers them
(including their autouse behavior) in this module.
"""

from __future__ import annotations

# Importing the golden fixtures registers them for this module; the autouse
# ones (fake LLM patched at the context_v2/check_text/handle_input_ask import
# sites, risk-audit no-op for SQLite) apply to every test here.
from tests.golden.conftest import (  # noqa: F401
    golden_disable_risk_audit_commit,
    golden_llm,
    golden_sse_settings,
    golden_shifu,
    seed_golden_user,
)

# First chunk of the deterministic fake completion (see GOLDEN_LLM_CHUNKS);
# seeing it in a content event proves the LLM stream is in flight, i.e. the
# streamed block row is staged but not yet finalized.
STREAMED_MARKER = "Hello "
STREAMED_FULL_TEXT = "Hello golden learner."


def _open_run_generator(app, user_bid: str, shifu, *, input_type: str):
    from flaskr.service.learn.runscript_v2 import run_script_inner

    return run_script_inner(
        app=app,
        user_bid=user_bid,
        shifu_bid=shifu.shifu_bid,
        outline_bid=shifu.lesson_bid,
        input=None,
        input_type=input_type,
        manage_app_context=False,
    )


def _consume_until_streaming(generator) -> list:
    """Advance the generator until the first streamed LLM chunk is yielded."""
    events = []
    for event in generator:
        events.append(event)
        content = getattr(event, "content", "")
        if isinstance(content, str) and STREAMED_MARKER in content:
            return events
    raise AssertionError(
        "generator finished without yielding a streamed LLM chunk; "
        f"events: {[getattr(e, 'type', None) for e in events]}"
    )


def _load_rows(app, user_bid: str):
    from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord

    with app.app_context():
        blocks = (
            LearnGeneratedBlock.query.filter_by(user_bid=user_bid)
            .order_by(LearnGeneratedBlock.id.asc())
            .all()
        )
        records = (
            LearnProgressRecord.query.filter_by(user_bid=user_bid)
            .order_by(LearnProgressRecord.id.asc())
            .all()
        )
        block_snapshot = [
            {
                "id": block.id,
                "content": block.generated_content,
                "position": block.position,
            }
            for block in blocks
        ]
        record_snapshot = [
            {
                "id": record.id,
                "outline_item_bid": record.outline_item_bid,
                "status": record.status,
                "block_position": record.block_position,
            }
            for record in records
        ]
    return block_snapshot, record_snapshot


def test_mid_stream_close_discards_staged_block_and_rerun_resumes(
    app,
    golden_shifu,  # noqa: F811 - fixture imported from tests.golden.conftest
):
    user_bid = "golden-user-disconnect-0001"
    seed_golden_user(app, user_bid)

    # --- Phase 1: start the lesson, disconnect mid-LLM-stream. ---
    with app.app_context():
        generator = _open_run_generator(app, user_bid, golden_shifu, input_type="start")
        _consume_until_streaming(generator)
        # Production trigger: run_script's producer finally block calls
        # res.close(); GeneratorExit -> rollback in run_script_inner.
        generator.close()

    blocks_after_close, records_after_close = _load_rows(app, user_bid)

    # The staged streamed-block row (generated_content == "") must have been
    # discarded by the GeneratorExit rollback: no durable empty block.
    assert all(block["content"] != "" for block in blocks_after_close), (
        f"durable empty generated block leaked: {blocks_after_close}"
    )
    # No partially streamed content became durable either.
    assert all(
        STREAMED_MARKER not in block["content"] for block in blocks_after_close
    ), f"partial stream content leaked: {blocks_after_close}"

    # Recorder steps that committed before the stream stay durable: the
    # progress-record placeholders exist despite the disconnect.
    assert records_after_close, "committed progress records must survive close()"

    # --- Phase 2: re-run resumes from the last finalized block. ---
    with app.app_context():
        rerun = _open_run_generator(app, user_bid, golden_shifu, input_type="continue")
        rerun_events = list(rerun)

    rerun_contents = [
        event.content
        for event in rerun_events
        if isinstance(getattr(event, "content", None), str)
    ]
    # The interrupted block is regenerated from scratch on the re-run.
    assert any(STREAMED_FULL_TEXT in content for content in rerun_contents), (
        f"re-run did not regenerate the interrupted block: {rerun_contents}"
    )

    blocks_after_rerun, _ = _load_rows(app, user_bid)

    # Blocks finalized before the disconnect were not regenerated: every row
    # that was durable after the close survives the re-run unchanged.
    surviving_ids = {block["id"] for block in blocks_after_rerun}
    for block in blocks_after_close:
        assert block["id"] in surviving_ids, (
            "re-run must resume from the last finalized block instead of "
            f"rewriting history; lost row: {block}"
        )

    # The regenerated stream was finalized exactly once.
    streamed_rows = [
        block for block in blocks_after_rerun if STREAMED_FULL_TEXT in block["content"]
    ]
    assert len(streamed_rows) == 1, (
        "expected exactly one durable row for the interrupted-then-regenerated "
        f"streamed block, got: {streamed_rows}"
    )


def test_close_before_any_stream_leaves_no_generated_blocks(
    app,
    golden_shifu,  # noqa: F811 - fixture imported from tests.golden.conftest
):
    """Closing right after the first event discards everything staged.

    The first yielded events precede any LLM stream (outline updates /
    preserved content); closing there must leave no durable generated block
    at all, and a fresh run must then complete normally.
    """
    user_bid = "golden-user-disconnect-0002"
    seed_golden_user(app, user_bid)

    with app.app_context():
        generator = _open_run_generator(app, user_bid, golden_shifu, input_type="start")
        first_event = next(generator)
        assert first_event is not None
        generator.close()

    blocks_after_close, _ = _load_rows(app, user_bid)
    assert all(block["content"] != "" for block in blocks_after_close), (
        f"durable empty generated block leaked: {blocks_after_close}"
    )

    with app.app_context():
        rerun = _open_run_generator(app, user_bid, golden_shifu, input_type="continue")
        rerun_events = list(rerun)
    assert rerun_events, "re-run after immediate disconnect must still stream"

    blocks_after_rerun, _ = _load_rows(app, user_bid)
    assert any(
        STREAMED_FULL_TEXT in block["content"] for block in blocks_after_rerun
    ), f"re-run must produce the streamed block: {blocks_after_rerun}"

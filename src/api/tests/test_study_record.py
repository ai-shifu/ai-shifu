"""Verify study records expose generated learning blocks."""

from flaskr.dao import db
from flaskr.service.learn.learn_funcs import get_learn_record
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
from flaskr.service.shifu.consts import BLOCK_TYPE_CONTENT_VALUE


def test_get_learn_record_returns_blocks(app: object) -> None:
    with app.app_context():
        # Other test modules (e.g. the mdflow backfill tests) commit rows for
        # the same shifu-1/outline-1/user-1 bids into the shared SQLite
        # database; clear both tables so this test only sees its own rows
        # regardless of execution order.
        LearnGeneratedBlock.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        progress = LearnProgressRecord(
            progress_record_bid="progress-1",
            shifu_bid="shifu-1",
            outline_item_bid="outline-1",
            user_bid="user-1",
            status=LEARN_STATUS_IN_PROGRESS,
            deleted=0,
        )
        block = LearnGeneratedBlock(
            generated_block_bid="block-1",
            progress_record_bid="progress-1",
            user_bid="user-1",
            block_bid="block",
            outline_item_bid="outline-1",
            shifu_bid="shifu-1",
            type=BLOCK_TYPE_CONTENT_VALUE,
            role=0,
            generated_content="hello",
            position=1,
            status=1,
            deleted=0,
        )
        db.session.add(progress)
        db.session.add(block)
        db.session.commit()

    record = get_learn_record(app, "shifu-1", "outline-1", "user-1", preview_mode=False)
    assert len(record.records) == 1
    assert record.records[0].content == "hello"

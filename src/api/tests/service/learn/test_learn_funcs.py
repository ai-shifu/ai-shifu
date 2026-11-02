"""Verify MarkdownFlow learning records progress through interactions."""

import sys
import types
import unittest
import unittest.mock

from flask import Flask

from tests.common.fixtures.model_factories import (
    make_generated_block,
    make_progress_record,
)

# Provide a lightweight Redis stub if the dependency is missing in the test env.
try:
    import redis as _redis  # type: ignore[import-untyped]  # noqa: F401
except ImportError:  # pragma: no cover - optional dependency
    redis_stub = types.ModuleType("redis")

    class _RedisStub:
        pass

    redis_stub.Redis = _RedisStub
    sys.modules["redis"] = redis_stub

from flaskr import dao
from flaskr.service.learn.const import LEARN_STATUS_IN_PROGRESS
from flaskr.service.learn.learn_dtos import BlockType, LikeStatus
from flaskr.service.learn.learn_funcs import get_learn_record
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDERRORMESSAGE_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)


class LearnRecordLoadTests(unittest.TestCase):
    """Verify learn record load behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = Flask("learn-record-tests")
        cls.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_BINDS={
                "ai_shifu_saas": "sqlite:///:memory:",
                "ai_shifu_admin": "sqlite:///:memory:",
            },
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        dao.db.init_app(cls.app)
        with cls.app.app_context():
            dao.db.create_all()

    def setUp(self) -> None:
        self.ctx = self.app.app_context()
        self.ctx.push()
        LearnGeneratedBlock.query.delete()
        LearnProgressRecord.query.delete()
        dao.db.session.commit()

    def tearDown(self) -> None:
        dao.db.session.remove()
        self.ctx.pop()

    def test_learn_record_loads_generated_and_input_content_separately(self) -> None:
        """Ensure learn record loading uses generated content and real user input."""
        progress = make_progress_record(
            progress_record_bid="progress-1",
            shifu_bid="shifu-1",
            outline_item_bid="outline-1",
            user_bid="user-1",
            status=LEARN_STATUS_IN_PROGRESS,
        )
        dao.db.session.add(progress)

        content_block = make_generated_block(
            generated_block_bid="gen-1",
            progress_record_bid=progress.progress_record_bid,
            user_bid=progress.user_bid,
            block_bid="block-1",
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            type=BLOCK_TYPE_MDCONTENT_VALUE,
            generated_content="assistant summary output",
            block_content_conf="mdflow content should not be returned",
            status=1,
        )
        error_block = make_generated_block(
            generated_block_bid="gen-2",
            progress_record_bid=progress.progress_record_bid,
            user_bid=progress.user_bid,
            block_bid="block-2",
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            type=BLOCK_TYPE_MDERRORMESSAGE_VALUE,
            generated_content="validation failed details",
            block_content_conf="mdflow error template",
            position=1,
            status=1,
        )
        interaction_block = make_generated_block(
            generated_block_bid="gen-3",
            progress_record_bid=progress.progress_record_bid,
            user_bid=progress.user_bid,
            block_bid="block-3",
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            type=BLOCK_TYPE_MDINTERACTION_VALUE,
            generated_content="user provided answer",
            block_content_conf="? [ask in mdflow]",
            position=2,
            status=1,
        )
        dao.db.session.add_all([content_block, error_block, interaction_block])
        dao.db.session.commit()

        record = get_learn_record(
            self.app,
            shifu_bid=progress.shifu_bid,
            outline_bid=progress.outline_item_bid,
            user_bid=progress.user_bid,
            preview_mode=False,
        )

        assert len(record.records) == 3

        content_record = record.records[0]
        assert content_record.block_type == BlockType.CONTENT
        assert content_record.content == content_block.generated_content
        assert content_record.content != content_block.block_content_conf
        assert content_record.user_input == ""
        assert content_record.like_status == LikeStatus.NONE

        error_record = record.records[1]
        assert error_record.block_type == BlockType.ERROR_MESSAGE
        assert error_record.content == error_block.generated_content
        assert error_record.user_input == ""
        assert error_record.like_status == LikeStatus.NONE

        interaction_record = record.records[2]
        assert interaction_record.block_type == BlockType.INTERACTION
        assert interaction_record.content == interaction_block.block_content_conf
        assert interaction_record.user_input == interaction_block.generated_content
        assert interaction_record.content != interaction_record.user_input
        # Interaction blocks should not carry like status in API responses.
        assert interaction_record.like_status == LikeStatus.NONE

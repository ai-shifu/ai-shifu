import sys
import types
import unittest
import unittest.mock

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Provide a lightweight Redis stub if the dependency is missing in the test env.
try:
    import redis as _redis  # type: ignore  # noqa: F401
except ImportError:  # pragma: no cover - optional dependency
    redis_stub = types.ModuleType("redis")

    class _RedisStub:
        pass

    redis_stub.Redis = _RedisStub
    sys.modules["redis"] = redis_stub

import flaskr.dao as dao

# Ensure SQLAlchemy is available for model declarations.
if dao.db is None:
    _test_app = Flask("test-learn-funcs")
    _test_app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    _db = SQLAlchemy()
    _db.init_app(_test_app)
    dao.db = _db

if not hasattr(dao, "redis_client"):
    dao.redis_client = None

from flaskr.service.learn.const import LEARN_STATUS_IN_PROGRESS
from flaskr.service.learn.learn_dtos import BlockType, LikeStatus
from flaskr.service.learn.learn_funcs import get_learn_record
from flaskr.service.learn.context_v2 import RunScriptContextV2, RunScriptInfo, RunType
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDERRORMESSAGE_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)


class LearnRecordLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()
        LearnGeneratedBlock.query.delete()
        LearnProgressRecord.query.delete()
        dao.db.session.commit()

    def tearDown(self):
        dao.db.session.remove()
        self.ctx.pop()

    def test_learn_record_loads_generated_and_input_content_separately(self):
        """Ensure learn record loading uses generated content and real user input."""
        progress = LearnProgressRecord(
            progress_record_bid="progress-1",
            shifu_bid="shifu-1",
            outline_item_bid="outline-1",
            user_bid="user-1",
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        dao.db.session.add(progress)

        content_block = LearnGeneratedBlock(
            generated_block_bid="gen-1",
            progress_record_bid=progress.progress_record_bid,
            user_bid=progress.user_bid,
            block_bid="block-1",
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            type=BLOCK_TYPE_MDCONTENT_VALUE,
            generated_content="assistant summary output",
            block_content_conf="mdflow content should not be returned",
            position=0,
            status=1,
        )
        error_block = LearnGeneratedBlock(
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
        interaction_block = LearnGeneratedBlock(
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

        self.assertEqual(len(record.records), 3)

        content_record = record.records[0]
        self.assertEqual(content_record.block_type, BlockType.CONTENT)
        self.assertEqual(content_record.content, content_block.generated_content)
        self.assertNotEqual(content_record.content, content_block.block_content_conf)
        self.assertEqual(content_record.user_input, "")
        self.assertEqual(content_record.like_status, LikeStatus.NONE)

        error_record = record.records[1]
        self.assertEqual(error_record.block_type, BlockType.ERROR_MESSAGE)
        self.assertEqual(error_record.content, error_block.generated_content)
        self.assertEqual(error_record.user_input, "")
        self.assertEqual(error_record.like_status, LikeStatus.NONE)

        interaction_record = record.records[2]
        self.assertEqual(interaction_record.block_type, BlockType.INTERACTION)
        self.assertEqual(
            interaction_record.content, interaction_block.block_content_conf
        )
        self.assertEqual(
            interaction_record.user_input, interaction_block.generated_content
        )
        self.assertNotEqual(interaction_record.content, interaction_record.user_input)
        # Interaction blocks should not carry like status in API responses.
        self.assertEqual(interaction_record.like_status, LikeStatus.NONE)

    def test_mdflow_context_loads_generated_and_user_inputs(self):
        """Verify mdflow run uses generated content for context and real user input values."""
        progress = LearnProgressRecord(
            progress_record_bid="progress-ctx",
            shifu_bid="shifu-ctx",
            outline_item_bid="outline-ctx",
            user_bid="user-ctx",
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        dao.db.session.add(progress)

        teacher_block = LearnGeneratedBlock(
            generated_block_bid="ctx-gen-1",
            progress_record_bid=progress.progress_record_bid,
            user_bid=progress.user_bid,
            block_bid="ctx-block-1",
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            type=BLOCK_TYPE_MDCONTENT_VALUE,
            generated_content="assistant output from mdflow",
            block_content_conf="teacher mdflow template",
            position=0,
            status=1,
        )
        student_block = LearnGeneratedBlock(
            generated_block_bid="ctx-gen-2",
            progress_record_bid=progress.progress_record_bid,
            user_bid=progress.user_bid,
            block_bid="ctx-block-2",
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            type=BLOCK_TYPE_MDINTERACTION_VALUE,
            generated_content="real user input value",
            block_content_conf="? [question from mdflow]",
            position=1,
            status=1,
        )
        dao.db.session.add_all([teacher_block, student_block])
        dao.db.session.commit()

        ctx = RunScriptContextV2.__new__(RunScriptContextV2)
        ctx.app = self.app
        ctx._trace_args = {}
        ctx._trace = types.SimpleNamespace(update=lambda **kwargs: None)
        ctx._outline_item_info = types.SimpleNamespace(
            bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            position=0,
        )
        ctx._shifu_info = types.SimpleNamespace(use_learner_language=False)
        ctx._user_info = types.SimpleNamespace(user_id=progress.user_bid, mobile="")
        ctx._preview_mode = False
        ctx._struct = None
        ctx._is_paid = True
        ctx._run_type = RunType.OUTPUT
        ctx._can_continue = True
        ctx._input_type = "chat"
        ctx._input = None
        ctx._last_position = -1
        ctx._current_attend = progress
        ctx._get_current_attend = types.MethodType(
            lambda self, outline_bid: progress, ctx
        )
        ctx._get_next_outline_item = types.MethodType(lambda self: [], ctx)
        ctx.get_llm_settings = types.MethodType(
            lambda self, outline_bid: LLMSettings(model="fake", temperature=0.0), ctx
        )
        ctx.get_system_prompt = types.MethodType(lambda self, outline_bid: None, ctx)
        ctx._get_run_script_info = types.MethodType(
            lambda self, attend, is_ask=False: RunScriptInfo(
                attend=attend,
                outline_bid=attend.outline_item_bid,
                block_position=0,
                mdflow="doc",
            ),
            ctx,
        )

        class DummyBlock:
            def __init__(self, block_type, content, index):
                self.block_type = block_type
                self.content = content
                self.index = index

        class DummyLLMResult:
            def __init__(self, content: str):
                self.content = content

        class FakeMarkdownFlow:
            last_context = None

            def __init__(self, *args, **kwargs):
                self.blocks = [DummyBlock(BlockType.CONTENT, "md content", 0)]

            def set_output_language(self, *_args, **_kwargs):
                return self

            def get_all_blocks(self):
                return self.blocks

            def get_block(self, block_index):
                return self.blocks[block_index]

            def process(
                self, block_index, mode, variables=None, context=None, user_input=None
            ):
                FakeMarkdownFlow.last_context = context

                def _gen():
                    yield DummyLLMResult("chunk")

                return _gen()

        with (
            unittest.mock.patch(
                "flaskr.service.learn.context_v2.MarkdownFlow", FakeMarkdownFlow
            ),
            unittest.mock.patch(
                "flaskr.service.learn.context_v2.get_user_profiles", return_value={}
            ),
            unittest.mock.patch(
                "flaskr.service.learn.context_v2.get_profile_item_definition_list",
                return_value=[],
            ),
        ):
            list(ctx.run_inner(self.app))

        self.assertEqual(
            FakeMarkdownFlow.last_context,
            [
                {"role": "user", "content": "md content"},
                {"role": "assistant", "content": teacher_block.generated_content},
            ],
        )
        self.assertNotIn(
            teacher_block.block_content_conf,
            FakeMarkdownFlow.last_context[0]["content"],
        )
        self.assertNotIn(
            student_block.block_content_conf,
            FakeMarkdownFlow.last_context[1]["content"],
        )


if __name__ == "__main__":
    unittest.main()

import asyncio
import sys
import types
import unittest

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Ensure minimal SQLAlchemy bindings exist so model classes can be defined.
import flaskr.dao as dao

if dao.db is None:
    _test_app = Flask("test-context-v2")
    _test_app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    _db = SQLAlchemy()
    _db.init_app(_test_app)
    dao.db = _db

if not hasattr(dao, "redis_client"):
    dao.redis_client = None

# Stub the LLM module to avoid outbound requests during import.
if "flaskr.api.llm" not in sys.modules:
    llm_stub = types.ModuleType("flaskr.api.llm")
    llm_stub.invoke_llm = lambda *args, **kwargs: []
    sys.modules["flaskr.api.llm"] = llm_stub

from flaskr.service.learn.context_v2 import RunScriptContextV2
from flaskr.service.learn.const import CONTEXT_INTERACTION_NEXT
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.models import LearnGeneratedBlock


def _make_context() -> RunScriptContextV2:
    # Bypass __init__ since we only need helper methods for these tests.
    return RunScriptContextV2.__new__(RunScriptContextV2)


class CollectAsyncGeneratorTests(unittest.TestCase):
    def test_without_running_loop(self):
        ctx = _make_context()

        async def sample():
            yield "one"
            yield "two"

        result = ctx._collect_async_generator(sample)

        self.assertEqual(result, ["one", "two"])

    def test_inside_running_loop(self):
        ctx = _make_context()

        async def sample():
            yield "alpha"

        async def runner():
            result = ctx._collect_async_generator(sample)
            self.assertEqual(result, ["alpha"])

        asyncio.run(runner())


class RunAsyncInSafeContextTests(unittest.TestCase):
    def test_without_running_loop(self):
        ctx = _make_context()

        async def sample():
            return "result"

        self.assertEqual(
            ctx._run_async_in_safe_context(lambda: sample()),
            "result",
        )

    def test_inside_running_loop(self):
        ctx = _make_context()

        async def sample():
            return "loop"

        async def runner():
            self.assertEqual(
                ctx._run_async_in_safe_context(lambda: sample()),
                "loop",
            )

        asyncio.run(runner())


class NextChapterInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask("next-chapter-tests")
        cls.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        dao.db.init_app(cls.app)
        with cls.app.app_context():
            dao.db.create_all()

    def setUp(self):
        self.app = self.__class__.app
        self.ctx = _make_context()
        self.ctx.app = self.app
        self.ctx._outline_item_info = types.SimpleNamespace(bid="outline-1")
        self.ctx._current_attend = types.SimpleNamespace(
            progress_record_bid="progress-1",
            outline_item_bid="outline-1",
            shifu_bid="shifu-1",
            block_position=2,
        )
        self.ctx._user_info = types.SimpleNamespace(user_id="user-1")
        with self.app.app_context():
            LearnGeneratedBlock.query.delete()
            dao.db.session.commit()

    def test_emits_and_persists_button_once(self):
        with self.app.app_context():
            events = list(self.ctx._emit_next_chapter_interaction())
            self.assertEqual(len(events), 1)
            next_event = events[0]
            self.assertEqual(next_event.type, GeneratedType.INTERACTION)
            self.assertIn(CONTEXT_INTERACTION_NEXT, next_event.content)

            stored_blocks = LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.progress_record_bid
                == self.ctx._current_attend.progress_record_bid
            ).all()
            self.assertEqual(len(stored_blocks), 1)

            self.assertEqual(
                list(self.ctx._emit_next_chapter_interaction()),
                [],
            )
            self.assertEqual(
                LearnGeneratedBlock.query.filter(
                    LearnGeneratedBlock.progress_record_bid
                    == self.ctx._current_attend.progress_record_bid
                ).count(),
                1,
            )


if __name__ == "__main__":
    unittest.main()

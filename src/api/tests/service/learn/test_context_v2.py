import asyncio
import types
import unittest
from unittest.mock import patch

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

from flaskr.service.learn.context_v2 import (
    RunScriptContextV2,
    RunScriptPreviewContextV2,
)
from flaskr.service.learn.const import CONTEXT_INTERACTION_NEXT
from flaskr.service.learn.learn_dtos import GeneratedType, PlaygroundPreviewRequest
from flaskr.service.learn.models import LearnGeneratedBlock


def _make_context() -> RunScriptContextV2:
    # Bypass __init__ since we only need helper methods for these tests.
    return RunScriptContextV2.__new__(RunScriptContextV2)


_HAS_COLLECT_ASYNC = hasattr(RunScriptContextV2, "_collect_async_generator")
_HAS_RUN_ASYNC = hasattr(RunScriptContextV2, "_run_async_in_safe_context")


@unittest.skipIf(
    not _HAS_COLLECT_ASYNC,
    "_collect_async_generator helper removed in current architecture.",
)
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


@unittest.skipIf(
    not _HAS_RUN_ASYNC,
    "_run_async_in_safe_context helper removed in current architecture.",
)
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
            events = list(
                self.ctx._emit_next_chapter_interaction(self.ctx._current_attend)
            )
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
                list(self.ctx._emit_next_chapter_interaction(self.ctx._current_attend)),
                [],
            )
            self.assertEqual(
                LearnGeneratedBlock.query.filter(
                    LearnGeneratedBlock.progress_record_bid
                    == self.ctx._current_attend.progress_record_bid
                ).count(),
                1,
            )


class StreamTtsGateTests(unittest.TestCase):
    def test_should_stream_tts_respects_preview_and_listen(self):
        ctx = _make_context()

        ctx._preview_mode = False
        ctx._listen = True
        self.assertTrue(ctx._should_stream_tts())

        ctx._listen = False
        self.assertFalse(ctx._should_stream_tts())

        ctx._preview_mode = True
        ctx._listen = True
        self.assertFalse(ctx._should_stream_tts())


class PreviewResolveLlmSettingsTests(unittest.TestCase):
    def test_falls_back_to_allowlist_when_persisted_model_not_allowed(self):
        app = Flask("preview-llm-settings")
        app.config.update(
            DEFAULT_LLM_MODEL="",
            DEFAULT_LLM_TEMPERATURE=0.3,
        )
        preview_ctx = RunScriptPreviewContextV2(app)
        preview_request = PlaygroundPreviewRequest(block_index=0)
        outline = types.SimpleNamespace(
            llm="silicon/fishaudio/fish-speech-1.5",
            llm_temperature=None,
        )
        shifu = types.SimpleNamespace(llm=None, llm_temperature=None)

        with (
            patch(
                "flaskr.service.learn.context_v2.get_allowed_models",
                return_value=["ark/deepseek-v3-2"],
            ),
            patch(
                "flaskr.service.learn.context_v2.get_current_models",
                return_value=[
                    {"model": "ark/deepseek-v3-2", "display_name": "DeepSeek V3.2"}
                ],
            ),
        ):
            model, temperature = preview_ctx._resolve_llm_settings(
                preview_request,
                outline,
                shifu,
            )

        self.assertEqual(model, "ark/deepseek-v3-2")
        self.assertEqual(temperature, 0.3)


class PreviewResolveBlockIndexTests(unittest.TestCase):
    def test_keeps_valid_block_index(self):
        app = Flask("preview-block-index")
        preview_ctx = RunScriptPreviewContextV2(app)
        mdflow_context = types.SimpleNamespace(
            get_all_blocks=lambda: ["b0", "b1", "b2"]
        )

        resolved = preview_ctx._resolve_preview_block_index(
            mdflow_context,
            1,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
        )

        self.assertEqual(resolved, 1)

    def test_falls_back_to_last_block_when_out_of_range(self):
        app = Flask("preview-block-index-fallback")
        preview_ctx = RunScriptPreviewContextV2(app)
        mdflow_context = types.SimpleNamespace(
            get_all_blocks=lambda: ["b0", "b1", "b2"]
        )

        resolved = preview_ctx._resolve_preview_block_index(
            mdflow_context,
            7,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
        )

        self.assertEqual(resolved, 2)

    def test_rejects_empty_blocks(self):
        app = Flask("preview-block-index-empty")
        preview_ctx = RunScriptPreviewContextV2(app)
        mdflow_context = types.SimpleNamespace(get_all_blocks=lambda: [])

        with self.assertRaises(ValueError):
            preview_ctx._resolve_preview_block_index(
                mdflow_context,
                0,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
            )


class PreviewResolveVariablesTests(unittest.TestCase):
    def test_does_not_inject_sys_user_language_when_missing(self):
        app = Flask("preview-variables")
        preview_ctx = RunScriptPreviewContextV2(app)
        preview_request = PlaygroundPreviewRequest(block_index=0)

        with patch("flaskr.service.learn.context_v2.get_user_profiles") as mock_fetch:
            variables = preview_ctx._resolve_preview_variables(
                preview_request=preview_request,
                user_bid="user-1",
                shifu_bid="shifu-1",
            )

        self.assertIsNone(variables.get("sys_user_language"))
        mock_fetch.assert_not_called()

    def test_keeps_existing_sys_user_language(self):
        app = Flask("preview-variables-existing")
        preview_ctx = RunScriptPreviewContextV2(app)
        preview_request = PlaygroundPreviewRequest(
            block_index=0,
            variables={"sys_user_language": "fr-FR"},
        )

        with patch("flaskr.service.learn.context_v2.get_user_profiles") as mock_fetch:
            variables = preview_ctx._resolve_preview_variables(
                preview_request=preview_request,
                user_bid="user-1",
                shifu_bid="shifu-1",
            )

        self.assertEqual(variables.get("sys_user_language"), "fr-FR")
        mock_fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()

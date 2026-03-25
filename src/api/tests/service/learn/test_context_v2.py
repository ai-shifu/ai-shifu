import asyncio
import time
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
    MdflowContextV2,
    RunScriptContextV2,
    RunScriptPreviewContextV2,
)
from flaskr.service.learn.const import CONTEXT_INTERACTION_NEXT
from flaskr.service.learn.learn_dtos import GeneratedType, PlaygroundPreviewRequest
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.consts import BLOCK_TYPE_MDCONTENT_VALUE
from flaskr.util import generate_id


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


class AccessGateFeedbackHelperTests(unittest.TestCase):
    def test_detects_blocking_access_gate(self):
        ctx = _make_context()
        ctx._is_paid = False
        ctx._user_info = types.SimpleNamespace(mobile="")

        self.assertTrue(
            ctx._is_access_gate_blocking_interaction(
                {"buttons": [{"value": "_sys_pay"}]}
            )
        )
        self.assertTrue(
            ctx._is_access_gate_blocking_interaction(
                {"buttons": [{"value": "_sys_login"}]}
            )
        )

        ctx._is_paid = True
        ctx._user_info = types.SimpleNamespace(mobile="13800000000")
        self.assertFalse(
            ctx._is_access_gate_blocking_interaction(
                {"buttons": [{"value": "_sys_pay"}, {"value": "_sys_login"}]}
            )
        )


class CompletionTailInteractionTests(unittest.TestCase):
    def test_emits_feedback_and_next_when_both_conditions_met(self):
        ctx = _make_context()
        calls: list[str] = []

        def _emit_feedback(_progress):
            calls.append("feedback")
            yield "feedback-event"

        def _emit_next(_progress):
            calls.append("next")
            yield "next-event"

        ctx._emit_lesson_feedback_interaction = _emit_feedback
        ctx._emit_next_chapter_interaction = _emit_next

        events = list(
            ctx._emit_completion_tail_interactions(
                progress_record=object(),
                current_outline_completed=True,
                has_next_outline_item=True,
            )
        )

        self.assertEqual(calls, ["feedback", "next"])
        self.assertEqual(events, ["feedback-event", "next-event"])

    def test_skips_next_when_no_next_outline(self):
        ctx = _make_context()
        calls: list[str] = []

        def _emit_feedback(_progress):
            calls.append("feedback")
            yield "feedback-event"

        def _emit_next(_progress):
            calls.append("next")
            yield "next-event"

        ctx._emit_lesson_feedback_interaction = _emit_feedback
        ctx._emit_next_chapter_interaction = _emit_next

        events = list(
            ctx._emit_completion_tail_interactions(
                progress_record=object(),
                current_outline_completed=True,
                has_next_outline_item=False,
            )
        )

        self.assertEqual(calls, ["feedback"])
        self.assertEqual(events, ["feedback-event"])

    def test_emits_only_next_when_not_completed(self):
        ctx = _make_context()
        calls: list[str] = []

        def _emit_feedback(_progress):
            calls.append("feedback")
            yield "feedback-event"

        def _emit_next(_progress):
            calls.append("next")
            yield "next-event"

        ctx._emit_lesson_feedback_interaction = _emit_feedback
        ctx._emit_next_chapter_interaction = _emit_next

        events = list(
            ctx._emit_completion_tail_interactions(
                progress_record=object(),
                current_outline_completed=False,
                has_next_outline_item=True,
            )
        )

        self.assertEqual(calls, ["next"])
        self.assertEqual(events, ["next-event"])


class RuntimeOutlineBlockCountTests(unittest.TestCase):
    def test_get_next_outline_item_uses_runtime_block_count_for_leaf_outline(self):
        ctx = _make_context()
        ctx.app = Flask("runtime-outline-block-count-tests")
        ctx._preview_mode = False

        class _Column:
            def in_(self, _values):
                return self

            def __eq__(self, _other):
                return self

        class _OutlineModel:
            outline_item_bid = _Column()
            hidden = _Column()
            title = _Column()
            deleted = _Column()

        class _FakeQuery:
            def filter(self, *_args, **_kwargs):
                return self

            def all(self):
                return [("outline-1", False, "Outline 1")]

        class _FakeMarkdownFlow:
            def __init__(self, *args, **kwargs):
                pass

            def get_all_blocks(self):
                return [object(), object()]

        outline_item = HistoryItem(
            bid="outline-1",
            id=1,
            type="outline",
            children=[],
            child_count=1,
        )
        ctx._struct = HistoryItem(
            bid="shifu-1",
            id=10,
            type="shifu",
            children=[outline_item],
        )
        ctx._current_outline_item = outline_item
        ctx._current_attend = types.SimpleNamespace(
            block_position=1,
            status=LEARN_STATUS_IN_PROGRESS,
        )
        ctx._outline_model = _OutlineModel

        with (
            patch.object(dao.db.session, "query", return_value=_FakeQuery()),
            patch(
                "flaskr.service.learn.context_v2.get_outline_item_dto_with_mdflow",
                return_value=types.SimpleNamespace(mdflow="doc"),
            ),
            patch(
                "flaskr.service.learn.context_v2.MarkdownFlow",
                _FakeMarkdownFlow,
            ),
        ):
            self.assertEqual(ctx._get_next_outline_item(), [])


class ExceptionGateFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask("exception-gate-feedback")
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
        self.ctx._outline_item_info = types.SimpleNamespace(
            bid="outline-locked",
            shifu_bid="shifu-1",
        )
        self.ctx._user_info = types.SimpleNamespace(user_id="user-1")
        with self.app.app_context():
            LearnGeneratedBlock.query.delete()
            LearnProgressRecord.query.delete()
            dao.db.session.commit()

    def test_emits_feedback_for_latest_completed_progress(self):
        with self.app.app_context():
            progress = LearnProgressRecord(
                progress_record_bid="progress-1",
                shifu_bid="shifu-1",
                outline_item_bid="outline-locked",
                user_bid="user-1",
                status=LEARN_STATUS_COMPLETED,
            )
            dao.db.session.add(progress)
            dao.db.session.add(
                LearnGeneratedBlock(
                    generated_block_bid=generate_id(self.app),
                    progress_record_bid=progress.progress_record_bid,
                    user_bid="user-1",
                    block_bid="",
                    outline_item_bid=progress.outline_item_bid,
                    shifu_bid=progress.shifu_bid,
                    type=BLOCK_TYPE_MDCONTENT_VALUE,
                    role=1,
                    generated_content="content",
                    position=0,
                    block_content_conf="content",
                    status=1,
                )
            )
            dao.db.session.commit()
            events = list(self.ctx._emit_feedback_before_exception_gate())
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].type, GeneratedType.INTERACTION)

    def test_skips_when_no_completed_progress(self):
        with self.app.app_context():
            events = list(self.ctx._emit_feedback_before_exception_gate())
            self.assertEqual(events, [])

    def test_skips_completed_progress_without_generated_blocks(self):
        with self.app.app_context():
            dao.db.session.add(
                LearnProgressRecord(
                    progress_record_bid="progress-empty",
                    shifu_bid="shifu-1",
                    outline_item_bid="outline-empty",
                    user_bid="user-1",
                    status=LEARN_STATUS_COMPLETED,
                )
            )
            dao.db.session.commit()
            events = list(self.ctx._emit_feedback_before_exception_gate())
            self.assertEqual(events, [])


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

    def test_iter_stream_result_with_idle_callback_drains_while_waiting(self):
        app = Flask("stream-tts-idle-drain")
        ctx = _make_context()
        ctx.app = app

        idle_ticks: list[int] = []

        def delayed_stream():
            time.sleep(0.05)
            yield "chunk-1"

        def on_idle():
            idle_ticks.append(len(idle_ticks))
            yield f"idle-{len(idle_ticks)}"

        with app.app_context():
            outputs = list(
                ctx._iter_stream_result_with_idle_callback(
                    delayed_stream(),
                    idle_callback=on_idle,
                    idle_poll_interval=0.01,
                )
            )

        assert outputs[0][0] == "idle"
        assert outputs[-1] == ("item", "chunk-1")
        assert idle_ticks


class StreamTtsTeardownTests(unittest.TestCase):
    def test_teardown_flushes_content_then_finalizes_tts(self):
        app = Flask("stream-tts-teardown")
        ctx = _make_context()
        ctx.app = app
        ctx._element_index_cursor = 2

        class _FakeProcessor:
            next_element_index = 5

            def __init__(self):
                self.finalize_calls = []

            def finalize(self, *, commit=True):
                self.finalize_calls.append(commit)
                yield "audio-complete"

        flush_calls: list[str] = []
        processor = _FakeProcessor()

        def _flush_content_cache():
            flush_calls.append("flush")
            yield "content-flush"

        with app.app_context():
            events = list(
                ctx._teardown_stream_tts_state(
                    tts_processor=processor,
                    flush_content_cache=_flush_content_cache,
                    log_prefix="test finalize",
                )
            )

        self.assertEqual(events, ["content-flush", "audio-complete"])
        self.assertEqual(flush_calls, ["flush"])
        self.assertEqual(processor.finalize_calls, [False])
        self.assertEqual(ctx._element_index_cursor, 5)

    def test_teardown_skips_emit_on_generator_exit(self):
        app = Flask("stream-tts-teardown-generator-exit")
        ctx = _make_context()
        ctx.app = app
        ctx._element_index_cursor = 1

        class _FakeProcessor:
            next_element_index = 9

            def __init__(self):
                self.finalize_calls = 0

            def finalize(self, *, commit=True):
                self.finalize_calls += 1
                yield "audio-complete"

        flush_calls: list[str] = []
        processor = _FakeProcessor()

        def _flush_content_cache():
            flush_calls.append("flush")
            yield "content-flush"

        with app.app_context():
            events = list(
                ctx._teardown_stream_tts_state(
                    tts_processor=processor,
                    flush_content_cache=_flush_content_cache,
                    log_prefix="test finalize",
                    skip_emit=True,
                )
            )

        self.assertEqual(events, [])
        self.assertEqual(flush_calls, [])
        self.assertEqual(processor.finalize_calls, 0)
        self.assertEqual(ctx._element_index_cursor, 1)


class MdflowContextCompatibilityTests(unittest.TestCase):
    def test_init_ignores_visual_mode_when_api_missing(self):
        class FakeMarkdownFlow:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            def set_output_language(self, *_args, **_kwargs):
                return self

        with patch("flaskr.service.learn.context_v2.MarkdownFlow", FakeMarkdownFlow):
            context = MdflowContextV2(document="doc", visual_mode=False)

        self.assertIsInstance(context._mdflow, FakeMarkdownFlow)

    def test_init_calls_visual_mode_when_api_exists(self):
        class FakeMarkdownFlow:
            def __init__(self, *args, **kwargs):
                self.visual_mode = None

            def set_visual_mode(self, visual_mode):
                self.visual_mode = visual_mode

            def set_output_language(self, *_args, **_kwargs):
                return self

        with patch("flaskr.service.learn.context_v2.MarkdownFlow", FakeMarkdownFlow):
            context = MdflowContextV2(document="doc", visual_mode=False)

        self.assertFalse(context._mdflow.visual_mode)


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

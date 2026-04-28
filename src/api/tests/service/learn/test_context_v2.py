# ruff: noqa: E402
import asyncio
import sys
import time
import types
import unittest
from unittest.mock import patch

from flask import Flask
from flask_sqlalchemy import SQLAlchemy


def _install_litellm_stub() -> None:
    if "litellm" in sys.modules:
        return

    litellm_stub = types.ModuleType("litellm")
    litellm_stub.get_max_tokens = lambda _model: 4096
    litellm_stub.completion = lambda *args, **kwargs: iter([])
    sys.modules["litellm"] = litellm_stub


def _install_openai_responses_stub() -> None:
    if "openai.types.responses" in sys.modules:
        return

    responses_pkg = types.ModuleType("openai.types.responses")
    responses_pkg.__path__ = []
    response_mod = types.ModuleType("openai.types.responses.response")
    response_create_mod = types.ModuleType(
        "openai.types.responses.response_create_params"
    )
    response_function_mod = types.ModuleType(
        "openai.types.responses.response_function_tool_call"
    )
    response_text_mod = types.ModuleType(
        "openai.types.responses.response_text_config_param"
    )

    for name in [
        "IncompleteDetails",
        "Response",
        "ResponseOutputItem",
        "Tool",
        "ToolChoice",
    ]:
        setattr(response_mod, name, type(name, (), {}))

    for name in [
        "Reasoning",
        "ResponseIncludable",
        "ResponseInputParam",
        "ToolChoice",
        "ToolParam",
        "Text",
    ]:
        setattr(response_create_mod, name, type(name, (), {}))

    response_function_tool_call = type("ResponseFunctionToolCall", (), {})
    response_text_config = type("ResponseTextConfigParam", (), {})
    setattr(
        response_function_mod,
        "ResponseFunctionToolCall",
        response_function_tool_call,
    )
    setattr(
        response_text_mod,
        "ResponseTextConfigParam",
        response_text_config,
    )
    setattr(
        responses_pkg,
        "ResponseFunctionToolCall",
        response_function_tool_call,
    )

    sys.modules["openai.types.responses"] = responses_pkg
    sys.modules["openai.types.responses.response"] = response_mod
    sys.modules["openai.types.responses.response_create_params"] = response_create_mod
    sys.modules["openai.types.responses.response_function_tool_call"] = (
        response_function_mod
    )
    sys.modules["openai.types.responses.response_text_config_param"] = response_text_mod


_install_litellm_stub()
_install_openai_responses_stub()

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
    BlockType as PreviewBlockType,
    MdflowContextV2,
    PaidException,
    RUNLLMProvider,
    RunScriptContextV2,
    RunScriptPreviewContextV2,
    _iter_llm_result_content_parts,
)
from flaskr.service.learn.const import CONTEXT_INTERACTION_NEXT
from flaskr.service.learn.learn_dtos import (
    ElementType,
    GeneratedType,
    PlaygroundPreviewRequest,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.learn.preview_elements import PreviewElementRunAdapter
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
)
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from flaskr.util import generate_id


def _make_context() -> RunScriptContextV2:
    # Bypass __init__ since we only need helper methods for these tests.
    return RunScriptContextV2.__new__(RunScriptContextV2)


class _FakeLangfuseSpan:
    def __init__(self):
        self.updated = {}
        self.end_kwargs = {}

    def update(self, **kwargs):
        self.updated = kwargs

    def end(self, **kwargs):
        self.end_kwargs = kwargs


class _FakeLangfuseTrace:
    def __init__(self):
        self.updated = {}

    def update(self, **kwargs):
        self.updated = kwargs


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
            ) as get_outline_item_mock,
            patch(
                "flaskr.service.learn.context_v2.MarkdownFlow",
                _FakeMarkdownFlow,
            ),
        ):
            self.assertEqual(ctx._get_next_outline_item(), [])

        self.assertEqual(
            get_outline_item_mock.call_args.kwargs.get("outline_item_id"),
            1,
        )

    def test_get_run_script_info_uses_outline_row_id_from_struct(self):
        ctx = _make_context()
        ctx.app = Flask("runtime-outline-row-id-tests")
        ctx._preview_mode = False
        ctx._current_outline_item = HistoryItem(
            bid="outline-1",
            id=42,
            type="outline",
            children=[],
            child_count=2,
        )
        ctx._struct = HistoryItem(
            bid="shifu-1",
            id=1,
            type="shifu",
            children=[ctx._current_outline_item],
        )

        attend = types.SimpleNamespace(outline_item_bid="outline-1", block_position=0)

        class _FakeMarkdownFlow:
            def __init__(self, *args, **kwargs):
                pass

            def get_all_blocks(self):
                return [object(), object()]

        with (
            patch(
                "flaskr.service.learn.context_v2.get_outline_item_dto_with_mdflow",
                return_value=types.SimpleNamespace(
                    mdflow="doc",
                    outline_bid="outline-1",
                    title="Outline 1",
                ),
            ) as get_outline_item_mock,
            patch(
                "flaskr.service.learn.context_v2.MarkdownFlow",
                _FakeMarkdownFlow,
            ),
        ):
            run_info = ctx._get_run_script_info(attend)

        self.assertIsNotNone(run_info)
        self.assertEqual(
            get_outline_item_mock.call_args.kwargs.get("outline_item_id"),
            42,
        )


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


class ReloadFromElementBidTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask("reload-from-element-bid")
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
        self.ctx._user_info = types.SimpleNamespace(user_id="user-1")
        self.ctx._input_type = "normal"
        self.ctx._can_continue = True
        self.ctx.run = lambda _app: iter(())
        with self.app.app_context():
            LearnGeneratedElement.query.delete()
            LearnGeneratedBlock.query.delete()
            LearnProgressRecord.query.delete()
            dao.db.session.commit()

    def test_reload_element_bid_realigns_progress_to_source_block(self):
        with self.app.app_context():
            progress = LearnProgressRecord(
                progress_record_bid="progress-1",
                shifu_bid="shifu-1",
                outline_item_bid="outline-1",
                user_bid="user-1",
                status=LEARN_STATUS_COMPLETED,
                block_position=5,
            )
            dao.db.session.add(progress)

            interaction_block = LearnGeneratedBlock(
                generated_block_bid="generated-interaction-1",
                progress_record_bid=progress.progress_record_bid,
                user_bid=progress.user_bid,
                block_bid="",
                outline_item_bid=progress.outline_item_bid,
                shifu_bid=progress.shifu_bid,
                type=BLOCK_TYPE_MDINTERACTION_VALUE,
                role=1,
                generated_content="selected value",
                position=2,
                block_content_conf="?[%{{nickname}} Alice | Bob]",
                status=1,
            )
            later_block = LearnGeneratedBlock(
                generated_block_bid="generated-content-2",
                progress_record_bid=progress.progress_record_bid,
                user_bid=progress.user_bid,
                block_bid="",
                outline_item_bid=progress.outline_item_bid,
                shifu_bid=progress.shifu_bid,
                type=BLOCK_TYPE_MDCONTENT_VALUE,
                role=1,
                generated_content="later content",
                position=3,
                block_content_conf="later content",
                status=1,
            )
            dao.db.session.add(interaction_block)
            dao.db.session.add(later_block)
            dao.db.session.add(
                LearnGeneratedElement(
                    element_bid="interaction-element-1",
                    progress_record_bid=progress.progress_record_bid,
                    user_bid=progress.user_bid,
                    generated_block_bid=interaction_block.generated_block_bid,
                    outline_item_bid=progress.outline_item_bid,
                    shifu_bid=progress.shifu_bid,
                    run_session_bid="run-1",
                    run_event_seq=1,
                    role="teacher",
                    element_index=4,
                    element_type=ElementType.INTERACTION.value,
                    element_type_code=205,
                    change_type="render",
                    content_text="?[%{{nickname}} Alice | Bob]",
                    payload="{}",
                    status=1,
                )
            )
            dao.db.session.add(
                LearnGeneratedElement(
                    element_bid="later-element-1",
                    progress_record_bid=progress.progress_record_bid,
                    user_bid=progress.user_bid,
                    generated_block_bid=later_block.generated_block_bid,
                    outline_item_bid=progress.outline_item_bid,
                    shifu_bid=progress.shifu_bid,
                    run_session_bid="run-1",
                    run_event_seq=2,
                    role="teacher",
                    element_index=5,
                    element_type=ElementType.TEXT.value,
                    element_type_code=213,
                    change_type="render",
                    content_text="later content",
                    payload="{}",
                    status=1,
                )
            )
            dao.db.session.commit()

            list(
                self.ctx.reload(
                    self.app,
                    "interaction-element-1",
                    reload_element_bid="interaction-element-1",
                )
            )

            dao.db.session.refresh(progress)
            dao.db.session.refresh(interaction_block)
            dao.db.session.refresh(later_block)
            later_element = LearnGeneratedElement.query.filter(
                LearnGeneratedElement.element_bid == "later-element-1"
            ).first()

            self.assertEqual(progress.block_position, 2)
            self.assertEqual(progress.status, LEARN_STATUS_IN_PROGRESS)
            self.assertEqual(interaction_block.status, 1)
            self.assertEqual(later_block.status, 0)
            self.assertIsNotNone(later_element)
            self.assertEqual(later_element.status, 0)

    def test_reload_preserves_ask_and_answer_blocks(self):
        with self.app.app_context():
            progress = LearnProgressRecord(
                progress_record_bid="progress-ask-keep",
                shifu_bid="shifu-1",
                outline_item_bid="outline-1",
                user_bid="user-1",
                status=LEARN_STATUS_COMPLETED,
                block_position=6,
            )
            dao.db.session.add(progress)

            target_block = LearnGeneratedBlock(
                generated_block_bid="generated-content-target",
                progress_record_bid=progress.progress_record_bid,
                user_bid=progress.user_bid,
                block_bid="",
                outline_item_bid=progress.outline_item_bid,
                shifu_bid=progress.shifu_bid,
                type=BLOCK_TYPE_MDCONTENT_VALUE,
                role=1,
                generated_content="target content",
                position=5,
                block_content_conf="target content",
                status=1,
            )
            ask_block = LearnGeneratedBlock(
                generated_block_bid="generated-ask-1",
                progress_record_bid=progress.progress_record_bid,
                user_bid=progress.user_bid,
                block_bid="",
                outline_item_bid=progress.outline_item_bid,
                shifu_bid=progress.shifu_bid,
                type=BLOCK_TYPE_MDASK_VALUE,
                role=0,
                generated_content="why?",
                position=5,
                block_content_conf="why?",
                status=1,
            )
            answer_block = LearnGeneratedBlock(
                generated_block_bid="generated-answer-1",
                progress_record_bid=progress.progress_record_bid,
                user_bid=progress.user_bid,
                block_bid="",
                outline_item_bid=progress.outline_item_bid,
                shifu_bid=progress.shifu_bid,
                type=BLOCK_TYPE_MDANSWER_VALUE,
                role=1,
                generated_content="because",
                position=5,
                block_content_conf="because",
                status=1,
            )
            later_block = LearnGeneratedBlock(
                generated_block_bid="generated-content-later",
                progress_record_bid=progress.progress_record_bid,
                user_bid=progress.user_bid,
                block_bid="",
                outline_item_bid=progress.outline_item_bid,
                shifu_bid=progress.shifu_bid,
                type=BLOCK_TYPE_MDCONTENT_VALUE,
                role=1,
                generated_content="later content",
                position=6,
                block_content_conf="later content",
                status=1,
            )
            dao.db.session.add(target_block)
            dao.db.session.add(ask_block)
            dao.db.session.add(answer_block)
            dao.db.session.add(later_block)
            dao.db.session.add(
                LearnGeneratedElement(
                    element_bid="target-element-1",
                    progress_record_bid=progress.progress_record_bid,
                    user_bid=progress.user_bid,
                    generated_block_bid=target_block.generated_block_bid,
                    outline_item_bid=progress.outline_item_bid,
                    shifu_bid=progress.shifu_bid,
                    run_session_bid="run-1",
                    run_event_seq=1,
                    role="teacher",
                    element_index=1,
                    element_type=ElementType.TEXT.value,
                    element_type_code=213,
                    change_type="render",
                    content_text="target content",
                    payload="{}",
                    status=1,
                )
            )
            dao.db.session.commit()

            list(
                self.ctx.reload(
                    self.app,
                    "target-element-1",
                    reload_element_bid="target-element-1",
                )
            )

            dao.db.session.refresh(target_block)
            dao.db.session.refresh(ask_block)
            dao.db.session.refresh(answer_block)
            dao.db.session.refresh(later_block)

            self.assertEqual(target_block.status, 0)
            self.assertEqual(later_block.status, 0)
            self.assertEqual(ask_block.status, 1)
            self.assertEqual(answer_block.status, 1)


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


class LLMResultContentPartsTests(unittest.TestCase):
    def test_formatted_elements_are_preserved_without_raw_splitting(self):
        result = types.SimpleNamespace(
            content="",
            formatted_elements=[
                types.SimpleNamespace(content="<svg", type="svg", number=7),
                types.SimpleNamespace(content="</svg>", type="svg", number=7),
            ],
        )

        self.assertEqual(
            list(_iter_llm_result_content_parts(result)),
            [("<svg", "svg", 7), ("</svg>", "svg", 7)],
        )


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


class PreviewRunLlmLoggingTests(unittest.TestCase):
    def test_complete_logs_full_preview_output(self):
        app = Flask("preview-run-llm-logging")
        parent_observation = object()
        provider = RUNLLMProvider(
            app=app,
            llm_settings=types.SimpleNamespace(model="gpt-test", temperature=0.6),
            trace=object(),
            parent_observation=parent_observation,
            trace_args={
                "user_id": "user-1",
                "metadata": {
                    "shifu_bid": "shifu-1",
                    "outline_bid": "outline-1",
                    "session_id": "session-1",
                    "scene": "lesson_preview",
                },
            },
            usage_context=types.SimpleNamespace(),
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
        )
        captured = {}

        with (
            patch.object(app.logger, "info") as mock_info,
            patch(
                "flaskr.service.learn.context_v2.chat_llm",
                side_effect=lambda *_args, **_kwargs: (
                    captured.setdefault("parent_observation", _args[2]),
                    iter(
                        [
                            types.SimpleNamespace(result="First line\n"),
                            types.SimpleNamespace(result="Second line"),
                        ]
                    ),
                )[1],
            ),
        ):
            output = provider.complete(messages=[{"role": "user", "content": "hello"}])

        self.assertEqual(output, "First line\nSecond line")
        self.assertIs(captured["parent_observation"], parent_observation)
        mock_info.assert_any_call(
            "preview llm output | shifu_bid=%s | outline_bid=%s | session_id=%s | scene=%s | model=%s | temperature=%s | output=%s",
            "shifu-1",
            "outline-1",
            "session-1",
            "lesson_preview",
            "gpt-test",
            0.6,
            "First line\nSecond line",
        )


class LangfuseTraceFinalizationTests(unittest.TestCase):
    def test_runtime_context_uses_current_langfuse_client(self):
        app = Flask("runtime-langfuse-client")
        sentinel_client = object()
        captured = {}
        struct = HistoryItem(
            bid="shifu-1",
            id=1,
            type="shifu",
            children=[
                HistoryItem(
                    bid="outline-1",
                    id=2,
                    type="outline",
                    children=[],
                    child_count=0,
                )
            ],
        )

        def _fake_create_trace_with_root_span(
            *, client, trace_payload, root_span_payload
        ):
            captured["client"] = client
            captured["trace_payload"] = trace_payload
            captured["root_span_payload"] = root_span_payload
            return _FakeLangfuseTrace(), _FakeLangfuseSpan()

        with (
            patch(
                "flaskr.service.learn.context_v2.get_langfuse_client",
                return_value=sentinel_client,
            ),
            patch(
                "flaskr.service.learn.context_v2.get_request_trace_id",
                return_value="req-trace-1",
            ),
            patch(
                "flaskr.service.learn.context_v2.create_trace_with_root_span",
                side_effect=_fake_create_trace_with_root_span,
            ),
        ):
            RunScriptContextV2(
                app=app,
                shifu_info=types.SimpleNamespace(),
                struct=struct,
                outline_item_info=types.SimpleNamespace(
                    bid="outline-1",
                    shifu_bid="shifu-1",
                    title="Lesson",
                ),
                user_info=types.SimpleNamespace(user_id="user-1"),
                is_paid=True,
                preview_mode=False,
            )

        self.assertIs(captured["client"], sentinel_client)
        self.assertEqual(captured["trace_payload"]["id"], "req-trace-1")

    def test_set_input_normalizes_structured_value_for_trace(self):
        ctx = _make_context()
        ctx._trace_args = {}

        ctx.set_input({"lang": ["Python", "Go"], "level": ["Beginner"]}, "select")

        self.assertEqual(ctx._trace_args["input"], "Python, Go, Beginner")
        self.assertEqual(ctx._trace_args["input_type"], "select")

    def test_set_input_normalizes_python_literal_string_for_trace(self):
        ctx = _make_context()
        ctx._trace_args = {}

        ctx.set_input("{'lang': ['Python', 'Go']}", "select")

        self.assertEqual(ctx._trace_args["input"], "Python, Go")

    def test_runtime_finalize_skips_empty_output_overwrite(self):
        ctx = _make_context()
        ctx._trace = _FakeLangfuseTrace()
        ctx._trace_root_span = _FakeLangfuseSpan()
        ctx._trace_args = {
            "user_id": "user-1",
            "session_id": "session-1",
            "name": "lesson_runtime/trace/Outline",
        }
        ctx._langfuse_output_chunks = []

        ctx._finalize_langfuse_trace()

        self.assertEqual(
            ctx._trace.updated,
            {
                "user_id": "user-1",
                "session_id": "session-1",
                "name": "lesson_runtime/trace/Outline",
            },
        )
        self.assertEqual(ctx._trace_root_span.end_kwargs, {})

    def test_runtime_finalize_uses_accumulated_output(self):
        ctx = _make_context()
        ctx._trace = _FakeLangfuseTrace()
        ctx._trace_root_span = _FakeLangfuseSpan()
        ctx._trace_args = {
            "user_id": "user-1",
            "session_id": "session-1",
            "input": "student input",
            "name": "lesson_runtime/trace/Outline",
        }
        ctx._langfuse_output_chunks = ["chunk-1", "chunk-2"]

        ctx._finalize_langfuse_trace()

        self.assertEqual(ctx._trace.updated["output"], "chunk-1chunk-2")
        self.assertEqual(
            ctx._trace_root_span.end_kwargs,
            {"input": "student input", "output": "chunk-1chunk-2"},
        )

    def test_append_langfuse_output_normalizes_python_literal_string(self):
        ctx = _make_context()
        ctx._langfuse_output_chunks = []

        ctx.append_langfuse_output("['part-1', 'part-2']")

        self.assertEqual(ctx._langfuse_output_chunks, ['["part-1", "part-2"]'])


class PreviewLangfuseTraceTests(unittest.TestCase):
    def test_stream_preview_sets_session_id_and_finalizes_root_span(self):
        app = Flask("preview-langfuse-trace")
        preview_ctx = RunScriptPreviewContextV2(app)
        preview_request = PlaygroundPreviewRequest(block_index=0)
        captured = {}

        class _FakePreviewContextStore:
            def __init__(self, *_args, **_kwargs):
                pass

            def get_context(self, *_args, **_kwargs):
                return []

            def replace_context(self, *_args, **_kwargs):
                return None

        class _FakePreviewMdflowContext:
            def __init__(self, *args, **kwargs):
                _ = args, kwargs

            @staticmethod
            def normalize_context_messages(_value):
                return None

            def get_block(self, _block_index):
                return types.SimpleNamespace(
                    block_type=PreviewBlockType.CONTENT, content="Prompt block"
                )

            def process(self, **_kwargs):
                return (
                    item
                    for item in [
                        types.SimpleNamespace(
                            content="Hello preview",
                            type="text",
                            number=0,
                        )
                    ]
                )

        class _FakePreviewAdapter:
            def __init__(self, *_args, **_kwargs):
                pass

            def process(self, events):
                return events

        def _fake_create_trace_with_root_span(
            *, client, trace_payload, root_span_payload
        ):
            _ = client, root_span_payload
            captured["trace_payload"] = trace_payload
            trace = _FakeLangfuseTrace()
            root_span = _FakeLangfuseSpan()
            captured["trace"] = trace
            captured["root_span"] = root_span
            return trace, root_span

        with (
            patch.object(
                preview_ctx,
                "_get_outline_record",
                return_value=types.SimpleNamespace(content="Doc", title="Outline"),
            ),
            patch.object(
                preview_ctx,
                "_get_shifu_record",
                return_value=types.SimpleNamespace(
                    llm=None,
                    llm_temperature=None,
                    use_learner_language=0,
                ),
            ),
            patch.object(
                preview_ctx, "_resolve_document_prompt", return_value="PROMPT"
            ),
            patch.object(
                preview_ctx, "_resolve_llm_settings", return_value=("gpt-test", 0.2)
            ),
            patch.object(preview_ctx, "_resolve_preview_variables", return_value={}),
            patch.object(preview_ctx, "_update_preview_context", return_value=None),
            patch(
                "flaskr.service.learn.context_v2._PreviewContextStore",
                _FakePreviewContextStore,
            ),
            patch(
                "flaskr.service.learn.context_v2.MdflowContextV2",
                _FakePreviewMdflowContext,
            ),
            patch(
                "flaskr.service.learn.context_v2.PreviewElementRunAdapter",
                _FakePreviewAdapter,
            ),
            patch(
                "flaskr.service.learn.context_v2.create_trace_with_root_span",
                side_effect=_fake_create_trace_with_root_span,
            ),
            patch(
                "flaskr.service.learn.context_v2.get_request_trace_id",
                return_value="preview-req-trace-1",
            ),
        ):
            messages = list(
                preview_ctx.stream_preview(
                    preview_request=preview_request,
                    shifu_bid="shifu-1",
                    outline_bid="outline-1",
                    user_bid="user-1",
                    session_id="preview-session-1",
                )
            )

        self.assertTrue(messages)
        self.assertEqual(captured["trace_payload"]["id"], "preview-req-trace-1")
        self.assertEqual(captured["trace_payload"]["session_id"], "preview-session-1")
        self.assertEqual(captured["trace"].updated["input"], "Prompt block")
        self.assertEqual(captured["trace"].updated["output"], "Hello preview")
        self.assertEqual(
            captured["root_span"].end_kwargs,
            {"input": "Prompt block", "output": "Hello preview"},
        )


class PreviewElementizationTests(unittest.TestCase):
    def test_preview_content_events_preserve_stream_parts(self):
        app = Flask("preview-content-events")
        preview_ctx = RunScriptPreviewContextV2(app)

        events = preview_ctx._preview_events_from_result(
            llm_result=types.SimpleNamespace(
                content="Hello preview",
                type="text",
                number=0,
            ),
            outline_bid="outline-1",
            generated_block_bid="0",
            current_block=types.SimpleNamespace(block_type="content"),
            is_user_input_validation=False,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, GeneratedType.CONTENT)
        self.assertEqual(
            events[0].get_mdflow_stream_parts(),
            [("Hello preview", "text", 0)],
        )

    def test_preview_content_stream_emits_element_and_done(self):
        app = Flask("preview-content-stream")
        preview_ctx = RunScriptPreviewContextV2(app)
        adapter = PreviewElementRunAdapter(
            app,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            user_bid="user-1",
            run_session_bid="preview-session-1",
        )
        content_chunks: list[str] = []

        messages = list(
            adapter.process(
                preview_ctx._iter_preview_generated_events(
                    result=(
                        chunk
                        for chunk in [
                            types.SimpleNamespace(
                                content="Hello preview",
                                type="text",
                                number=0,
                            )
                        ]
                    ),
                    outline_bid="outline-1",
                    block_index=0,
                    current_block=types.SimpleNamespace(block_type="content"),
                    is_user_input_validation=False,
                    content_chunks=content_chunks,
                    langfuse_output_chunks=[],
                )
            )
        )

        element_messages = [item for item in messages if item.type == "element"]
        self.assertGreaterEqual(len(element_messages), 2)
        self.assertEqual(content_chunks, ["Hello preview"])
        self.assertEqual(element_messages[0].content.element_type, ElementType.TEXT)
        self.assertFalse(element_messages[0].content.is_final)
        self.assertEqual(element_messages[-1].content.element_type, ElementType.TEXT)
        self.assertTrue(element_messages[-1].content.is_final)
        done_messages = [
            item for item in messages if item.type == GeneratedType.DONE.value
        ]
        self.assertEqual(len(done_messages), 2)
        self.assertFalse(done_messages[0].is_terminal)
        self.assertEqual(messages[-1].type, GeneratedType.DONE.value)
        self.assertTrue(messages[-1].is_terminal)

    def test_preview_content_uses_formatted_elements_when_top_level_content_empty(self):
        app = Flask("preview-content-formatted-elements")
        preview_ctx = RunScriptPreviewContextV2(app)
        adapter = PreviewElementRunAdapter(
            app,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            user_bid="user-1",
            run_session_bid="preview-session-3",
        )
        content_chunks: list[str] = []

        messages = list(
            adapter.process(
                preview_ctx._iter_preview_generated_events(
                    result=types.SimpleNamespace(
                        content="",
                        formatted_elements=[
                            types.SimpleNamespace(
                                content="Visual caption",
                                type="text",
                                number=0,
                            )
                        ],
                    ),
                    outline_bid="outline-1",
                    block_index=0,
                    current_block=types.SimpleNamespace(block_type="content"),
                    is_user_input_validation=False,
                    content_chunks=content_chunks,
                    langfuse_output_chunks=[],
                )
            )
        )

        element_messages = [item for item in messages if item.type == "element"]
        self.assertGreaterEqual(len(element_messages), 2)
        self.assertEqual(content_chunks, ["Visual caption"])
        self.assertEqual(element_messages[0].content.content_text, "Visual caption")
        done_messages = [
            item for item in messages if item.type == GeneratedType.DONE.value
        ]
        self.assertEqual(len(done_messages), 2)
        self.assertFalse(done_messages[0].is_terminal)
        self.assertEqual(messages[-1].type, GeneratedType.DONE.value)
        self.assertTrue(messages[-1].is_terminal)

    def test_preview_interaction_validation_uses_formatted_elements_when_content_empty(
        self,
    ):
        app = Flask("preview-interaction-validation-formatted-elements")
        preview_ctx = RunScriptPreviewContextV2(app)
        adapter = PreviewElementRunAdapter(
            app,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            user_bid="user-1",
            run_session_bid="preview-session-4",
        )
        content_chunks: list[str] = []

        messages = list(
            adapter.process(
                preview_ctx._iter_preview_generated_events(
                    result=types.SimpleNamespace(
                        content="",
                        formatted_elements=[
                            types.SimpleNamespace(
                                content="Validation error",
                                type="text",
                                number=0,
                            )
                        ],
                    ),
                    outline_bid="outline-1",
                    block_index=2,
                    current_block=types.SimpleNamespace(
                        block_type=PreviewBlockType.INTERACTION,
                        content="? [A//a]",
                    ),
                    is_user_input_validation=True,
                    content_chunks=content_chunks,
                    langfuse_output_chunks=[],
                )
            )
        )

        element_messages = [item for item in messages if item.type == "element"]
        self.assertGreaterEqual(len(element_messages), 2)
        self.assertEqual(content_chunks, ["Validation error"])
        self.assertEqual(element_messages[0].content.content_text, "Validation error")
        done_messages = [
            item for item in messages if item.type == GeneratedType.DONE.value
        ]
        self.assertEqual(len(done_messages), 2)
        self.assertFalse(done_messages[0].is_terminal)
        self.assertEqual(messages[-1].type, GeneratedType.DONE.value)
        self.assertTrue(messages[-1].is_terminal)

    def test_preview_interaction_stream_emits_interaction_element_and_done(self):
        app = Flask("preview-interaction-stream")
        preview_ctx = RunScriptPreviewContextV2(app)
        adapter = PreviewElementRunAdapter(
            app,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            user_bid="user-1",
            run_session_bid="preview-session-2",
        )
        content_chunks: list[str] = []
        langfuse_output_chunks: list[str] = []

        messages = list(
            adapter.process(
                preview_ctx._iter_preview_generated_events(
                    result=types.SimpleNamespace(content="Please choose one"),
                    outline_bid="outline-1",
                    block_index=2,
                    current_block=types.SimpleNamespace(
                        block_type=PreviewBlockType.INTERACTION,
                        content="? [A//a]",
                    ),
                    is_user_input_validation=False,
                    content_chunks=content_chunks,
                    langfuse_output_chunks=langfuse_output_chunks,
                )
            )
        )

        element_messages = [item for item in messages if item.type == "element"]
        self.assertEqual(len(element_messages), 1)
        interaction = element_messages[0].content
        self.assertEqual(interaction.element_type, ElementType.INTERACTION)
        self.assertEqual(interaction.role, "ui")
        self.assertEqual(interaction.content_text, "Please choose one")
        self.assertEqual(content_chunks, [])
        self.assertEqual(langfuse_output_chunks, ["Please choose one"])
        done_messages = [
            item for item in messages if item.type == GeneratedType.DONE.value
        ]
        self.assertEqual(len(done_messages), 2)
        self.assertFalse(done_messages[0].is_terminal)
        self.assertEqual(messages[-1].type, GeneratedType.DONE.value)
        self.assertTrue(messages[-1].is_terminal)


class RuntimeExceptionLangfuseTests(unittest.TestCase):
    def test_run_emits_gate_interaction_after_paid_exception(self):
        app = Flask("runtime-langfuse-paid")
        ctx = _make_context()

        def _raise_paid(_app):
            raise PaidException()

        ctx.run_inner = _raise_paid
        ctx._emit_feedback_before_exception_gate = lambda: iter(["feedback"])
        ctx._emit_current_progress_gate_interaction = lambda content: iter([content])

        with patch("flaskr.service.learn.context_v2._", lambda key: key):
            outputs = list(ctx.run(app))

        self.assertEqual(outputs, ["feedback", "?[server.order.checkout//_sys_pay]"])


if __name__ == "__main__":
    unittest.main()

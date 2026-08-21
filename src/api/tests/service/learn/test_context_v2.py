# ruff: noqa: E402
"""Verify learning-context outline navigation and failure handling."""

import asyncio
import json
import sys
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, call, patch

from flask import Flask


def _install_litellm_stub() -> None:
    if "litellm" in sys.modules:
        return

    litellm_stub = types.ModuleType("litellm")

    def get_model_info(*args: object, **kwargs: object):
        _ = args, kwargs
        message = "unknown model"
        raise ValueError(message)

    litellm_stub.get_max_tokens = lambda _model: 4096
    litellm_stub.get_model_info = get_model_info
    litellm_stub.completion = lambda *_args, **_kwargs: iter([])
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
    response_function_mod.ResponseFunctionToolCall = response_function_tool_call
    response_text_mod.ResponseTextConfigParam = response_text_config
    responses_pkg.ResponseFunctionToolCall = response_function_tool_call

    sys.modules["openai.types.responses"] = responses_pkg
    sys.modules["openai.types.responses.response"] = response_mod
    sys.modules["openai.types.responses.response_create_params"] = response_create_mod
    sys.modules["openai.types.responses.response_function_tool_call"] = (
        response_function_mod
    )
    sys.modules["openai.types.responses.response_text_config_param"] = response_text_mod


_install_litellm_stub()
_install_openai_responses_stub()

import itertools

import pytest
from flaskr import dao
from flaskr.service.learn import context_v2 as context_v2_module
from flaskr.service.learn.const import CONTEXT_INTERACTION_NEXT
from flaskr.service.learn.context_v2 import (
    BlockType as PreviewBlockType,
)
from flaskr.service.learn.context_v2 import (
    MdflowContextV2,
    PaidError,
    RUNLLMProvider,
    RunScriptContextV2,
    RunScriptPreviewContextV2,
    _find_outline_path_or_raise,
    _PreviewContextStore,
    _resolve_runtime_language_context,
    _resolve_runtime_output_language,
)
from flaskr.service.learn.learn_dtos import (
    ElementType,
    GeneratedType,
    PlaygroundPreviewRequest,
)
from flaskr.service.learn.learner_profile_prompt import (
    LEARNER_PROFILE_PROMPT_MARKER,
    build_course_prompt,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.learn.preview_elements import PreviewElementRunAdapter
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_NOT_STARTED,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.util import generate_id
from markdown_flow import USER_ANSWER_CONTEXT_KEY, MarkdownFlow
from markdown_flow.llm import LLMResult


def _make_context() -> RunScriptContextV2:
    # Bypass __init__ since we only need helper methods for these tests.
    ctx = RunScriptContextV2.__new__(RunScriptContextV2)
    ctx._stop_event = None
    return ctx


class _FakeLangfuseSpan:
    def __init__(self) -> None:
        self.updated = {}
        self.end_kwargs = {}

    def update(self, **kwargs: object):
        self.updated = kwargs

    def end(self, **kwargs: object):
        self.end_kwargs = kwargs


class _FakeLangfuseTrace:
    def __init__(self) -> None:
        self.updated = {}

    def update(self, **kwargs: object):
        self.updated = kwargs


_HAS_COLLECT_ASYNC = hasattr(RunScriptContextV2, "_collect_async_generator")
_HAS_RUN_ASYNC = hasattr(RunScriptContextV2, "_run_async_in_safe_context")


class OutlinePathGuardTests(unittest.TestCase):
    """Verify outline path guard behavior."""

    def test_get_next_outline_item_ignores_missing_current_outline_item(self):
        ctx = _make_context()
        ctx._struct = HistoryItem(bid="shifu-bid", id=1, type="shifu", children=[])
        ctx._current_outline_item = None
        ctx._current_attend = types.SimpleNamespace(
            block_position=0,
            status=LEARN_STATUS_IN_PROGRESS,
        )
        ctx._outline_model = types.SimpleNamespace(
            outline_item_bid=MagicMock(),
            hidden=MagicMock(),
            title=MagicMock(),
            deleted=MagicMock(),
        )
        query = MagicMock()
        query.filter.return_value.all.return_value = []

        with patch.object(context_v2_module.db.session, "query", return_value=query):
            result = ctx._get_next_outline_item()

        assert result == []

    def test_find_outline_path_returns_path_when_outline_exists(self):
        root = HistoryItem(
            bid="shifu-bid",
            id=1,
            type="shifu",
            children=[
                HistoryItem(bid="outline-bid", id=2, type="outline", children=[])
            ],
        )

        path = _find_outline_path_or_raise(root, "outline-bid")

        assert [item.bid for item in path] == ["shifu-bid", "outline-bid"]

    def test_find_outline_path_raises_app_error_when_outline_missing(self):
        root = HistoryItem(bid="shifu-bid", id=1, type="shifu", children=[])

        with (
            patch(
                "flaskr.service.learn.context_v2.raise_error",
                side_effect=RuntimeError("lesson missing"),
            ) as raise_error_mock,
            pytest.raises(RuntimeError),
        ):
            _find_outline_path_or_raise(root, "missing-outline")

        raise_error_mock.assert_called_once_with("server.shifu.lessonNotFoundInCourse")


@unittest.skipIf(
    not _HAS_COLLECT_ASYNC,
    "_collect_async_generator helper removed in current architecture.",
)
class CollectAsyncGeneratorTests(unittest.TestCase):
    """Verify collect async generator behavior."""

    def test_without_running_loop(self):
        ctx = _make_context()

        async def sample():
            yield "one"
            yield "two"

        result = ctx._collect_async_generator(sample)

        assert result == ["one", "two"]

    def test_inside_running_loop(self):
        ctx = _make_context()

        async def sample():
            yield "alpha"

        async def runner():
            result = ctx._collect_async_generator(sample)
            assert result == ["alpha"]

        asyncio.run(runner())


@unittest.skipIf(
    not _HAS_RUN_ASYNC,
    "_run_async_in_safe_context helper removed in current architecture.",
)
class RunAsyncInSafeContextTests(unittest.TestCase):
    """Verify run async in safe context behavior."""

    def test_without_running_loop(self):
        ctx = _make_context()

        async def sample():
            return "result"

        assert ctx._run_async_in_safe_context(sample) == "result"

    def test_inside_running_loop(self):
        ctx = _make_context()

        async def sample():
            return "loop"

        async def runner():
            assert ctx._run_async_in_safe_context(sample) == "loop"

        asyncio.run(runner())


class NextChapterInteractionTests(unittest.TestCase):
    """Verify next chapter interaction behavior."""

    @classmethod
    def setUpClass(cls) -> None:
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
            assert len(events) == 1
            next_event = events[0]
            assert next_event.type == GeneratedType.INTERACTION
            assert CONTEXT_INTERACTION_NEXT in next_event.content

            stored_blocks = LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.progress_record_bid
                == self.ctx._current_attend.progress_record_bid
            ).all()
            assert len(stored_blocks) == 1

            assert (
                list(self.ctx._emit_next_chapter_interaction(self.ctx._current_attend))
                == []
            )
            assert (
                LearnGeneratedBlock.query.filter(
                    LearnGeneratedBlock.progress_record_bid
                    == self.ctx._current_attend.progress_record_bid
                ).count()
                == 1
            )


class AccessGateFeedbackHelperTests(unittest.TestCase):
    """Verify access gate feedback helper behavior."""

    def test_detects_blocking_access_gate(self):
        ctx = _make_context()
        ctx._is_paid = False
        ctx._user_info = types.SimpleNamespace(mobile="")

        assert ctx._is_access_gate_blocking_interaction(
            {"buttons": [{"value": "_sys_pay"}]}
        )
        assert ctx._is_access_gate_blocking_interaction(
            {"buttons": [{"value": "_sys_login"}]}
        )

        ctx._is_paid = True
        ctx._user_info = types.SimpleNamespace(mobile="13800000000")
        assert not ctx._is_access_gate_blocking_interaction(
            {"buttons": [{"value": "_sys_pay"}, {"value": "_sys_login"}]}
        )


class CompletionTailInteractionTests(unittest.TestCase):
    """Verify completion tail interaction behavior."""

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

        assert calls == ["next", "feedback"]
        assert events == ["next-event", "feedback-event"]

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

        assert calls == ["feedback"]
        assert events == ["feedback-event"]

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

        assert calls == ["next"]
        assert events == ["next-event"]


class RuntimeOutlineBlockCountTests(unittest.TestCase):
    """Verify runtime outline block count behavior."""

    def test_get_next_outline_item_uses_runtime_block_count_for_leaf_outline(self):
        ctx = _make_context()
        ctx.app = Flask("runtime-outline-block-count-tests")
        ctx._preview_mode = False

        class _Column:
            __hash__ = None

            def in_(self, _values):
                return self

            def __eq__(self, _other) -> "_Column":
                return self

        class _OutlineModel:
            outline_item_bid = _Column()
            hidden = _Column()
            title = _Column()
            deleted = _Column()

        class _FakeQuery:
            def filter(self, *_args: object, **_kwargs: object):
                return self

            def all(self):
                return [("outline-1", False, "Outline 1")]

        class _FakeMarkdownFlow:
            def __init__(self, *args: object, **kwargs: object) -> None:
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
            assert ctx._get_next_outline_item() == []

        assert get_outline_item_mock.call_args.kwargs.get("outline_item_id") == 1

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
            def __init__(self, *args: object, **kwargs: object) -> None:
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

        assert run_info is not None
        assert get_outline_item_mock.call_args.kwargs.get("outline_item_id") == 42


class ExceptionGateFeedbackTests(unittest.TestCase):
    """Verify exception gate feedback behavior."""

    @classmethod
    def setUpClass(cls) -> None:
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
            events = list(self.ctx._emit_feedback_after_exception_gate())
            assert len(events) == 1
            assert events[0].type == GeneratedType.INTERACTION

    def test_skips_when_no_completed_progress(self):
        with self.app.app_context():
            events = list(self.ctx._emit_feedback_after_exception_gate())
            assert events == []

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
            events = list(self.ctx._emit_feedback_after_exception_gate())
            assert events == []


class ExceptionGateInteractionPersistenceTests(unittest.TestCase):
    """Verify exception gate interaction persistence behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = Flask("exception-gate-interaction-persistence")
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
        self.ctx._current_attend = None
        with self.app.app_context():
            LearnGeneratedBlock.query.delete()
            LearnProgressRecord.query.delete()
            dao.db.session.commit()

    def test_emits_gate_interaction_without_existing_progress(self):
        with self.app.app_context():
            events = list(
                self.ctx._emit_current_progress_gate_interaction(
                    "?[server.order.checkout//_sys_pay]"
                )
            )

            progress = LearnProgressRecord.query.one()
            block = LearnGeneratedBlock.query.one()

        assert len(events) == 1
        assert progress.status == LEARN_STATUS_NOT_STARTED
        assert block.progress_record_bid == progress.progress_record_bid
        assert block.outline_item_bid == "outline-locked"
        assert block.block_content_conf == "?[server.order.checkout//_sys_pay]"


class StreamTtsGateTests(unittest.TestCase):
    """Verify stream TTS gate behavior."""

    def test_should_stream_tts_respects_preview_and_listen(self):
        ctx = _make_context()

        ctx._input_type = "normal"
        ctx._preview_mode = False
        ctx._listen = True
        assert ctx._should_stream_tts()

        ctx._listen = False
        assert not ctx._should_stream_tts()

        ctx._preview_mode = True
        ctx._listen = True
        assert not ctx._should_stream_tts()

        ctx._preview_mode = False
        ctx._input_type = "ask"
        assert not ctx._should_stream_tts()

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

    def test_iter_stream_result_with_idle_callback_stops_and_cleans_up(self):
        app = Flask("stream-tts-stop")
        ctx = _make_context()
        ctx.app = app
        stop_event = threading.Event()
        ctx._stop_event = stop_event
        remove_calls: list[str] = []

        class ClosableStream:
            def __init__(self) -> None:
                self.close_calls = 0
                self._yielded_first = False
                self.second_next_started = threading.Event()
                self.release_second = threading.Event()

            def __iter__(self) -> "ClosableStream":
                return self

            def __next__(self) -> str:
                if not self._yielded_first:
                    self._yielded_first = True
                    return "chunk-1"
                self.second_next_started.set()
                if not self.release_second.wait(timeout=1.0):
                    raise StopIteration
                return "chunk-2"

            def close(self):
                self.close_calls += 1

        stream = ClosableStream()
        fake_db = types.SimpleNamespace(
            session=types.SimpleNamespace(remove=lambda: remove_calls.append("remove"))
        )

        with patch.object(context_v2_module, "db", fake_db):
            iterator = ctx._iter_stream_result_with_idle_callback(
                stream,
                idle_poll_interval=0.01,
            )

            assert next(iterator) == ("item", "chunk-1")
            assert stream.second_next_started.wait(timeout=1.0)

            stop_event.set()
            stream.release_second.set()
            with pytest.raises(GeneratorExit):
                next(iterator)

        assert stream.close_calls == 1
        assert remove_calls == ["remove"]


class ReloadFromElementBidTests(unittest.TestCase):
    """Verify reload from element bid behavior."""

    @classmethod
    def setUpClass(cls) -> None:
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

            assert progress.block_position == 2
            assert progress.status == LEARN_STATUS_IN_PROGRESS
            assert interaction_block.status == 1
            assert later_block.status == 0
            assert later_element is not None
            assert later_element.status == 0

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

            assert target_block.status == 0
            assert later_block.status == 0
            assert ask_block.status == 1
            assert answer_block.status == 1


class StreamTtsTeardownTests(unittest.TestCase):
    """Verify stream TTS teardown behavior."""

    def test_teardown_flushes_content_then_finalizes_tts(self):
        app = Flask("stream-tts-teardown")
        ctx = _make_context()
        ctx.app = app
        ctx._element_index_cursor = 2

        class _FakeProcessor:
            next_element_index = 5

            def __init__(self) -> None:
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

        assert events == ["content-flush", "audio-complete"]
        assert flush_calls == ["flush"]
        assert processor.finalize_calls == [False]
        assert ctx._element_index_cursor == 5

    def test_teardown_skips_emit_on_generator_exit(self):
        app = Flask("stream-tts-teardown-generator-exit")
        ctx = _make_context()
        ctx.app = app
        ctx._element_index_cursor = 1

        class _FakeProcessor:
            next_element_index = 9

            def __init__(self) -> None:
                self.finalize_calls = 0

            def finalize(self, *, commit=True):
                _ = commit
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

        assert events == []
        assert flush_calls == []
        assert processor.finalize_calls == 0
        assert ctx._element_index_cursor == 1


class MdflowContextCompatibilityTests(unittest.TestCase):
    """Verify MarkdownFlow context compatibility behavior."""

    def test_init_ignores_visual_mode_when_api_missing(self):
        class FakeMarkdownFlow:
            def __init__(self, *args: object, **kwargs: object) -> None:
                self.args = args
                self.kwargs = kwargs

            def set_output_language(self, *_args: object, **_kwargs: object):
                return self

        with patch("flaskr.service.learn.context_v2.MarkdownFlow", FakeMarkdownFlow):
            context = MdflowContextV2(document="doc", visual_mode=False)

        assert isinstance(context._mdflow, FakeMarkdownFlow)

    def test_init_calls_visual_mode_when_api_exists(self):
        class FakeMarkdownFlow:
            def __init__(self, *args: object, **kwargs: object) -> None:
                _ = (args, kwargs)
                self.visual_mode = None

            def set_visual_mode(self, visual_mode):
                self.visual_mode = visual_mode

            def set_output_language(self, *_args: object, **_kwargs: object):
                return self

        with patch("flaskr.service.learn.context_v2.MarkdownFlow", FakeMarkdownFlow):
            context = MdflowContextV2(document="doc", visual_mode=False)

        assert not context._mdflow.visual_mode

    def test_init_uses_explicit_output_language_when_enabled(self):
        class FakeMarkdownFlow:
            def __init__(self, *args: object, **kwargs: object) -> None:
                _ = (args, kwargs)
                self.output_language = None

            def set_output_language(self, language):
                self.output_language = language
                return self

        with (
            patch("flaskr.service.learn.context_v2.MarkdownFlow", FakeMarkdownFlow),
            patch(
                "flaskr.service.learn.context_v2.get_markdownflow_output_language",
                return_value="English",
            ),
        ):
            context = MdflowContextV2(
                document="doc",
                use_learner_language=True,
                output_language="zh-CN",
            )

        assert context._mdflow.output_language == "简体中文"

    def test_filter_context_removes_stale_english_output_instruction(self):
        context = [
            {
                "role": "user",
                "content": "<output_language_instruction>\nOUTPUT: 100% English\n</output_language_instruction>",
            },
            {"role": "assistant", "content": "English answer"},
            {"role": "user", "content": "中文问题"},
        ]

        filtered = MdflowContextV2.filter_context_by_output_language(
            context,
            "zh-CN",
        )

        assert filtered == context[1:]


class RuntimeOutputLanguageTests(unittest.TestCase):
    """Verify runtime output language behavior."""

    def test_runtime_language_overrides_stale_profile_language(self):
        with patch(
            "flaskr.service.learn.context_v2.get_current_language",
            return_value="zh-CN",
        ):
            output_language = _resolve_runtime_output_language(
                {"sys_user_language": "en-US", "language": "en-US"}
            )

        assert output_language == "zh-CN"

    def test_runtime_language_overlays_stale_production_prompt_variables(self):
        stored_profile = {
            "sys_user_language": "zh-CN",
            "language": "zh-CN",
            "sys_user_nickname": "Learner",
        }

        with patch(
            "flaskr.service.learn.context_v2.get_current_language",
            return_value="fr-FR",
        ):
            runtime_profile, output_language = _resolve_runtime_language_context(
                stored_profile,
                use_learner_language=True,
            )

        assert output_language == "fr-FR"
        assert runtime_profile["sys_user_language"] == "fr-FR"
        assert runtime_profile["language"] == "fr-FR"
        assert runtime_profile["sys_user_nickname"] == "Learner"
        assert stored_profile["sys_user_language"] == "zh-CN"
        assert stored_profile["language"] == "zh-CN"

    def test_runtime_language_keeps_profile_variables_when_feature_is_disabled(self):
        stored_profile = {
            "sys_user_language": "zh-CN",
            "language": "zh-CN",
        }

        with patch(
            "flaskr.service.learn.context_v2.get_current_language",
            return_value="fr-FR",
        ):
            runtime_profile, output_language = _resolve_runtime_language_context(
                stored_profile,
                use_learner_language=False,
            )

        assert output_language == "fr-FR"
        assert runtime_profile == stored_profile
        assert runtime_profile is not stored_profile


class PreviewResolveLlmSettingsTests(unittest.TestCase):
    """Verify preview resolve LLM settings behavior."""

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

        assert model == "ark/deepseek-v3-2"
        assert temperature == 0.3


class PreviewResolveVariablesTests(unittest.TestCase):
    """Verify preview resolve variables behavior."""

    def test_injects_request_language_when_missing(self):
        app = Flask("preview-variables")
        preview_ctx = RunScriptPreviewContextV2(app)
        preview_request = PlaygroundPreviewRequest(block_index=0)

        with (
            patch(
                "flaskr.service.learn.context_v2.get_user_profiles",
                return_value={"sys_user_nickname": "017"},
            ) as mock_fetch,
            patch(
                "flaskr.service.learn.context_v2.get_current_language",
                return_value="zh-CN",
            ),
        ):
            variables = preview_ctx._resolve_preview_variables(
                preview_request=preview_request,
                user_bid="user-1",
                shifu_bid="shifu-1",
            )

        assert variables.get("sys_user_language") == "zh-CN"
        assert variables.get("language") == "zh-CN"
        assert variables.get("sys_user_nickname") == "017"
        mock_fetch.assert_called_once_with(app, "user-1", "shifu-1")

    def test_empty_sys_user_language_uses_request_language(self):
        app = Flask("preview-variables-empty-language")
        preview_ctx = RunScriptPreviewContextV2(app)
        preview_request = PlaygroundPreviewRequest(
            block_index=0,
            variables={"sys_user_language": "", "language": ""},
        )

        with (
            patch(
                "flaskr.service.learn.context_v2.get_user_profiles",
                return_value={"sys_user_language": "en-US", "language": "en-US"},
            ),
            patch(
                "flaskr.service.learn.context_v2.get_current_language",
                return_value="zh-CN",
            ),
        ):
            variables = preview_ctx._resolve_preview_variables(
                preview_request=preview_request,
                user_bid="user-1",
                shifu_bid="shifu-1",
            )

        assert variables.get("sys_user_language") == "zh-CN"
        assert variables.get("language") == "zh-CN"

    def test_request_language_overrides_stale_profile_language(self):
        app = Flask("preview-variables-request-language")
        preview_ctx = RunScriptPreviewContextV2(app)
        preview_request = PlaygroundPreviewRequest(
            block_index=0,
            variables={"sys_user_language": "en-US", "language": "zh-CN"},
        )

        with patch(
            "flaskr.service.learn.context_v2.get_user_profiles",
            return_value={"sys_user_language": "en-US", "language": "en-US"},
        ):
            variables = preview_ctx._resolve_preview_variables(
                preview_request=preview_request,
                user_bid="user-1",
                shifu_bid="shifu-1",
            )

        assert variables.get("sys_user_language") == "zh-CN"
        assert variables.get("language") == "zh-CN"

    def test_keeps_existing_sys_user_language(self):
        app = Flask("preview-variables-existing")
        preview_ctx = RunScriptPreviewContextV2(app)
        preview_request = PlaygroundPreviewRequest(
            block_index=0,
            variables={"sys_user_language": "fr-FR", "language": "fr-FR"},
        )

        with patch(
            "flaskr.service.learn.context_v2.get_user_profiles",
            return_value={"sys_user_nickname": "017"},
        ) as mock_fetch:
            variables = preview_ctx._resolve_preview_variables(
                preview_request=preview_request,
                user_bid="user-1",
                shifu_bid="shifu-1",
            )

        assert variables.get("sys_user_language") == "fr-FR"
        assert variables.get("language") == "fr-FR"
        mock_fetch.assert_called_once_with(app, "user-1", "shifu-1")


class CoursePromptCompositionTests(unittest.TestCase):
    """Verify course prompt composition behavior."""

    def assert_composed_course_prompt(
        self,
        prompt: str | None,
        *,
        course_prompt: str,
        learner_profile: str,
    ) -> None:
        assert prompt is not None
        assert prompt is not None
        composition_index = prompt.index("<composition_contract>")
        course_index = prompt.index("<course_prompt>")
        learner_profile_opening_tag = '<learner_profile format="json-string">'
        profile_index = prompt.index(learner_profile_opening_tag)
        assert composition_index < course_index
        assert course_index < profile_index
        assert f"<course_prompt>\n{course_prompt}\n</course_prompt>" in prompt
        assert (
            f'{learner_profile_opening_tag}\n"{learner_profile}"\n</learner_profile>'
            in prompt
        )
        assert prompt.count(LEARNER_PROFILE_PROMPT_MARKER) == 1

    def test_runtime_getter_returns_course_prompt_with_current_learner_profile(self):
        app = Flask("runtime-course-prompt-profile")
        ctx = _make_context()
        ctx.app = app
        ctx._struct = object()
        ctx._user_info = types.SimpleNamespace(learner_profile="称呼我小雨，偏好图解")

        outline_model = MagicMock()
        outline_model.query.filter.return_value.all.return_value = [
            types.SimpleNamespace(
                id="outline-db-1",
                llm_system_prompt="COURSE RULE",
            )
        ]
        ctx._outline_model = outline_model
        ctx._shifu_model = MagicMock()

        with patch(
            "flaskr.service.learn.context_v2._find_outline_path_or_raise",
            return_value=[types.SimpleNamespace(id="outline-db-1", type="outline")],
        ):
            prompt = ctx.get_system_prompt("outline-1")

        self.assert_composed_course_prompt(
            prompt,
            course_prompt="COURSE RULE",
            learner_profile="称呼我小雨，偏好图解",
        )
        ctx._shifu_model.query.filter.assert_not_called()

    def test_formal_preview_composes_request_prompt_with_current_learner(self):
        app = Flask("preview-course-prompt-profile")
        preview_ctx = RunScriptPreviewContextV2(app)
        preview_request = PlaygroundPreviewRequest(
            block_index=0,
            document_prompt="PREVIEW COURSE RULE",
        )
        learner = types.SimpleNamespace(learner_profile="最近关注知识管理")

        with patch.object(
            preview_ctx,
            "_load_learner_for_course_prompt",
            return_value=learner,
        ) as mock_load:
            prompt = preview_ctx._resolve_document_prompt(
                preview_request,
                outline=None,
                shifu=types.SimpleNamespace(llm_system_prompt="FALLBACK RULE"),
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
            )

        self.assert_composed_course_prompt(
            prompt,
            course_prompt="PREVIEW COURSE RULE",
            learner_profile="最近关注知识管理",
        )
        assert prompt is not None
        assert "FALLBACK RULE" not in prompt
        mock_load.assert_called_once_with("user-1")

    def test_formal_preview_uses_current_explicit_nickname_without_profile_text(self):
        app = Flask("preview-course-prompt-nickname")
        preview_ctx = RunScriptPreviewContextV2(app)
        preview_request = PlaygroundPreviewRequest(
            block_index=0,
            document_prompt="PREVIEW COURSE RULE",
        )

        with patch.object(
            preview_ctx,
            "_load_learner_for_course_prompt",
            return_value=types.SimpleNamespace(
                learner_profile="",
                nickname="Current Learner",
                user_bid="user-1",
                user_identify="user-1",
            ),
        ):
            prompt = preview_ctx._resolve_document_prompt(
                preview_request,
                outline=None,
                shifu=None,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
            )

        assert prompt is not None
        encoded_context = prompt.split('<learner_profile format="json-string">\n', 1)[
            1
        ].split("\n</learner_profile>", 1)[0]
        assert (
            json.loads(encoded_context)
            == 'Preferred form of address (learner-authored): "Current Learner"'
        )

    def test_formal_preview_reloads_profile_for_each_request(self):
        app = Flask("preview-course-prompt-profile-refresh")
        preview_ctx = RunScriptPreviewContextV2(app)
        preview_request = PlaygroundPreviewRequest(
            block_index=0,
            document_prompt="PREVIEW COURSE RULE",
        )

        with patch.object(
            preview_ctx,
            "_load_learner_for_course_prompt",
            side_effect=[
                types.SimpleNamespace(learner_profile="偏好图解"),
                types.SimpleNamespace(learner_profile=""),
            ],
        ) as mock_load:
            personalized_prompt = preview_ctx._resolve_document_prompt(
                preview_request,
                outline=None,
                shifu=None,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
            )
            cleared_prompt = preview_ctx._resolve_document_prompt(
                preview_request,
                outline=None,
                shifu=None,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
            )

        self.assert_composed_course_prompt(
            personalized_prompt,
            course_prompt="PREVIEW COURSE RULE",
            learner_profile="偏好图解",
        )
        assert cleared_prompt == "PREVIEW COURSE RULE"
        assert mock_load.call_args_list == [call("user-1"), call("user-1")]

    def test_formal_preview_recomposes_client_envelope_for_current_learner(self):
        app = Flask("preview-course-prompt-current-account")
        preview_ctx = RunScriptPreviewContextV2(app)
        prompt_for_previous_account = build_course_prompt(
            "PREVIEW COURSE RULE",
            learner=types.SimpleNamespace(learner_profile="PREVIOUS ACCOUNT PROFILE"),
        )
        preview_request = PlaygroundPreviewRequest(
            block_index=0,
            document_prompt=prompt_for_previous_account,
        )

        with patch.object(
            preview_ctx,
            "_load_learner_for_course_prompt",
            side_effect=[
                types.SimpleNamespace(learner_profile="CURRENT ACCOUNT PROFILE"),
                types.SimpleNamespace(learner_profile=""),
            ],
        ):
            current_prompt = preview_ctx._resolve_document_prompt(
                preview_request,
                outline=None,
                shifu=None,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="current-user",
            )
            cleared_prompt = preview_ctx._resolve_document_prompt(
                preview_request,
                outline=None,
                shifu=None,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="current-user",
            )

        self.assert_composed_course_prompt(
            current_prompt,
            course_prompt="PREVIEW COURSE RULE",
            learner_profile="CURRENT ACCOUNT PROFILE",
        )
        assert current_prompt is not None
        assert "PREVIOUS ACCOUNT PROFILE" not in current_prompt
        assert cleared_prompt == "PREVIEW COURSE RULE"

    def test_preview_learner_lookup_failure_cleans_the_database_session(self):
        app = Flask("preview-course-prompt-lookup-failure")
        preview_ctx = RunScriptPreviewContextV2(app)
        lookup_error = RuntimeError("database unavailable")

        with (
            patch(
                "flaskr.service.learn.context_v2.load_user_aggregate",
                side_effect=lookup_error,
            ),
            patch(
                "flaskr.service.learn.context_v2.cleanup_session_after"
            ) as mock_cleanup,
        ):
            learner = preview_ctx._load_learner_for_course_prompt("user-1")

        assert learner is None
        mock_cleanup.assert_called_once_with(
            lookup_error,
            source="preview learner profile lookup",
            session=context_v2_module.db.session,
        )


class PreviewRunLlmLoggingTests(unittest.TestCase):
    """Verify preview run LLM logging behavior."""

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

        assert output == "First line\nSecond line"
        assert captured["parent_observation"] is parent_observation
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
    """Verify langfuse trace finalization behavior."""

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

        assert captured["client"] is sentinel_client
        assert captured["trace_payload"]["id"] == "req-trace-1"

    def test_set_input_normalizes_structured_value_for_trace(self):
        ctx = _make_context()
        ctx._trace_args = {}

        ctx.set_input({"lang": ["Python", "Go"], "level": ["Beginner"]}, "select")

        assert ctx._trace_args["input"] == "Python, Go, Beginner"
        assert ctx._trace_args["input_type"] == "select"

    def test_set_input_normalizes_python_literal_string_for_trace(self):
        ctx = _make_context()
        ctx._trace_args = {}

        ctx.set_input("{'lang': ['Python', 'Go']}", "select")

        assert ctx._trace_args["input"] == "Python, Go"

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

        assert ctx._trace.updated == {
            "user_id": "user-1",
            "session_id": "session-1",
            "name": "lesson_runtime/trace/Outline",
        }
        assert ctx._trace_root_span.end_kwargs == {}

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

        assert ctx._trace.updated["output"] == "chunk-1chunk-2"
        assert ctx._trace_root_span.end_kwargs == {
            "input": "student input",
            "output": "chunk-1chunk-2",
        }

    def test_append_langfuse_output_normalizes_python_literal_string(self):
        ctx = _make_context()
        ctx._langfuse_output_chunks = []

        ctx.append_langfuse_output("['part-1', 'part-2']")

        assert ctx._langfuse_output_chunks == ['["part-1", "part-2"]']


class PreviewLangfuseTraceTests(unittest.TestCase):
    """Verify preview langfuse trace behavior."""

    def test_stream_preview_sets_session_id_and_finalizes_root_span(self):
        app = Flask("preview-langfuse-trace")
        preview_ctx = RunScriptPreviewContextV2(app)
        preview_request = PlaygroundPreviewRequest(block_index=0)
        captured = {}

        class _FakePreviewContextStore:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                pass

            def get_context(self, *_args: object, **_kwargs: object):
                return []

            def replace_context(self, *_args: object, **_kwargs: object):
                return None

        class _FakePreviewMdflowContext:
            def __init__(self, *args: object, **kwargs: object) -> None:
                _ = args, kwargs

            @staticmethod
            def normalize_context_messages(_value) -> None:
                return None

            @staticmethod
            def filter_context_by_output_language(context, _output_language) -> object:
                return context

            def get_block(self, _block_index):
                return types.SimpleNamespace(
                    block_type=PreviewBlockType.CONTENT, content="Prompt block"
                )

            def process(self, **_kwargs: object):
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
            def __init__(self, *_args: object, **_kwargs: object) -> None:
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

        assert messages
        assert captured["trace_payload"]["id"] == "preview-req-trace-1"
        assert captured["trace_payload"]["session_id"] == "preview-session-1"
        assert captured["trace"].updated["input"] == "Prompt block"
        assert captured["trace"].updated["output"] == "Hello preview"
        assert captured["root_span"].end_kwargs == {
            "input": "Prompt block",
            "output": "Hello preview",
        }


class PreviewElementizationTests(unittest.TestCase):
    """Verify preview elementization behavior."""

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

        assert len(events) == 1
        assert events[0].type == GeneratedType.CONTENT
        assert events[0].get_mdflow_stream_parts() == [("Hello preview", "text", 0)]

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
        assert len(element_messages) >= 2
        assert content_chunks == ["Hello preview"]
        assert element_messages[0].content.element_type == ElementType.TEXT
        assert not element_messages[0].content.is_final
        assert element_messages[-1].content.element_type == ElementType.TEXT
        assert element_messages[-1].content.is_final
        done_messages = [
            item for item in messages if item.type == GeneratedType.DONE.value
        ]
        assert len(done_messages) == 2
        assert not done_messages[0].is_terminal
        assert messages[-1].type == GeneratedType.DONE.value
        assert messages[-1].is_terminal

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
        assert len(element_messages) >= 2
        assert content_chunks == ["Visual caption"]
        assert element_messages[0].content.content_text == "Visual caption"
        done_messages = [
            item for item in messages if item.type == GeneratedType.DONE.value
        ]
        assert len(done_messages) == 2
        assert not done_messages[0].is_terminal
        assert messages[-1].type == GeneratedType.DONE.value
        assert messages[-1].is_terminal

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
        assert len(element_messages) >= 2
        assert content_chunks == ["Validation error"]
        assert element_messages[0].content.content_text == "Validation error"
        done_messages = [
            item for item in messages if item.type == GeneratedType.DONE.value
        ]
        assert len(done_messages) == 2
        assert not done_messages[0].is_terminal
        assert messages[-1].type == GeneratedType.DONE.value
        assert messages[-1].is_terminal

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
        assert len(element_messages) == 1
        interaction = element_messages[0].content
        assert interaction.element_type == ElementType.INTERACTION
        assert interaction.role == "ui"
        assert interaction.content_text == "Please choose one"
        assert content_chunks == []
        assert langfuse_output_chunks == ["Please choose one"]
        done_messages = [
            item for item in messages if item.type == GeneratedType.DONE.value
        ]
        assert len(done_messages) == 2
        assert not done_messages[0].is_terminal
        assert messages[-1].type == GeneratedType.DONE.value
        assert messages[-1].is_terminal


class _InMemoryCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str):
        return self.store.get(key)

    def setex(self, key: str, _ttl: int, value):
        self.store[key] = value

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                removed += 1
        return removed


def _make_preview_store(
    doc: str = "doc",
) -> tuple[_PreviewContextStore, _InMemoryCache, str]:
    app = Flask("preview-context-store")
    store = _PreviewContextStore(app, "user-1", "shifu-1", "outline-1")
    cache = _InMemoryCache()
    store._cache = cache
    return store, cache, doc


class PreviewSentPromptCaptureTests(unittest.TestCase):
    """The preview flow stores the exact user message markdown-flow sent to the LLM (LLMResult.prompt) instead of a locally re-rendered block, so the replayed preview context stays byte-identical to the sent request."""

    def test_iter_preview_generated_events_captures_prompt(self):
        app = Flask("preview-prompt-capture")
        preview_ctx = RunScriptPreviewContextV2(app)
        sent_prompt_chunks: list[str] = []

        list(
            preview_ctx._iter_preview_generated_events(
                result=(
                    chunk
                    for chunk in [
                        LLMResult(
                            content="Hello preview",
                            type="text",
                            number=0,
                            prompt="P-PREVIEW",
                        )
                    ]
                ),
                outline_bid="outline-1",
                block_index=0,
                current_block=types.SimpleNamespace(block_type="content"),
                is_user_input_validation=False,
                content_chunks=[],
                langfuse_output_chunks=[],
                sent_prompt_chunks=sent_prompt_chunks,
            )
        )

        assert sent_prompt_chunks == ["P-PREVIEW"]

    def test_update_preview_context_prefers_sent_prompt(self):
        app = Flask("preview-prompt-store")
        preview_ctx = RunScriptPreviewContextV2(app)
        appended: list[tuple] = []
        store = types.SimpleNamespace(
            append_context=lambda *args: appended.append(args)
        )
        request = PlaygroundPreviewRequest(block_index=0)

        preview_ctx._update_preview_context(
            store,
            "doc",
            request,
            ["generated "],
            "re-rendered block",
            sent_prompt="P-PREVIEW",
        )
        preview_ctx._update_preview_context(
            store,
            "doc",
            request,
            ["generated "],
            "re-rendered block",
        )

        assert appended[0][2] == "P-PREVIEW"
        # Without a captured prompt the legacy rendering still applies.
        assert appended[1][2] == "re-rendered block"


class PreviewContextStoreTruncationTests(unittest.TestCase):
    """Verify preview context store truncation behavior."""

    def _populate(self, store, doc, indices):
        for idx in indices:
            store.append_context(doc, idx, f"u{idx}", f"a{idx}")

    def test_sequential_blocks_accumulate(self):
        store, _cache, doc = _make_preview_store()
        self._populate(store, doc, [0, 1, 2, 3])
        messages = store.get_context(doc, 4)
        assert messages == [
            {"role": "user", "content": "u0"},
            {"role": "assistant", "content": "a0"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "u3"},
            {"role": "assistant", "content": "a3"},
        ]

    def test_reselect_drops_entries_at_or_above_block_index(self):
        store, _cache, doc = _make_preview_store()
        self._populate(store, doc, [0, 1, 2, 3])
        messages = store.get_context(doc, 2)
        assert messages == [
            {"role": "user", "content": "u0"},
            {"role": "assistant", "content": "a0"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
        ]
        persisted = store.load()
        assert [entry["block_index"] for entry in persisted["entries"]] == [0, 1]

    def test_repeated_reselect_does_not_grow(self):
        store, _cache, doc = _make_preview_store()
        self._populate(store, doc, [0, 1, 2, 3])
        for _ in range(5):
            store.get_context(doc, 2)
            store.append_context(doc, 2, "u-new", "a-new")
        persisted = store.load()
        index_counts: dict[int, int] = {}
        for entry in persisted["entries"]:
            index_counts[entry["block_index"]] = (
                index_counts.get(entry["block_index"], 0) + 1
            )
        assert index_counts.get(2) == 1
        assert index_counts.get(0) == 1
        assert index_counts.get(1) == 1

    def test_backtrack_to_earlier_block(self):
        store, _cache, doc = _make_preview_store()
        self._populate(store, doc, [0, 1, 2, 3])
        messages = store.get_context(doc, 1)
        assert messages == [
            {"role": "user", "content": "u0"},
            {"role": "assistant", "content": "a0"},
        ]
        persisted = store.load()
        assert [entry["block_index"] for entry in persisted["entries"]] == [0]

    def test_block_index_zero_clears(self):
        store, cache, doc = _make_preview_store()
        self._populate(store, doc, [0, 1, 2])
        assert store.get_context(doc, 0) == []
        assert cache.store == {}

    def test_document_hash_change_clears(self):
        store, cache, _doc = _make_preview_store(doc="doc-A")
        self._populate(store, "doc-A", [0, 1, 2])
        assert store.get_context("doc-B", 3) == []
        assert cache.store == {}

    def test_legacy_flat_schema_clears(self):
        store, cache, doc = _make_preview_store()
        store.save(
            {
                "document_hash": store._hash_document(doc),
                "context": [
                    {"role": "user", "content": "legacy-u"},
                    {"role": "assistant", "content": "legacy-a"},
                ],
            }
        )
        assert store.get_context(doc, 3) == []
        assert cache.store == {}

    def test_append_skips_when_both_empty(self):
        store, cache, doc = _make_preview_store()
        store.append_context(doc, 2, None, None)
        assert cache.store == {}

    def test_append_user_only_and_assistant_only(self):
        store, _cache, doc = _make_preview_store()
        store.append_context(doc, 1, "user-only", None)
        store.append_context(doc, 2, None, "assistant-only")
        messages = store.get_context(doc, 3)
        assert messages == [
            {"role": "user", "content": "user-only"},
            {"role": "assistant", "content": "assistant-only"},
        ]

    def test_missing_document_hash_clears_entries(self):
        store, cache, doc = _make_preview_store()
        store.save(
            {"entries": [{"block_index": 1, "user": "stale", "assistant": "stale"}]}
        )
        assert store.get_context(doc, 3) == []
        assert cache.store == {}

    def test_empty_document_hash_clears_entries(self):
        store, cache, doc = _make_preview_store()
        store.save(
            {
                "document_hash": "",
                "entries": [{"block_index": 1, "user": "stale", "assistant": "stale"}],
            }
        )
        assert store.get_context(doc, 3) == []
        assert cache.store == {}

    def test_replace_context_pairs_messages_with_sentinel_index(self):
        store, _cache, doc = _make_preview_store()
        store.replace_context(
            doc,
            [
                {"role": "user", "content": "ctx-u-0"},
                {"role": "assistant", "content": "ctx-a-0"},
                {"role": "user", "content": "ctx-u-1"},
            ],
        )
        persisted = store.load()
        assert all(entry["block_index"] < 0 for entry in persisted["entries"])
        # A real block_index request should preserve all sentinel entries.
        messages = store.get_context(doc, 5)
        assert messages == [
            {"role": "user", "content": "ctx-u-0"},
            {"role": "assistant", "content": "ctx-a-0"},
            {"role": "user", "content": "ctx-u-1"},
        ]


class RuntimeExceptionLangfuseTests(unittest.TestCase):
    """Verify runtime exception langfuse behavior."""

    def test_run_emits_gate_interaction_after_paid_exception(self):
        app = Flask("runtime-langfuse-paid")
        ctx = _make_context()

        def _raise_paid(_app):
            raise PaidError

        ctx.run_inner = _raise_paid
        ctx._emit_feedback_after_exception_gate = lambda: iter(["feedback"])
        ctx._emit_current_progress_gate_interaction = lambda content: iter([content])

        with patch("flaskr.service.learn.context_v2._", lambda key: key):
            outputs = list(ctx.run(app))

        assert outputs == ["?[server.order.checkout//_sys_pay]", "feedback"]


class BuildContextFromBlocksTests(unittest.TestCase):
    """build_context_from_blocks should hand interaction blocks to markdown-flow as raw ?[...] assistant messages so its _transform_context_messages can expand them, instead of dropping them or flattening input into a bare user message."""

    DOC = (
        "Content one.\n"
        "---\n"
        "?[%{{nickname}} ...What is your name?]\n"
        "---\n"
        "Second content {{nickname}}."
    )

    def _blocks(self):
        return [
            types.SimpleNamespace(
                type=BLOCK_TYPE_MDCONTENT_VALUE,
                position=0,
                generated_content="reply zero",
            ),
            types.SimpleNamespace(
                type=BLOCK_TYPE_MDINTERACTION_VALUE,
                position=1,
                generated_content="Alice",
            ),
            types.SimpleNamespace(
                type=BLOCK_TYPE_MDCONTENT_VALUE,
                position=2,
                generated_content="reply two",
            ),
        ]

    def test_interaction_block_kept_as_raw_assistant_message(self):
        app = Flask(__name__)
        with app.app_context():
            messages = MdflowContextV2.build_context_from_blocks(
                self._blocks(), self.DOC, {"nickname": "Alice"}
            )

        # The interaction block survives as a raw ?[...] assistant message.
        interaction_msgs = [
            m for m in messages if m["role"] == "assistant" and "?[" in m["content"]
        ]
        assert len(interaction_msgs) == 1
        assert "%{{nickname}}" in interaction_msgs[0]["content"]

    def test_transform_expands_interaction_without_adjacent_users(self):
        app = Flask(__name__)
        with app.app_context():
            messages = MdflowContextV2.build_context_from_blocks(
                self._blocks(), self.DOC, {"nickname": "Alice"}
            )

        # Feed the assembled context through markdown-flow's native transform,
        # exactly as the content-generation path does.
        from markdown_flow import MarkdownFlow

        mf = MarkdownFlow(self.DOC, llm_provider=None)
        transformed = mf._transform_context_messages(messages, {"nickname": "Alice"})

        # Interaction answer becomes user(value)+assistant("ok").
        assert {"role": "user", "content": "Alice"} in transformed
        # No raw interaction syntax leaks after transform.
        assert all("?[" not in m["content"] for m in transformed)
        # Roles strictly alternate: no two adjacent user messages.
        roles = [m["role"] for m in transformed]
        for prev, cur in itertools.pairwise(roles):
            assert not (prev == "user" and cur == "user"), (
                f"adjacent user messages in {roles}"
            )


class BuildContextGenerationPromptReplayTests(unittest.TestCase):
    """Content blocks replay the persisted generation_prompt verbatim so the rebuilt history stays byte-identical to the request previously sent to the LLM (keeping provider-side prefix caching effective); legacy rows without it fall back to re-rendering the block source with the current variables."""

    DOC = (
        "Content one {{nickname}}.\n"
        "---\n"
        "?[%{{nickname}} ...What is your name?]\n"
        "---\n"
        "Second content."
    )

    STORED_PROMPT = (
        'Content one """UNKNOWN""".\n\n'
        "The next interaction will appear immediately after this content."
    )

    def test_stored_prompt_replayed_verbatim_ignoring_current_variables(self):
        blocks = [
            types.SimpleNamespace(
                type=BLOCK_TYPE_MDCONTENT_VALUE,
                position=0,
                generated_content="reply zero",
                generation_prompt=self.STORED_PROMPT,
            ),
        ]
        app = Flask(__name__)
        with app.app_context():
            messages = MdflowContextV2.build_context_from_blocks(
                blocks, self.DOC, {"nickname": "Alice"}
            )

        # The stored prompt wins even though nickname now resolves to Alice.
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == self.STORED_PROMPT

    def test_missing_or_empty_prompt_falls_back_to_current_rendering(self):
        blocks = [
            # Legacy row persisted before the column existed.
            types.SimpleNamespace(
                type=BLOCK_TYPE_MDCONTENT_VALUE,
                position=0,
                generated_content="reply zero",
            ),
            # Row persisted with an empty prompt.
            types.SimpleNamespace(
                type=BLOCK_TYPE_MDCONTENT_VALUE,
                position=2,
                generated_content="reply two",
                generation_prompt="",
            ),
        ]
        app = Flask(__name__)
        with app.app_context():
            messages = MdflowContextV2.build_context_from_blocks(
                blocks, self.DOC, {"nickname": "Alice"}
            )

        user_messages = [m for m in messages if m["role"] == "user"]
        assert len(user_messages) == 2
        assert "Alice" in user_messages[0]["content"]
        assert user_messages[1]["content"] == "Second content."


class StreamContentBlockPromptCaptureTests(unittest.TestCase):
    """_phase_stream_content_block captures LLMResult.prompt (the exact user message markdown-flow sent to the LLM) and hands it to the recorder; prompt-less streams (preserved content) freeze the variables-rendered block source instead."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = Flask("stream-prompt-capture-tests")
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

    def _run_stream_phase(self, stream_items):
        ctx = _make_context()
        ctx.app = self.app
        ctx._input_type = "normal"
        ctx._preview_mode = False
        ctx._listen = False
        ctx._current_attend = types.SimpleNamespace(
            progress_record_bid="progress-prompt-1",
            shifu_bid="shifu-prompt-1",
        )
        # _recorder is a lazy read-only property backed by __dict__.
        ctx.__dict__["_run_recorder"] = MagicMock()

        def fake_stream():
            yield from stream_items

        mdflow_context = types.SimpleNamespace(process=lambda **_kwargs: fake_stream())
        attend = types.SimpleNamespace(shifu_bid="shifu-prompt-1")
        state = types.SimpleNamespace(
            run_script_info=types.SimpleNamespace(
                attend=attend,
                outline_bid="outline-prompt-1",
                block_position=0,
                mdflow="",
            ),
            block_list=[object(), object()],
            user_profile={"nickname": "Alice"},
            message_list=[],
            llm_provider=MagicMock(),
            mdflow_context=mdflow_context,
            block=types.SimpleNamespace(content="Preserved {{nickname}} text."),
        )
        generated_block = LearnGeneratedBlock(
            generated_block_bid="gb-prompt-capture-1",
            progress_record_bid="progress-prompt-1",
            user_bid="user-prompt-1",
            outline_item_bid="outline-prompt-1",
            shifu_bid="shifu-prompt-1",
            position=0,
            generated_content="",
            block_content_conf="",
            status=1,
        )
        with self.app.app_context():
            events = list(
                ctx._phase_stream_content_block(self.app, state, generated_block)
            )
            dao.db.session.rollback()
        return ctx, events

    def test_llm_prompt_captured_and_passed_to_finalize(self):
        ctx, _events = self._run_stream_phase(
            [
                LLMResult(content="Hello ", type="text", number=0, prompt="P-EXACT"),
                LLMResult(content="world", type="text", number=0, prompt="P-EXACT"),
            ]
        )
        finalize_call = ctx._recorder.finalize_streamed_block.call_args
        assert finalize_call.kwargs["generation_prompt"] == "P-EXACT"
        assert finalize_call.args[1] == "Hello world"

    def test_promptless_stream_falls_back_to_rendered_block_source(self):
        ctx, _events = self._run_stream_phase(
            [LLMResult(content="Preserved Alice text.", type="text", number=0)]
        )
        finalize_call = ctx._recorder.finalize_streamed_block.call_args
        assert (
            finalize_call.kwargs["generation_prompt"] == 'Preserved """Alice""" text.'
        )


class BuildContextNoVariableInteractionTests(unittest.TestCase):
    """No-variable interactions carry a real learner answer with no variable to recover it from.

    build_context_from_blocks attaches the answer stored in generated_content to the
    interaction message via the user_answer extension field (markdown-flow >= 0.3.0); the
    library then expands it into {user: answer} + {assistant: "ok"}, or skips the turn when
    the answer is empty.
    """

    DOC = (
        "Content one.\n"
        "---\n"
        "?[网络招聘网站 | 猎头公司 | 人才测评 | 培训业务]\n"
        "---\n"
        "Second content."
    )
    INTERACTION = "?[网络招聘网站 | 猎头公司 | 人才测评 | 培训业务]"

    def _blocks(self, selection):
        return [
            types.SimpleNamespace(
                type=BLOCK_TYPE_MDCONTENT_VALUE,
                position=0,
                generated_content="reply zero",
            ),
            types.SimpleNamespace(
                type=BLOCK_TYPE_MDINTERACTION_VALUE,
                position=1,
                generated_content=selection,
            ),
        ]

    def test_selection_attached_via_user_answer_field(self):
        app = Flask(__name__)
        with app.app_context():
            messages = MdflowContextV2.build_context_from_blocks(
                self._blocks("猎头公司"), self.DOC, {}
            )

        assert messages == [
            {"role": "user", "content": "Content one."},
            {"role": "assistant", "content": "reply zero"},
            {
                "role": "assistant",
                "content": self.INTERACTION,
                USER_ANSWER_CONTEXT_KEY: "猎头公司",
            },
        ]

    def test_empty_selection_carries_empty_user_answer(self):
        app = Flask(__name__)
        with app.app_context():
            messages = MdflowContextV2.build_context_from_blocks(
                self._blocks("   "), self.DOC, {}
            )

        # The empty answer travels with the message; the library skips the
        # turn instead of fabricating a {user: "ok"} pair.
        assert messages[-1] == {
            "role": "assistant",
            "content": self.INTERACTION,
            USER_ANSWER_CONTEXT_KEY: "",
        }

    def test_library_expands_answer_and_skips_empty_turns(self):
        """End-to-end: the context built here goes through markdown-flow's message transform and comes out with the real answer, no raw ?[...] syntax, and no fabricated "ok" for unanswered interactions."""
        app = Flask(__name__)
        with app.app_context():
            answered = MdflowContextV2.build_context_from_blocks(
                self._blocks("猎头公司"), self.DOC, {}
            )
            unanswered = MdflowContextV2.build_context_from_blocks(
                self._blocks(""), self.DOC, {}
            )

        mdflow = MarkdownFlow(self.DOC)
        transformed = mdflow._transform_context_messages(answered, {})
        assert transformed == [
            {"role": "user", "content": "Content one."},
            {"role": "assistant", "content": "reply zero"},
            {"role": "user", "content": "猎头公司"},
            {"role": "assistant", "content": "ok"},
        ]
        assert all("?[" not in m["content"] for m in transformed)
        assert all(USER_ANSWER_CONTEXT_KEY not in m for m in transformed), (
            "extension fields must never reach the LLM"
        )

        transformed_empty = mdflow._transform_context_messages(unanswered, {})
        assert transformed_empty == [
            {"role": "user", "content": "Content one."},
            {"role": "assistant", "content": "reply zero"},
        ]

    def test_variable_free_text_input_carries_the_learner_answer(self):
        document = "Content one.\n---\n?[...What is your name?]\n---\nSecond content."
        app = Flask(__name__)
        with app.app_context():
            messages = MdflowContextV2.build_context_from_blocks(
                self._blocks("Alice"), document, {}
            )

        assert messages[-1] == {
            "role": "assistant",
            "content": "?[...What is your name?]",
            USER_ANSWER_CONTEXT_KEY: "Alice",
        }
        transformed = MarkdownFlow(document)._transform_context_messages(messages, {})
        assert {"role": "user", "content": "Alice"} in transformed
        assert all("?[" not in m["content"] for m in transformed)


class TraceSessionBindingTests(unittest.TestCase):
    """Cover the langfuse session id binding of a runtime step."""

    def _context(self, trace):
        ctx = _make_context()
        ctx.app = MagicMock()
        ctx._trace = trace
        ctx._trace_id = "f" * 32
        ctx._trace_args = {"user_id": "user-1", "metadata": {"scene": "lesson_runtime"}}
        ctx._trace_root_span = None
        ctx._current_attend = MagicMock(progress_record_bid="progress-1")
        ctx._outline_item_info = MagicMock(bid="outline-1", shifu_bid="shifu-1")
        return ctx

    def test_binding_pushes_the_session_id_to_langfuse_immediately(self):
        # The SDK carries trace attributes on every observation, so a session id
        # that only reaches langfuse at finalize time would be missing from all
        # observations of the step.
        trace = _FakeLangfuseTrace()
        ctx = self._context(trace)

        ctx._bind_trace_session()

        assert ctx._trace_args["session_id"] == "progress-1"
        assert trace.updated == {"session_id": "progress-1"}

    def test_binding_without_a_trace_does_not_raise(self):
        ctx = self._context(None)

        ctx._bind_trace_session()

        assert ctx._trace_args["session_id"] == "progress-1"


if __name__ == "__main__":
    unittest.main()

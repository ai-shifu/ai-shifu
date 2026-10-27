"""Cover where a lesson request goes: every lesson turn to 2.0, a follow-up to `learn.ask`."""

from __future__ import annotations

import logging
import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING, NoReturn
from unittest.mock import Mock

import pytest
from flask import has_app_context
from flaskr.service.learn import runscript_v2
from flaskr.service.learn.const import INPUT_TYPE_ASK
from flaskr.service.learn.learn_dtos import RunElementSSEMessageDTO

from . import test_runscript_v2_lock as stream_helpers

if TYPE_CHECKING:
    from collections.abc import Iterator

SHIFU = "shifu-a"
OTHER = "shifu-b"


@pytest.fixture(autouse=True)
def _no_real_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for the commit checkpoint the agent path ends with: there is no database here."""
    from flaskr.common.config import Config

    monkeypatch.setattr(runscript_v2, "_commit_pending_step", lambda: None)
    monkeypatch.setattr(
        runscript_v2, "_ensure_healthy_db_connection", lambda _app: None
    )
    monkeypatch.setattr(Config, "_instance", None)
    monkeypatch.delenv("FLOW_ENGINE_V2_ENABLED", raising=False)


def _routes_to_agent(**kwargs: object) -> bool:
    defaults = {
        "shifu_bid": SHIFU,
        "input_type": None,
        "reload_generated_block_bid": None,
        "reload_element_bid": None,
    }
    return runscript_v2._teaches_with_agent(**{**defaults, **kwargs})


def test_a_lesson_is_taught_with_the_agent_engine() -> None:
    assert _routes_to_agent() is True


def test_another_course_also_uses_the_agent_engine() -> None:
    assert _routes_to_agent(shifu_bid=OTHER) is True


@pytest.mark.parametrize("flag", ["false", "0", ""])
def test_the_retired_flag_no_longer_keeps_a_course_on_1_0(
    monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    monkeypatch.setenv("FLOW_ENGINE_V2_ENABLED", flag)
    assert _routes_to_agent(shifu_bid=SHIFU) is True
    assert _routes_to_agent(shifu_bid=OTHER) is True


def test_a_follow_up_question_is_not_a_lesson_turn() -> None:
    """Ask runs beside the lesson under its own semaphore, not through the turn loop."""
    assert _routes_to_agent(input_type=INPUT_TYPE_ASK) is False


@pytest.mark.parametrize("listen", [False, True], ids=["read", "listen"])
@pytest.mark.parametrize("preview", [False, True], ids=["formal", "preview"])
@pytest.mark.parametrize("anchored", [False, True], ids=["unanchored", "anchored"])
def test_follow_up_dispatch_preserves_the_sidecar_request(
    monkeypatch: pytest.MonkeyPatch,
    listen: bool,
    preview: bool,
    anchored: bool,
) -> None:
    """Ask must bypass agent turns and retain its request and emitted events."""
    from flaskr.service.learn.agent import lesson_entry

    app = SimpleNamespace(logger=logging.getLogger(__name__))
    stop_event = threading.Event()
    adapter = SimpleNamespace(persist_only_final=False)
    question = "Explain the earlier answer.\nKeep its exact wording."
    block_bid = "selected-block" if anchored else None
    element_bid = "selected-element" if anchored else None
    seen = []
    response = [object(), object()]

    def follow_up(**kwargs: object) -> Iterator[object]:
        seen.append(kwargs)
        yield from response

    def refuse_agent(*_args: object, **_kwargs: object) -> NoReturn:
        pytest.fail("A follow-up must not enter the teaching agent turn loop")

    monkeypatch.setattr(runscript_v2, "_follow_up_events", follow_up)
    monkeypatch.setattr(lesson_entry, "agent_lesson_events", refuse_agent)
    commits = []
    monkeypatch.setattr(
        runscript_v2, "_commit_pending_step", lambda: commits.append(True)
    )

    events = list(
        runscript_v2._lesson_events(
            app=app,
            user_bid="learner-bid",
            shifu_bid=SHIFU,
            outline_bid="lesson-bid",
            user_input=question,
            input_type=INPUT_TYPE_ASK,
            reload_generated_block_bid=block_bid,
            reload_element_bid=element_bid,
            listen=listen,
            learning_mode="listen" if listen else "read",
            preview_mode=preview,
            stop_event=stop_event,
            element_adapter=adapter,
            heartbeat_interval=0.5,
        )
    )

    assert events == response
    assert seen == [
        {
            "app": app,
            "user_bid": "learner-bid",
            "outline_bid": "lesson-bid",
            "user_input": question,
            "reload_generated_block_bid": block_bid,
            "reload_element_bid": element_bid,
            "listen": listen,
            "learning_mode": "listen" if listen else "read",
            "preview_mode": preview,
            "stop_event": stop_event,
            "element_adapter": adapter,
        }
    ]
    assert seen[0]["app"] is app
    assert seen[0]["stop_event"] is stop_event
    assert seen[0]["element_adapter"] is adapter
    assert adapter.persist_only_final is False
    assert commits == []


@pytest.mark.parametrize("listen", [False, True], ids=["read", "listen"])
@pytest.mark.parametrize("preview", [False, True], ids=["formal", "preview"])
def test_follow_up_producer_normalizes_listen_before_sidecar_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    listen: bool,
    preview: bool,
) -> None:
    """Real Ask producers suppress lesson TTS and keep their separate semaphore."""
    from flaskr.service.learn.agent import lesson_entry

    app = stream_helpers._make_test_app()
    lock = stream_helpers.FakeLock([True])
    cache = stream_helpers.FakeCacheProvider(lock)
    lesson_key = runscript_v2._get_run_script_status_key(app, "learner", "lesson")
    cache.setex(lesson_key, 60, "active-lesson")
    monkeypatch.setattr(runscript_v2, "cache_provider", cache)
    acquire = Mock(return_value=True)
    release = Mock()
    monkeypatch.setattr(runscript_v2, "_ask_sem_acquire", acquire)
    monkeypatch.setattr(runscript_v2, "_ask_sem_release", release)
    remove = Mock()
    monkeypatch.setattr(runscript_v2, "_remove_db_session_safely", remove)
    agent = Mock(side_effect=AssertionError("Ask entered the teaching agent"))
    monkeypatch.setattr(lesson_entry, "agent_lesson_events", agent)
    adapters = []

    def make_adapter(*args: object, **kwargs: object) -> object:
        adapter = stream_helpers.FakeListenElementAdapter(*args, **kwargs)
        adapter.persist_only_final = kwargs["persist_only_final"]
        adapters.append(adapter)
        return adapter

    monkeypatch.setattr(runscript_v2, "ListenElementRunAdapter", make_adapter)
    seen = []

    def follow_up(**kwargs: object) -> Iterator[RunElementSSEMessageDTO]:
        seen.append((kwargs, has_app_context()))
        yield RunElementSSEMessageDTO(
            type="element", event_type="element", content="Sidecar answer"
        )

    monkeypatch.setattr(runscript_v2, "_follow_up_events", follow_up)
    events = stream_helpers._parse_sse_events(
        list(
            runscript_v2.run_script(
                app=app,
                shifu_bid=SHIFU,
                outline_bid="lesson",
                user_bid="learner",
                user_input="Explain my answer.",
                input_type=INPUT_TYPE_ASK,
                reload_generated_block_bid="selected-block",
                reload_element_bid="selected-element",
                listen=listen,
                learning_mode="listen" if listen else "read",
                preview_mode=preview,
            )
        )
    )

    assert len(seen) == 1
    kwargs, producer_has_context = seen[0]
    assert producer_has_context is True
    assert kwargs["listen"] is False
    assert kwargs["learning_mode"] == ("listen" if listen else "read")
    assert kwargs["preview_mode"] is preview
    assert kwargs["user_input"] == "Explain my answer."
    assert kwargs["reload_generated_block_bid"] == "selected-block"
    assert kwargs["reload_element_bid"] == "selected-element"
    assert len(adapters) == 1
    assert kwargs["element_adapter"] is adapters[0]
    assert adapters[0].persist_only_final is False
    assert [event["type"] for event in events] == ["element", "done"]
    assert events[0]["content"] == "Sidecar answer"
    assert events[-1]["is_terminal"] is True
    agent.assert_not_called()
    acquire.assert_called_once_with(app, "learner", "lesson")
    release.assert_called_once_with(app, "learner", "lesson")
    assert lock.acquire_calls == lock.release_calls == 0
    assert cache.get(lesson_key) == b"active-lesson"
    remove.assert_called_once_with(app, source="run_script producer")


@pytest.mark.parametrize("learning_mode", ["read", "listen", "classroom"])
def test_a_listening_learner_is_also_taught_by_the_agent_engine(
    monkeypatch: pytest.MonkeyPatch,
    learning_mode: str,
) -> None:
    """Listening is about how a lesson is delivered, not about who teaches it.

    What the engine teaches is spoken by the same pipeline that speaks a 1.0 lesson, so a listening
    request no longer stays behind -- and `listen` reaches the agent path rather than the routing
    decision.
    """
    from flaskr.service.learn.agent import lesson_entry

    seen: dict = {}

    def _agent(_app: object, **kwargs: object) -> list:
        seen.update(kwargs)
        return []

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", _agent)

    class _App:
        import logging

        logger = logging.getLogger("test_lesson_routing")

    list(
        runscript_v2._lesson_events(
            app=_App(),
            user_bid="user-bid",
            shifu_bid=SHIFU,
            outline_bid="outline-bid",
            user_input=None,
            input_type=None,
            reload_generated_block_bid=None,
            reload_element_bid=None,
            listen=learning_mode == "listen",
            learning_mode=learning_mode,
            preview_mode=False,
            stop_event=None,
            element_adapter=None,
            heartbeat_interval=0.5,
        )
    )

    assert seen["listen"] is (learning_mode == "listen")
    assert seen["learning_mode"] == learning_mode


@pytest.mark.parametrize(
    "reload_kwargs",
    [
        pytest.param({"reload_generated_block_bid": "block-bid"}, id="block"),
        pytest.param({"reload_element_bid": "element-bid"}, id="element"),
    ],
)
def test_regenerating_past_content_stays_with_the_agent_engine(
    reload_kwargs: dict,
) -> None:
    """Going back is the agent's own to do.

    Sent to the script engine, a reload regenerated from rows the agent wrote and left the agent's
    session where it was, so the page and the lesson disagreed from then on.
    """
    assert _routes_to_agent(**reload_kwargs) is True


def test_a_lesson_with_no_script_is_completed_rather_than_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty lesson ends as 1.0 ended it: complete, with the next lesson offered."""
    from flaskr.service.learn.agent import lesson_entry

    def _no_script(*_args: object, **_kwargs: object) -> None:
        raise lesson_entry.LessonNotTeachable

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", _no_script)
    completed: list[dict] = []
    marker = object()

    def _complete(_app: object, **kwargs: object) -> Iterator[object]:
        completed.append(kwargs)
        yield marker

    monkeypatch.setattr(lesson_entry, "complete_empty_lesson", _complete)
    steps: list[str] = []
    monkeypatch.setattr(
        runscript_v2,
        "_ensure_healthy_db_connection",
        lambda _app: steps.append("probe"),
    )
    monkeypatch.setattr(
        runscript_v2, "_commit_pending_step", lambda: steps.append("commit")
    )

    def _adapt(events: Iterator[object]) -> Iterator[object]:
        for event in events:
            steps.append("adapted")
            yield event

    class _App:
        logger = logging.getLogger("test_lesson_routing")

    events = list(
        runscript_v2._lesson_events(
            app=_App(),
            user_bid="user-bid",
            shifu_bid=SHIFU,
            outline_bid="outline-bid",
            user_input=None,
            input_type=None,
            reload_generated_block_bid=None,
            reload_element_bid=None,
            listen=False,
            learning_mode="read",
            preview_mode=False,
            stop_event=None,
            element_adapter=SimpleNamespace(persist_only_final=True, process=_adapt),
            heartbeat_interval=0.5,
        )
    )
    assert events == [marker]
    # The connection is checked before any lesson read, and what the adapter staged for the
    # next-lesson button is committed before the stream ends.
    assert steps == ["probe", "adapted", "commit"]
    assert completed == [
        {
            "user_bid": "user-bid",
            "shifu_bid": SHIFU,
            "outline_bid": "outline-bid",
            "preview_mode": False,
        }
    ]


def test_going_back_in_a_lesson_with_no_script_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lesson with no script has no turn to take the learner back to."""
    from flaskr.service.common.models import AppError
    from flaskr.service.learn.agent import lesson_entry

    def _no_script(*_args: object, **_kwargs: object) -> None:
        raise lesson_entry.LessonNotTeachable

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", _no_script)
    completed: list[bool] = []
    monkeypatch.setattr(
        lesson_entry,
        "complete_empty_lesson",
        lambda *_a, **_kw: completed.append(True) or iter(()),
    )

    class _App:
        import logging

        logger = logging.getLogger("test_lesson_routing")

    class _Adapter:
        persist_only_final = True

    with pytest.raises(AppError):
        list(
            runscript_v2._lesson_events(
                app=_App(),
                user_bid="user-bid",
                shifu_bid=SHIFU,
                outline_bid="outline-bid",
                user_input={"way": ["Right"]},
                input_type=None,
                reload_generated_block_bid="block-bid",
                reload_element_bid=None,
                listen=False,
                learning_mode="read",
                preview_mode=False,
                stop_event=None,
                element_adapter=_Adapter(),
                heartbeat_interval=0.5,
            )
        )
    assert completed == []


def test_a_busy_worker_tells_the_learner_to_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stream shows an AppError's own message and renders anything else as "unknown error".

    A learner told the system is busy can act on it; a learner told nothing cannot.
    """
    from flaskr.service.common.models import AppError
    from flaskr.service.learn.agent import lesson_entry
    from markdownflow.bridge import TurnCapacityError

    def _at_capacity(*_args: object, **_kwargs: object) -> None:
        raise TurnCapacityError

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", _at_capacity)

    class _App:
        import logging

        logger = logging.getLogger("test_lesson_routing")

    with pytest.raises(AppError):
        list(
            runscript_v2._lesson_events(
                app=_App(),
                user_bid="user-bid",
                shifu_bid=SHIFU,
                outline_bid="outline-bid",
                user_input=None,
                input_type=None,
                reload_generated_block_bid=None,
                reload_element_bid=None,
                listen=False,
                learning_mode="read",
                preview_mode=False,
                stop_event=None,
                element_adapter=None,
                heartbeat_interval=0.5,
            )
        )


def test_the_input_the_browser_sends_reaches_the_agent_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every lesson input is a map, so routing must forward it rather than flatten it away."""
    from flaskr.service.learn.agent import lesson_entry

    seen: dict = {}

    def _agent(_app: object, **kwargs: object) -> list:
        seen.update(kwargs)
        return []

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", _agent)

    class _App:
        import logging

        logger = logging.getLogger("test_lesson_routing")

    sent = {"feeling": ["Good"]}
    list(
        runscript_v2._lesson_events(
            app=_App(),
            user_bid="user-bid",
            shifu_bid=SHIFU,
            outline_bid="outline-bid",
            user_input=sent,
            input_type=None,
            reload_generated_block_bid=None,
            reload_element_bid=None,
            listen=False,
            learning_mode="read",
            preview_mode=False,
            stop_event=None,
            element_adapter=None,
            heartbeat_interval=0.5,
        )
    )
    assert seen["user_input"] == sent


def test_the_agent_path_makes_what_the_adapter_staged_durable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adapter finalises the block after the turn's last event, outside the turn's transaction.

    The 1.0 run ends with a commit checkpoint for exactly that; the 2.0 path did not, and every
    element written at finalisation -- a lesson's cards among them -- was dropped with the session.
    """
    from flaskr.service.learn.agent import lesson_entry

    monkeypatch.setattr(
        lesson_entry, "agent_lesson_events", lambda *_a, **_k: iter(["event"])
    )
    committed: list[bool] = []
    monkeypatch.setattr(
        runscript_v2, "_commit_pending_step", lambda: committed.append(True)
    )

    class _App:
        import logging

        logger = logging.getLogger("test_lesson_routing")

    events = list(
        runscript_v2._lesson_events(
            app=_App(),
            user_bid="user-bid",
            shifu_bid=SHIFU,
            outline_bid="outline-bid",
            user_input=None,
            input_type=None,
            reload_generated_block_bid=None,
            reload_element_bid=None,
            listen=False,
            learning_mode="read",
            preview_mode=False,
            stop_event=None,
            element_adapter=None,
            heartbeat_interval=0.5,
        )
    )

    assert events == ["event"]
    assert committed == [True]

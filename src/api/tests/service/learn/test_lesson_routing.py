"""Cover which engine a lesson request goes to.

The case that matters most is the boring one: with 2.0 disabled, every request takes the 1.0 path.
That is what every deployment except the simulation environment runs, so it is asserted from
several directions rather than once.
"""

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
    monkeypatch.setattr(Config, "_instance", None)
    monkeypatch.delenv("FLOW_ENGINE_V2_ENABLED", raising=False)


@pytest.fixture
def enabled_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable every course through the real deployment configuration path."""
    monkeypatch.setenv("FLOW_ENGINE_V2_ENABLED", "true")


def _routes_to_agent(**kwargs: object) -> bool:
    defaults = {
        "shifu_bid": SHIFU,
        "input_type": None,
        "reload_generated_block_bid": None,
        "reload_element_bid": None,
    }
    return runscript_v2._teaches_with_agent(**{**defaults, **kwargs})


@pytest.mark.usefixtures("enabled_deployment")
def test_an_enabled_deployment_teaches_with_the_agent_engine() -> None:
    assert _routes_to_agent() is True


@pytest.mark.usefixtures("enabled_deployment")
def test_another_course_also_uses_the_agent_engine() -> None:
    assert _routes_to_agent(shifu_bid=OTHER) is True


def test_with_disabled_deployment_every_course_stays_on_the_script_engine() -> None:
    """Production sets nothing, so this is the path production takes."""
    assert _routes_to_agent(shifu_bid=SHIFU) is False
    assert _routes_to_agent(shifu_bid=OTHER) is False


@pytest.mark.usefixtures("enabled_deployment")
def test_a_follow_up_question_keeps_the_script_engine() -> None:
    """Ask runs beside the lesson under its own semaphore, not through the turn loop."""
    assert _routes_to_agent(input_type=INPUT_TYPE_ASK) is False


@pytest.mark.parametrize("enabled", [False, True], ids=["v1", "v2"])
@pytest.mark.parametrize("listen", [False, True], ids=["read", "listen"])
@pytest.mark.parametrize("preview", [False, True], ids=["formal", "preview"])
@pytest.mark.parametrize("anchored", [False, True], ids=["unanchored", "anchored"])
def test_follow_up_dispatch_preserves_the_sidecar_request(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    listen: bool,
    preview: bool,
    anchored: bool,
) -> None:
    """Ask must bypass agent turns and retain its request and emitted events."""
    from flaskr.service.learn.agent import lesson_entry

    monkeypatch.setenv("FLOW_ENGINE_V2_ENABLED", str(enabled).lower())
    app = SimpleNamespace(logger=logging.getLogger(__name__))
    stop_event = threading.Event()
    adapter = SimpleNamespace(persist_only_final=False)
    question = "Explain the earlier answer.\nKeep its exact wording."
    block_bid = "selected-block" if anchored else None
    element_bid = "selected-element" if anchored else None
    seen = []
    response = [object(), object()]

    def script_engine(**kwargs: object) -> Iterator[object]:
        seen.append(kwargs)
        yield from response

    def refuse_agent(*_args: object, **_kwargs: object) -> NoReturn:
        pytest.fail("A follow-up must not enter the teaching agent turn loop")

    monkeypatch.setattr(runscript_v2, "run_script_inner", script_engine)
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
            "shifu_bid": SHIFU,
            "outline_bid": "lesson-bid",
            "user_input": question,
            "input_type": INPUT_TYPE_ASK,
            "reload_generated_block_bid": block_bid,
            "reload_element_bid": element_bid,
            "listen": listen,
            "learning_mode": "listen" if listen else "read",
            "preview_mode": preview,
            "stop_event": stop_event,
            "element_adapter": adapter,
            "manage_app_context": False,
        }
    ]
    assert seen[0]["app"] is app
    assert seen[0]["stop_event"] is stop_event
    assert seen[0]["element_adapter"] is adapter
    assert adapter.persist_only_final is False
    assert commits == []


@pytest.mark.parametrize("enabled", [False, True], ids=["v1", "v2"])
@pytest.mark.parametrize("listen", [False, True], ids=["read", "listen"])
@pytest.mark.parametrize("preview", [False, True], ids=["formal", "preview"])
def test_follow_up_producer_normalizes_listen_before_sidecar_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    listen: bool,
    preview: bool,
) -> None:
    """Real Ask producers suppress lesson TTS and keep their separate semaphore."""
    from flaskr.service.learn.agent import lesson_entry

    monkeypatch.setenv("FLOW_ENGINE_V2_ENABLED", str(enabled).lower())
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

    def script_engine(**kwargs: object) -> Iterator[RunElementSSEMessageDTO]:
        seen.append((kwargs, has_app_context()))
        yield RunElementSSEMessageDTO(
            type="element", event_type="element", content="Sidecar answer"
        )

    monkeypatch.setattr(runscript_v2, "run_script_inner", script_engine)
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
    assert kwargs["input_type"] == INPUT_TYPE_ASK
    assert kwargs["user_input"] == "Explain my answer."
    assert kwargs["reload_generated_block_bid"] == "selected-block"
    assert kwargs["reload_element_bid"] == "selected-element"
    assert kwargs["manage_app_context"] is False
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


@pytest.mark.usefixtures("enabled_deployment")
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


@pytest.mark.usefixtures("enabled_deployment")
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


@pytest.mark.usefixtures("enabled_deployment")
def test_a_lesson_with_no_script_falls_back_rather_than_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configuration mistake should not refuse the learner: 1.0 knows what to do with it."""
    from flaskr.service.learn.agent import lesson_entry

    def _no_script(*_args: object, **_kwargs: object) -> None:
        raise lesson_entry.LessonNotTeachable

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", _no_script)

    fell_back: list[bool] = []

    def _script_engine(**_kwargs: object) -> list:
        fell_back.append(True)
        return []

    monkeypatch.setattr(runscript_v2, "run_script_inner", _script_engine)

    class _App:
        import logging

        logger = logging.getLogger("test_lesson_routing")

    class _Adapter:
        persist_only_final = True

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
            element_adapter=_Adapter(),
            heartbeat_interval=0.5,
        )
    )
    assert fell_back == [True]


@pytest.mark.usefixtures("enabled_deployment")
def test_going_back_in_a_lesson_with_no_script_is_refused_rather_than_sent_to_1_0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1.0 would rewrite history and leave the lesson's 2.0 session on its old branch."""
    from flaskr.service.common.models import AppError
    from flaskr.service.learn.agent import lesson_entry

    def _no_script(*_args: object, **_kwargs: object) -> None:
        raise lesson_entry.LessonNotTeachable

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", _no_script)
    fell_back: list[bool] = []
    monkeypatch.setattr(
        runscript_v2, "run_script_inner", lambda **_kw: fell_back.append(True) or []
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
    assert fell_back == []


def test_the_script_engine_is_reached_with_what_it_expects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Routing must not quietly drop arguments the 1.0 path relies on."""
    monkeypatch.setattr(runscript_v2, "uses_agent_engine", lambda _bid: False)
    seen: dict = {}

    def _script_engine(**kwargs: object) -> list:
        seen.update(kwargs)
        return []

    monkeypatch.setattr(runscript_v2, "run_script_inner", _script_engine)

    sentinel_adapter = object()
    sentinel_stop = object()
    list(
        runscript_v2._lesson_events(
            app=None,
            user_bid="user-bid",
            shifu_bid=SHIFU,
            outline_bid="outline-bid",
            user_input="hello",
            input_type=None,
            reload_generated_block_bid=None,
            reload_element_bid=None,
            listen=True,
            learning_mode="listen",
            preview_mode=True,
            stop_event=sentinel_stop,
            element_adapter=sentinel_adapter,
            heartbeat_interval=0.5,
        )
    )
    assert seen["listen"] is True
    assert seen["learning_mode"] == "listen"
    assert seen["preview_mode"] is True
    assert seen["user_input"] == "hello"
    assert seen["element_adapter"] is sentinel_adapter
    assert seen["stop_event"] is sentinel_stop
    # The producer thread owns the app context; the inner run must not take it as well.
    assert seen["manage_app_context"] is False


def test_a_busy_worker_tells_the_learner_to_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stream shows an AppError's own message and renders anything else as "unknown error".

    A learner told the system is busy can act on it; a learner told nothing cannot.
    """
    from flaskr.service.common.models import AppError
    from flaskr.service.learn.agent import lesson_entry
    from flaskr.service.learn.agent.bridge import TurnCapacityError

    monkeypatch.setattr(runscript_v2, "uses_agent_engine", lambda _bid: True)

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


@pytest.mark.usefixtures("enabled_deployment")
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


@pytest.mark.usefixtures("enabled_deployment")
def test_falling_back_to_the_script_engine_restores_per_update_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adapter is built for the agent engine and shared with the fallback path.

    1.0 relies on every update being written — a learner refreshing mid-stream reads the latest
    row — so a fallback that kept the agent's write-once mode would change 1.0's behaviour.
    """
    from flaskr.service.learn.agent import lesson_entry

    def _no_script(*_args: object, **_kwargs: object) -> None:
        raise lesson_entry.LessonNotTeachable

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", _no_script)
    monkeypatch.setattr(runscript_v2, "run_script_inner", lambda **_kwargs: [])

    class _Adapter:
        persist_only_final = True

    class _App:
        import logging

        logger = logging.getLogger("test_lesson_routing")

    adapter = _Adapter()
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
            element_adapter=adapter,
            heartbeat_interval=0.5,
        )
    )

    assert adapter.persist_only_final is False


@pytest.mark.usefixtures("enabled_deployment")
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

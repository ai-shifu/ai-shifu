"""Cover which engine a lesson request goes to.

The case that matters most is the boring one: with no allowlist, every request takes the 1.0 path.
That is what every deployment except the simulation environment runs, so it is asserted from
several directions rather than once.
"""

from __future__ import annotations

import pytest
from flaskr.service.learn import runscript_v2
from flaskr.service.learn.const import INPUT_TYPE_ASK

SHIFU = "shifu-on-the-list"
OTHER = "shifu-not-on-the-list"


@pytest.fixture(autouse=True)
def _no_real_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The agent path ends with a commit checkpoint; these tests run without a database."""
    monkeypatch.setattr(runscript_v2, "_commit_pending_step", lambda: None)


@pytest.fixture
def allowlisted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put one course on the 2.0 allowlist, as a deployment's environment would."""
    monkeypatch.setattr(
        runscript_v2, "uses_agent_engine", lambda shifu_bid: shifu_bid == SHIFU
    )


def _routes_to_agent(**kwargs: object) -> bool:
    defaults = {
        "shifu_bid": SHIFU,
        "input_type": None,
        "reload_generated_block_bid": None,
        "reload_element_bid": None,
    }
    return runscript_v2._teaches_with_agent(**{**defaults, **kwargs})


@pytest.mark.usefixtures("allowlisted")
def test_an_allowlisted_course_is_taught_by_the_agent_engine() -> None:
    assert _routes_to_agent() is True


@pytest.mark.usefixtures("allowlisted")
def test_a_course_not_on_the_list_stays_on_the_script_engine() -> None:
    assert _routes_to_agent(shifu_bid=OTHER) is False


def test_with_no_allowlist_every_course_stays_on_the_script_engine() -> None:
    """Production sets nothing, so this is the path production takes."""
    assert _routes_to_agent(shifu_bid=SHIFU) is False
    assert _routes_to_agent(shifu_bid=OTHER) is False


@pytest.mark.usefixtures("allowlisted")
def test_a_follow_up_question_keeps_the_script_engine() -> None:
    """Ask runs beside the lesson under its own semaphore, not through the turn loop."""
    assert _routes_to_agent(input_type=INPUT_TYPE_ASK) is False


@pytest.mark.usefixtures("allowlisted")
def test_a_listening_learner_is_also_taught_by_the_agent_engine(
    monkeypatch: pytest.MonkeyPatch,
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
            listen=True,
            learning_mode="listen",
            preview_mode=False,
            stop_event=None,
            element_adapter=None,
            heartbeat_interval=0.5,
        )
    )

    assert seen["listen"] is True


@pytest.mark.usefixtures("allowlisted")
@pytest.mark.parametrize(
    "reload_kwargs",
    [
        pytest.param({"reload_generated_block_bid": "block-bid"}, id="block"),
        pytest.param({"reload_element_bid": "element-bid"}, id="element"),
    ],
)
def test_regenerating_past_content_keeps_the_script_engine(
    reload_kwargs: dict,
) -> None:
    """Those requests address rows 1.0 wrote; the agent engine has no equivalent of them."""
    assert _routes_to_agent(**reload_kwargs) is False


@pytest.mark.usefixtures("allowlisted")
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


@pytest.mark.usefixtures("allowlisted")
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


@pytest.mark.usefixtures("allowlisted")
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


@pytest.mark.usefixtures("allowlisted")
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

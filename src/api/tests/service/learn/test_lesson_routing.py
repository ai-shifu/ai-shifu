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
        "listen": False,
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
def test_a_listening_learner_keeps_the_script_engine() -> None:
    """Teaching it in read mode would answer a request for one thing with another.

    The engine's segment and narration events have nowhere to go until listen-mode mapping
    exists, so the request stays with the engine that can serve it.
    """
    assert _routes_to_agent(listen=True) is False


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

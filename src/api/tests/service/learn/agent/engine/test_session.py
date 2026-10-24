"""Session persistence: what survives a store round trip."""

from collections.abc import Callable

import pytest
from flaskr.service.learn.agent.engine import (
    InMemorySessionStore,
    InteractionSpec,
    Option,
    PendingInteraction,
    ScriptBundle,
    Session,
    SessionStore,
    SQLiteSessionStore,
)
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    "store_factory", [InMemorySessionStore, lambda: SQLiteSessionStore(":memory:")]
)
async def test_roundtrip(store_factory: Callable[[], SessionStore]) -> None:
    store = store_factory()
    s = Session(script=ScriptBundle(script="hi {{n}}"), user_id="u1", listen_mode=True)
    s.messages = [
        ModelRequest(parts=[UserPromptPart(content="x")]),
        ModelResponse(parts=[TextPart(content="y")]),
    ]
    s.memory = {"n": "Lin"}
    s.user_memory = {"pace": "slow"}
    s.pending = [
        PendingInteraction(
            "c1",
            InteractionSpec(type="single", prompt="q", options=[Option(display="A")]),
        )
    ]
    s.answers = {"c0": "Learner chose: A"}
    s.usage = {"requests": 2}
    s.turn = 3
    s.interrupted = True
    await store.save(s)
    back = await store.load(s.id)
    assert back is not None
    assert back.script == s.script
    assert back.user_id == "u1"
    assert back.listen_mode
    assert len(back.messages) == 2
    assert isinstance(back.messages[1], ModelResponse)
    assert back.memory == {"n": "Lin"}
    assert back.user_memory == {"pace": "slow"}
    assert back.pending[0].tool_call_id == "c1"
    assert back.pending[0].spec.options[0].display == "A"
    # Answers already collected for a turn survive the round trip: a lesson whose model asked two
    # questions at once is resumed across separate host requests, with the session persisted
    # between them.
    assert back.answers == {"c0": "Learner chose: A"}
    assert back.usage == {"requests": 2}
    assert back.turn == 3
    assert back.interrupted
    assert back.all_memory() == {"pace": "slow", "n": "Lin"}
    assert await store.load("nope") is None


def test_legacy_session_defaults_to_uninterrupted() -> None:
    """Existing saved sessions remain readable without the additive retry flag."""
    state = Session(script=ScriptBundle(script="Teach the next step.")).to_dict()
    state.pop("interrupted")
    assert not Session.from_dict(state).interrupted


@pytest.mark.parametrize("pending", [False, True])
def test_existing_session_results_establish_named_answer_acceptance(
    pending: bool,
) -> None:
    """Old serialized sessions need no new field to distinguish answers from seeds."""
    session = Session(
        script=ScriptBundle(script="Ask %{{goal}}."), memory={"goal": "A"}
    )
    session.messages = [
        ModelResponse(parts=[ToolCallPart("interact", {"variable": "goal"}, "q")])
    ]
    if pending:
        session.answers = {"q": "Learner wrote: A"}
    else:
        session.messages.append(
            ModelRequest(parts=[ToolReturnPart("interact", "Learner chose: A", "q")])
        )
    legacy = session.to_dict()
    legacy.pop("answer_hashes")
    restored = Session.from_dict(legacy)
    assert restored.answered_memory_keys() == {"goal"}
    assert Session.loads(restored.dumps()).answered_memory_keys() == {"goal"}
    session.memory.clear()
    assert not session.answered_memory_keys()


@pytest.mark.parametrize(
    "kind",
    ["seed", "unasked", "failed", "empty", "duplicate", "duplicate-return", "order"],
)
def test_unaccepted_session_records_never_unlock_a_named_question(kind: str) -> None:
    """Only a uniquely paired successful host answer establishes acceptance."""
    session = Session(
        script=ScriptBundle(script="Ask %{{goal}}."), memory={"goal": "A"}
    )
    call = ModelResponse(parts=[ToolCallPart("interact", {"variable": "goal"}, "q")])
    if kind != "seed":
        session.messages = [call]
        session.messages.append(
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        "interact",
                        "Learner continued without answering."
                        if kind == "unasked"
                        else "Learner wrote: "
                        if kind == "empty"
                        else "Learner wrote: A",
                        "q",
                        outcome="failed" if kind == "failed" else "success",
                    )
                ]
            )
        )
    if kind == "duplicate":
        session.messages.insert(0, call)
    elif kind == "duplicate-return":
        session.messages.append(session.messages[-1])
    elif kind == "order":
        session.messages.reverse()
    legacy = session.to_dict()
    legacy.pop("answer_hashes")
    assert not Session.from_dict(legacy).answered_memory_keys()


def test_answer_fingerprint_survives_reload_and_rejects_a_changed_copy() -> None:
    """Only the currently tracked copy can be refreshed from course storage."""
    session = Session(script=ScriptBundle(script="Ask %{{goal}}."))
    session.record_answer("goal", "Original")
    restored = Session.loads(session.dumps())
    assert restored.answered_memory_keys() == {"goal"}
    restored.memory["goal"] = "Working note"
    assert not restored.answered_memory_keys()
    restored.answer_hashes["goal"] = None
    restored.memory["goal"] = False
    assert not restored.answered_memory_keys()


@pytest.mark.parametrize(
    ("scope", "value", "current"),
    [
        ("session", "A", "A"),
        ("session", "B", "B"),
        ("user", "B", "B"),
        ("user", "B", "A"),
    ],
)
def test_legacy_remember_results_identify_the_current_answer_owner(
    scope: str, value: str, current: str
) -> None:
    """A successful session write supersedes even an identical historical answer."""
    session = Session(
        script=ScriptBundle(script="Ask %{{goal}}."), memory={"goal": current}
    )
    session.messages = [
        ModelResponse(parts=[ToolCallPart("interact", {"variable": "goal"}, "q")]),
        ModelRequest(parts=[ToolReturnPart("interact", "Learner wrote: A", "q")]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    "remember", {"key": "goal", "value": value, "scope": scope}, "n"
                )
            ]
        ),
        ModelRequest(
            parts=[ToolReturnPart("remember", f"remembered goal ({scope})", "n")]
        ),
    ]
    legacy = session.to_dict()
    legacy.pop("answer_hashes")
    restored = Session.from_dict(legacy)
    assert restored.answered_memory_keys() == ({"goal"} if scope == "user" else set())


def test_a_confirm_stored_before_the_label_mark_existed_is_still_the_engine_s() -> None:
    """A learner mid-lesson when that change ships must not get the English button back.

    Sessions written before the engine recorded who named a confirm's button carry no such
    field. A stored confirm carrying exactly the engine's own default was the engine's.
    """
    stored = {
        "id": "s1",
        "script": {"script": "lesson"},
        "pending": [
            {
                "tool_call_id": "c1",
                "spec": {
                    "type": "confirm",
                    "prompt": "",
                    "options": [{"display": "Continue", "value": "continue"}],
                },
            }
        ],
    }
    session = Session.from_dict(stored)
    assert session.pending[0].spec.labelled_by_engine is True


def test_a_confirm_stored_with_the_mark_is_believed() -> None:
    """A session written since the field existed records the answer; do not second-guess it."""
    stored = {
        "id": "s1",
        "script": {"script": "lesson"},
        "pending": [
            {
                "tool_call_id": "c1",
                "spec": {
                    "type": "confirm",
                    "prompt": "",
                    "options": [{"display": "Continue", "value": "continue"}],
                    "labelled_by_engine": False,
                },
            }
        ],
    }
    session = Session.from_dict(stored)
    assert session.pending[0].spec.labelled_by_engine is False

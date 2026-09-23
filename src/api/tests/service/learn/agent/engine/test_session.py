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
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

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
    assert back.all_memory() == {"pace": "slow", "n": "Lin"}
    assert await store.load("nope") is None


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

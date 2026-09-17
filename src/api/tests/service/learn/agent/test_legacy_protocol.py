"""Cover the translation from engine events to the events the 1.0 lesson stream speaks."""

from __future__ import annotations

import pytest
from flaskr.service.learn.agent import legacy_protocol
from flaskr.service.learn.agent.engine.events import (
    ContentDelta,
    ErrorEvent,
    InteractionRequest,
    MemoryUpdated,
    NarrationDelta,
    SegmentEnd,
    SegmentStart,
    ToolCall,
    ToolResult,
    TurnDone,
    Visual,
)
from flaskr.service.learn.agent.engine.interaction import InteractionSpec, Option
from flaskr.service.learn.learn_dtos import GeneratedType

OUTLINE = "outline-bid"
BLOCK = "block-bid"


def _translate(event: object) -> list:
    return legacy_protocol.translate(
        event, outline_bid=OUTLINE, generated_block_bid=BLOCK
    )


# --- interaction syntax ------------------------------------------------------------------


def _spec(**kwargs: object) -> InteractionSpec:
    return InteractionSpec(**kwargs)


def test_a_single_choice_renders_with_one_bar() -> None:
    rendered = legacy_protocol.render_interaction(
        _spec(
            type="single",
            prompt="Pick one",
            options=[Option(display="A"), Option(display="B")],
            variable="choice",
        )
    )
    assert rendered == "?[%{{choice}} A | B]"


def test_a_multiple_choice_renders_with_two_bars() -> None:
    """The double bar is what tells the frontend more than one answer is allowed."""
    rendered = legacy_protocol.render_interaction(
        _spec(
            type="multi",
            prompt="Pick some",
            options=[Option(display="A"), Option(display="B")],
            variable="choices",
        )
    )
    assert rendered == "?[%{{choices}} A || B]"


def test_a_choice_without_a_variable_stores_nothing() -> None:
    rendered = legacy_protocol.render_interaction(
        _spec(type="single", prompt="Pick", options=[Option(display="A")])
    )
    assert rendered == "?[A]"


def test_a_stored_value_is_kept_separate_from_the_text_the_learner_reads() -> None:
    rendered = legacy_protocol.render_interaction(
        _spec(
            type="single",
            prompt="Pick",
            options=[Option(display="Yes, please", value="yes")],
            variable="answer",
        )
    )
    assert rendered == "?[%{{answer}} Yes, please//yes]"


def test_a_value_is_written_even_when_it_equals_the_display() -> None:
    """A value equal to its display is still written out.

    Omitting it changes nothing here, but the same shortcut would silently store the display when
    the value is an empty string.
    """
    rendered = legacy_protocol.render_interaction(
        _spec(
            type="single",
            prompt="Pick",
            options=[Option(display="Yes", value="Yes")],
            variable="answer",
        )
    )
    assert rendered == "?[%{{answer}} Yes//Yes]"


def test_an_empty_stored_value_is_not_mistaken_for_an_absent_one() -> None:
    """`Option(value="")` stores the empty string; dropping it would store the display instead."""
    rendered = legacy_protocol.render_interaction(
        _spec(
            type="single",
            prompt="Pick",
            options=[Option(display="Skip", value="")],
            variable="answer",
        )
    )
    assert rendered == "?[%{{answer}} Skip//]"


def test_free_text_renders_as_a_trailing_placeholder() -> None:
    rendered = legacy_protocol.render_interaction(
        _spec(
            type="text",
            prompt="Tell me",
            variable="story",
            placeholder="Your answer",
        )
    )
    assert rendered == "?[%{{story}} ...Your answer]"


def test_a_choice_that_also_accepts_text_offers_both() -> None:
    rendered = legacy_protocol.render_interaction(
        _spec(
            type="single_or_text",
            prompt="Pick or write",
            options=[Option(display="A")],
            variable="answer",
            placeholder="Something else",
        )
    )
    assert rendered == "?[%{{answer}} A | ...Something else]"


def test_multiple_choice_with_text_keeps_the_double_bar() -> None:
    rendered = legacy_protocol.render_interaction(
        _spec(
            type="multi_or_text",
            prompt="Pick or write",
            options=[Option(display="A"), Option(display="B")],
            variable="answer",
            placeholder="Other",
        )
    )
    assert rendered == "?[%{{answer}} A || B || ...Other]"


def test_a_confirm_renders_one_button_and_stores_nothing() -> None:
    """The spec drops a confirm's variable, because pressing continue is not an answer."""
    rendered = legacy_protocol.render_interaction(
        _spec(
            type="confirm",
            prompt="Ready?",
            options=[Option(display="Continue")],
            variable="would_overwrite_a_real_answer",
        )
    )
    assert rendered == "?[Continue]"


# --- event translation -------------------------------------------------------------------


def test_lesson_text_becomes_a_content_event() -> None:
    (translated,) = _translate(ContentDelta(text="hello"))
    assert translated.type == GeneratedType.CONTENT
    assert translated.content == "hello"
    assert translated.outline_bid == OUTLINE
    assert translated.generated_block_bid == BLOCK


def test_an_empty_text_chunk_is_dropped() -> None:
    """Forwarding it would persist an element row holding nothing."""
    assert _translate(ContentDelta(text="")) == []


def test_an_interaction_arrives_as_its_question_then_its_controls() -> None:
    question, controls = _translate(
        InteractionRequest(
            id="i1",
            spec=_spec(
                type="single",
                prompt="Which one?",
                options=[Option(display="A")],
                variable="pick",
            ),
        )
    )
    assert question.type == GeneratedType.CONTENT
    assert question.content == "Which one?"
    assert controls.type == GeneratedType.INTERACTION
    assert controls.content == "?[%{{pick}} A]"


def test_an_interaction_without_a_question_sends_only_its_controls() -> None:
    (controls,) = _translate(
        InteractionRequest(
            id="i1",
            spec=_spec(type="single", prompt="   ", options=[Option(display="A")]),
        )
    )
    assert controls.type == GeneratedType.INTERACTION


def test_a_memory_write_becomes_a_variable_update() -> None:
    (translated,) = _translate(MemoryUpdated(key="name", value="Ada"))
    assert translated.type == GeneratedType.VARIABLE_UPDATE
    assert translated.content.variable_name == "name"
    assert translated.content.variable_value == "Ada"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(None, "", id="none-becomes-empty"),
        pytest.param(42, "42", id="number"),
        pytest.param(True, "True", id="boolean"),
    ],
)
def test_a_memory_value_reaches_the_frontend_as_text(
    value: object, expected: str
) -> None:
    """The 1.0 payload carries strings, so anything else has to be rendered as one."""
    (translated,) = _translate(MemoryUpdated(key="k", value=value))
    assert translated.content.variable_value == expected


def test_a_finished_lesson_closes_the_stream() -> None:
    """Only an explicit finish may use DONE: the element adapter marks it terminal."""
    (translated,) = _translate(TurnDone(reason="finished"))
    assert translated.type == GeneratedType.DONE


def test_a_turn_that_ran_out_of_content_leaves_the_lesson_resumable() -> None:
    """The model often never calls finish. DONE here would close the stream mid-lesson."""
    (translated,) = _translate(TurnDone(reason="end"))
    assert translated.type == GeneratedType.BREAK


def test_a_turn_waiting_on_the_learner_does_not_close_the_stream() -> None:
    """The interaction event already told the frontend to wait; done would let it move on."""
    assert _translate(TurnDone(reason="interaction")) == []


def test_a_failed_turn_never_reports_success() -> None:
    """The browser reads a terminal DONE as success and clears the failed flag it had set."""
    assert _translate(ErrorEvent(message="boom")) == []
    assert _translate(ErrorEvent(message="boom", retryable=True)) == []


@pytest.mark.parametrize(
    "event",
    [
        pytest.param(ToolCall(id="t1", name="interact"), id="tool-call"),
        pytest.param(ToolResult(id="t1", name="interact"), id="tool-result"),
    ],
)
def test_the_engine_talking_to_the_model_is_not_shown_to_the_learner(
    event: object,
) -> None:
    assert _translate(event) == []


@pytest.mark.parametrize(
    "event",
    [
        pytest.param(
            SegmentStart(segment_id="s1", visual=Visual(kind="html", content="<p/>")),
            id="segment-start",
        ),
        pytest.param(NarrationDelta(segment_id="s1", text="spoken"), id="narration"),
        pytest.param(SegmentEnd(segment_id="s1", narration="spoken"), id="segment-end"),
    ],
)
def test_listen_mode_events_are_left_for_the_change_that_maps_them(
    event: object,
) -> None:
    """Slides and audio need mapping of their own; dropping them here is deliberate, not missing."""
    assert _translate(event) == []


# --- round trip --------------------------------------------------------------------------
#
# Asserting the exact string only proves this module is self-consistent. These parse what it
# renders with the same library the 1.0 path uses and compare the controls a learner would get,
# so a syntax drift fails here rather than in front of a learner.


def _parse(rendered: str) -> dict:
    from markdown_flow import InteractionParser

    return InteractionParser().parse(rendered)


@pytest.mark.parametrize(
    ("spec_kwargs", "expected"),
    [
        pytest.param(
            {
                "type": "single",
                "prompt": "p",
                "options": [Option(display="A"), Option(display="B")],
                "variable": "choice",
            },
            {
                "variable": "choice",
                "buttons": [("A", "A"), ("B", "B")],
                "is_multi_select": False,
                "question": None,
            },
            id="single",
        ),
        pytest.param(
            {
                "type": "multi",
                "prompt": "p",
                "options": [Option(display="A"), Option(display="B")],
                "variable": "choices",
            },
            {
                "variable": "choices",
                "buttons": [("A", "A"), ("B", "B")],
                "is_multi_select": True,
                "question": None,
            },
            id="multi",
        ),
        pytest.param(
            {
                "type": "text",
                "prompt": "p",
                "variable": "story",
                "placeholder": "Your answer",
            },
            {
                "variable": "story",
                "buttons": [],
                "is_multi_select": False,
                "question": "Your answer",
            },
            id="free-text",
        ),
        pytest.param(
            {
                "type": "single",
                "prompt": "p",
                "options": [Option(display="Yes, please", value="yes")],
                "variable": "answer",
            },
            {
                "variable": "answer",
                "buttons": [("Yes, please", "yes")],
                "is_multi_select": False,
                "question": None,
            },
            id="display-and-value",
        ),
        pytest.param(
            {
                "type": "single_or_text",
                "prompt": "p",
                "options": [Option(display="A")],
                "variable": "answer",
                "placeholder": "Other",
            },
            {
                "variable": "answer",
                "buttons": [("A", "A")],
                "is_multi_select": False,
                "question": "Other",
            },
            id="choice-or-text",
        ),
        pytest.param(
            {"type": "confirm", "prompt": "p", "options": [Option(display="Continue")]},
            {
                "variable": None,
                "buttons": [("Continue", "Continue")],
                "is_multi_select": False,
                "question": None,
            },
            id="confirm-stores-nothing",
        ),
    ],
)
def test_the_controls_a_learner_gets_are_the_ones_the_model_asked_for(
    spec_kwargs: dict, expected: dict
) -> None:
    parsed = _parse(legacy_protocol.render_interaction(_spec(**spec_kwargs)))

    assert parsed.get("variable") == expected["variable"]
    assert [
        (b["display"], b["value"]) for b in (parsed.get("buttons") or [])
    ] == expected["buttons"]
    assert bool(parsed.get("is_multi_select")) is expected["is_multi_select"]
    if expected["question"] is not None:
        assert parsed.get("question") == expected["question"]


def test_the_stored_value_a_learner_returns_is_the_one_the_engine_will_match() -> None:
    """`normalize_answer` maps a submitted display through the spec's own option strings.

    A renderer that trimmed or dropped text would send the learner a token absent from that map,
    and a required answer would be rejected with nothing to explain it.
    """
    from flaskr.service.learn.agent.engine.interaction import (
        InteractionAnswer,
        normalize_answer,
    )

    spec = _spec(
        type="single",
        prompt="p",
        options=[Option(display="Yes, please", value="yes")],
        variable="answer",
    )
    parsed = _parse(legacy_protocol.render_interaction(spec))
    submitted = parsed["buttons"][0]["display"]

    assert normalize_answer(spec, InteractionAnswer(values=[submitted])).values == [
        "yes"
    ]


# --- what the grammar cannot carry -------------------------------------------------------


@pytest.mark.parametrize(
    ("spec_kwargs", "why"),
    [
        pytest.param(
            {
                "type": "single",
                "prompt": "p",
                "options": [Option(display="A | B")],
                "variable": "v",
            },
            "a bar splits one choice into two",
            id="bar-in-display",
        ),
        pytest.param(
            {
                "type": "single",
                "prompt": "p",
                "options": [Option(display="A//B")],
                "variable": "v",
            },
            "a double slash gives half the display away to the stored value",
            id="slashes-in-display",
        ),
        pytest.param(
            {
                "type": "single",
                "prompt": "p",
                "options": [Option(display="A]B")],
                "variable": "v",
            },
            "a bracket ends the interaction early",
            id="bracket-in-display",
        ),
        pytest.param(
            {
                "type": "single",
                "prompt": "p",
                "options": [Option(display="A...B")],
                "variable": "v",
            },
            "an ellipsis turns the rest into a text box",
            id="ellipsis-in-display",
        ),
        pytest.param(
            {
                "type": "single",
                "prompt": "p",
                "options": [Option(display=" A ")],
                "variable": "v",
            },
            "the grammar drops surrounding spaces, and the engine matches the untrimmed string",
            id="padded-display",
        ),
    ],
)
def test_an_interaction_the_grammar_would_reshape_is_refused(
    spec_kwargs: dict, why: str
) -> None:
    """Rendering it approximately gives the learner controls the engine will not accept."""
    with pytest.raises(legacy_protocol.UnrepresentableInteractionError):
        legacy_protocol.render_interaction(_spec(**spec_kwargs))
    assert why  # documents the case


def test_translating_an_unrenderable_interaction_raises_rather_than_guessing() -> None:
    """The caller decides how to degrade; silently sending broken controls is not an option."""
    with pytest.raises(legacy_protocol.UnrepresentableInteractionError):
        _translate(
            InteractionRequest(
                id="i1",
                spec=_spec(
                    type="single",
                    prompt="q",
                    options=[Option(display="A | B")],
                    variable="v",
                ),
            )
        )

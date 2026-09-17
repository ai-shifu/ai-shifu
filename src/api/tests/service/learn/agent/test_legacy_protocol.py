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


def test_a_value_identical_to_the_display_is_not_repeated() -> None:
    rendered = legacy_protocol.render_interaction(
        _spec(
            type="single",
            prompt="Pick",
            options=[Option(display="Yes", value="Yes")],
            variable="answer",
        )
    )
    assert rendered == "?[%{{answer}} Yes]"


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


@pytest.mark.parametrize("reason", ["end", "finished"])
def test_a_turn_that_ran_out_of_content_closes_the_stream(reason: str) -> None:
    (translated,) = _translate(TurnDone(reason=reason))
    assert translated.type == GeneratedType.DONE


def test_a_turn_waiting_on_the_learner_does_not_close_the_stream() -> None:
    """The interaction event already told the frontend to wait; done would let it move on."""
    assert _translate(TurnDone(reason="interaction")) == []


def test_a_failed_turn_closes_the_stream_rather_than_leaving_it_open() -> None:
    """1.0 has no error event, and a frontend left waiting never recovers on its own."""
    (translated,) = _translate(ErrorEvent(message="boom"))
    assert translated.type == GeneratedType.DONE


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
# renders with the same library the 1.0 path uses, so a syntax drift fails here rather than in
# front of a learner.


@pytest.mark.parametrize(
    ("spec_kwargs", "expected_variables"),
    [
        pytest.param(
            {
                "type": "single",
                "prompt": "p",
                "options": [Option(display="A"), Option(display="B")],
                "variable": "choice",
            },
            ["choice"],
            id="single",
        ),
        pytest.param(
            {
                "type": "multi",
                "prompt": "p",
                "options": [Option(display="A"), Option(display="B")],
                "variable": "choices",
            },
            ["choices"],
            id="multi",
        ),
        pytest.param(
            {
                "type": "text",
                "prompt": "p",
                "variable": "story",
                "placeholder": "Your answer",
            },
            ["story"],
            id="free-text",
        ),
        pytest.param(
            {
                "type": "single",
                "prompt": "p",
                "options": [Option(display="Yes, please", value="yes")],
                "variable": "answer",
            },
            ["answer"],
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
            ["answer"],
            id="choice-or-text",
        ),
        pytest.param(
            {"type": "confirm", "prompt": "p", "options": [Option(display="Continue")]},
            [],
            id="confirm-stores-nothing",
        ),
    ],
)
def test_what_this_renders_parses_back_as_an_interaction(
    spec_kwargs: dict, expected_variables: list[str]
) -> None:
    from markdown_flow import MarkdownFlow

    rendered = legacy_protocol.render_interaction(_spec(**spec_kwargs))
    parsed = MarkdownFlow(rendered)

    assert [block.block_type.name for block in parsed.get_all_blocks()] == [
        "INTERACTION"
    ]
    assert parsed.extract_variables() == expected_variables

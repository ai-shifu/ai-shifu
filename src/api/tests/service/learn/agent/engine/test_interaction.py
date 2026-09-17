"""Interaction specs: validation, answer normalization, what gets stored."""

import pytest
from flaskr.service.learn.agent.engine.interaction import (
    InteractionAnswer,
    InteractionSpec,
    Option,
    format_answer_for_model,
    normalize_answer,
    stored_value,
)
from pydantic import ValidationError


def spec(t: str, opts: tuple[str, ...] = ("A", "B"), **kw: object) -> InteractionSpec:
    return InteractionSpec(
        type=t, prompt="q", options=[Option(display=o) for o in opts], **kw
    )


def test_choice_types_need_options() -> None:
    with pytest.raises(ValidationError):
        InteractionSpec(type="single", prompt="q")
    with pytest.raises(ValidationError):
        InteractionSpec(type="text", prompt="q", options=[Option(display="x")])


def test_confirm_gets_default_option() -> None:
    s = InteractionSpec(type="confirm", prompt="go on")
    assert s.options[0].stored == "continue"


def test_normalize_maps_display_to_value_and_drops_strangers() -> None:
    s = InteractionSpec(
        type="single",
        prompt="q",
        options=[Option(display="Yes", value="y"), Option(display="No", value="n")],
    )
    a = normalize_answer(s, InteractionAnswer(values=["Yes", "Maybe"]))
    assert a.values == ["y"]
    m = normalize_answer(
        spec("multi", ("A", "B", "C")), InteractionAnswer(values=["C", "A", "Z"])
    )
    assert m.values == ["C", "A"]


def test_or_text_keeps_free_text_values() -> None:
    a = normalize_answer(
        spec("single_or_text"), InteractionAnswer(values=["mine"], text=None)
    )
    assert a.values == ["mine"]


def test_stored_value_and_model_text() -> None:
    s = spec("single_or_text", variable="v")
    a = InteractionAnswer(values=["A"], text="because")
    assert stored_value(s, a) == "A; because"
    assert format_answer_for_model(s, a) == "Learner chose: A; and wrote: because"
    assert (
        format_answer_for_model(s, InteractionAnswer())
        == "Learner continued without answering."
    )
    assert stored_value(spec("text", ()), InteractionAnswer(text="free")) == "free"


def test_coerce() -> None:
    assert InteractionAnswer.coerce("hi").text == "hi"
    assert InteractionAnswer.coerce(["a"]).values == ["a"]
    assert InteractionAnswer.coerce({"values": ["a"], "text": "t"}).text == "t"


def test_a_confirm_never_carries_a_memory_variable() -> None:
    """A confirm means "go on", so its button text is never stored as an answer.

    Models do attach a variable to one -- often the variable the previous question filled -- and
    storing the button's label then destroys a real answer.
    """
    spec = InteractionSpec.model_validate(
        {
            "type": "confirm",
            "prompt": "我复述的和你的实际情况一致吗？",
            "options": [{"display": "对，就是这样"}],
            "variable": "卡点场景",
        }
    )
    assert spec.variable is None


def test_other_interaction_types_keep_their_variable() -> None:
    for kind, extra in (
        ("text", {}),
        ("single", {"options": [{"display": "A"}]}),
        ("multi", {"options": [{"display": "A"}]}),
        ("single_or_text", {"options": [{"display": "A"}]}),
    ):
        spec = InteractionSpec.model_validate(
            {"type": kind, "prompt": "q", "variable": "mood", **extra}
        )
        assert spec.variable == "mood", kind

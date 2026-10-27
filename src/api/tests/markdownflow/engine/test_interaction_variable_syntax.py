"""Keep authored answer controls equivalent for both variable marker spellings."""

import pytest
from markdown_flow import InteractionParser
from markdownflow.engine.interaction import InteractionSpec, Option
from markdownflow.engine.tools import (
    normalize_script_text_input,
    script_options,
    script_pauses,
    script_text_inputs,
)


@pytest.mark.parametrize("prefix", ["%", ""])
@pytest.mark.parametrize("separator", [" | ", " || "])
def test_binding_does_not_become_an_option_or_placeholder(
    prefix: str, separator: str
) -> None:
    source = (
        "?[ "
        + prefix
        + "{{ Which [path] | level//hint...? }} A//a"
        + separator
        + "B//b"
        + separator
        + "...Other]"
    )

    assert script_options(source) == {"A": "A", "a": "a", "B": "B", "b": "b"}
    (question,) = script_text_inputs(source)
    assert question.variable == "Which [path] | level//hint...?"
    assert question.placeholder == "Other"
    assert [choice.strip() for choice in question.choices] == ["A//a", "B//b", ""]
    assert question.multi is (separator == " || ")


@pytest.mark.parametrize("prefix", ["%", ""])
def test_named_single_option_is_not_an_automatic_navigation_pause(prefix: str) -> None:
    assert script_pauses("?[" + prefix + "{{ready}} Ready]") == 0


@pytest.mark.parametrize("prefix", ["%", ""])
def test_named_text_only_input_has_no_extra_variable_button(prefix: str) -> None:
    source = "?[" + prefix + "{{goal}}...Your goal?]"
    assert script_options(source) == {}
    (question,) = script_text_inputs(source)
    assert question.variable == "goal"
    assert question.placeholder == "Your goal?"
    assert not any(choice.strip() for choice in question.choices)


@pytest.mark.parametrize("prefix", ["%", ""])
@pytest.mark.parametrize("name", ["", " ", "bad\nkey", "bad\x00key", "bad\u2028key"])
@pytest.mark.parametrize("body", ["Ready", "Ready | ...Hint", "...Hint"])
def test_invalid_leading_bindings_do_not_define_controls(
    prefix: str, name: str, body: str
) -> None:
    """Invalid bindings cannot authorize options, navigation pauses, or hint repairs."""
    source = "?[" + prefix + "{{" + name + "}} " + body + "]"
    assert InteractionParser().parse(source)["type"] is None
    assert script_options(source) == {}
    assert script_pauses(source) == 0
    assert script_text_inputs(source) == ()

    spec = InteractionSpec(
        type="single",
        prompt="Pick",
        options=[Option(display="Ready"), Option(display="...Hint")],
    )
    assert normalize_script_text_input(spec, script_text_inputs(source)) == spec


@pytest.mark.parametrize("prefix", ["%", ""])
@pytest.mark.parametrize("name", [" ", "bad\nkey", "bad\x00key"])
def test_invalid_bindings_leave_following_valid_controls_available(
    prefix: str, name: str
) -> None:
    """Rejecting a malformed question must not discard later authored controls."""
    source = (
        "?[" + prefix + "{{" + name + "}} Wrong | ...Ignored]"
        "\n\n?[{{goal}} First//one | ...Explain]\n\n?[Continue]"
    )
    assert script_options(source) == {
        "First": "First",
        "one": "one",
        "Continue": "Continue",
    }
    assert script_pauses(source) == 1
    (question,) = script_text_inputs(source)
    assert question.variable == "goal"
    assert question.placeholder == "Explain"

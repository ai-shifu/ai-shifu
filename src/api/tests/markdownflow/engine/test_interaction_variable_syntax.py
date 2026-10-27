"""Keep authored answer controls equivalent for both variable marker spellings."""

import pytest
from markdownflow.engine.tools import script_options, script_pauses, script_text_inputs


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

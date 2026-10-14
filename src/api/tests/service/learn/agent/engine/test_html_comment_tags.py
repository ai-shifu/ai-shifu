"""HTML attributes cannot turn authored notes into Markdown code examples."""

import pytest
from flaskr.service.learn.agent.engine.script import (
    ScriptBundle,
    collected_names,
    render_first_prompt,
)
from flaskr.service.learn.agent.engine.script_comments import strip_comments


@pytest.mark.parametrize("quote", ["'", '"'])
@pytest.mark.parametrize("attribute", ["title", "data-hint"])
def test_attribute_backticks_do_not_protect_comments(
    quote: str, attribute: str
) -> None:
    first = f"<span {attribute}={quote}`>{quote}>One</span>"
    second = f"<span {attribute}={quote}`{quote}>Two</span>"
    source = first + "<!-- private %{{hidden}} {{secret}} -->" + second
    bundle = ScriptBundle(script=source)
    assert strip_comments(source) == first + second
    assert collected_names(source) == frozenset()
    prompt = render_first_prompt(bundle, {})
    assert first + second in prompt
    assert "private" not in prompt
    assert "hidden" not in prompt
    assert "secret" not in prompt
    assert bundle.script == source


def test_html_attribute_comment_notation_is_literal_attribute_data() -> None:
    source = '<span title="<!-- literal -->`">Visible</span><!-- private -->'
    assert strip_comments(source) == source.removesuffix("<!-- private -->")


def test_html_inside_markdown_code_remains_literal() -> None:
    source = '``<span title="`">One</span><!-- literal -->`` <!-- private -->'
    assert strip_comments(source) == source.removesuffix("<!-- private -->")

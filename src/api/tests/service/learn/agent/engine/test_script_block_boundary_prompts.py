"""Unmatched code delimiters cannot expose author notes across Markdown blocks."""

import pytest
from flaskr.service.learn.agent.engine.script import (
    ScriptBundle,
    collected_names,
    render_first_prompt,
    substitution_names,
)


@pytest.mark.parametrize(
    "boundary", ["# Heading", "---", "- List item", "> Quoted paragraph", "<div>"]
)
@pytest.mark.parametrize("linebreak", ["\n", "\r\n", "\r"])
def test_separate_blocks_cannot_pair_delimiters_to_expose_author_notes(
    boundary: str, linebreak: str
) -> None:
    source = linebreak.join(
        [
            "`Unfinished paragraph",
            boundary,
            "<!-- private %{{hidden}} {{secret}} -->",
            "Another unmatched `",
        ]
    )
    bundle = ScriptBundle(script=source)
    prompt = render_first_prompt(bundle, {"secret": "Historical learner value"})
    assert "<!-- private" not in prompt
    assert "Historical learner value" not in prompt.split("<script>", 1)[1]
    assert '"secret": "Historical learner value"' in prompt
    assert collected_names(source) == frozenset()
    assert substitution_names(bundle) == frozenset()
    assert bundle.script == source


@pytest.mark.parametrize("field", ["constraints", "extras"])
def test_block_boundaries_also_filter_non_lesson_authored_documents(field: str) -> None:
    source = "`Unfinished\n# Heading\n<!-- private author note -->\n`"
    bundle = (
        ScriptBundle(script="Teach.", constraints=source)
        if field == "constraints"
        else ScriptBundle(script="Teach.", extras={"reference": source})
    )
    assert "private author note" not in render_first_prompt(bundle, {})


def test_soft_linebreak_inside_a_real_code_span_preserves_its_literal_example() -> None:
    source = "`Example <!-- literal\ncomment -->`"
    assert source in render_first_prompt(ScriptBundle(script=source), {})

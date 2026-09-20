"""Cover a question travelling from the script to the learner without being rewritten.

The reported failure: a six-option multiple choice with a free-text box came back as a single
choice carrying one option the author never wrote, with a placeholder of the model's own. The
syntax prompt now forbids that, but a prompt is an instruction, not a guarantee -- so this covers
the part of the journey the code owns. The model's own fidelity is checked against the live
gateway, which no offline test can do.
"""

from __future__ import annotations

from flaskr.service.learn.agent.engine.interaction import InteractionSpec, Option
from flaskr.service.learn.agent.legacy_protocol import render_interaction
from markdown_flow import InteractionParser

# The question as the author wrote it, from 跟 AI 学 AI 通识.
AUTHORED = (
    "?[%{{purpose}} 找工作 || 提升竞争力 || 生活幸福 || 好奇 || 害怕被 AI 替代 "
    "|| 改变世界 ||...还有什么目的？]"
)


def _spec_from(authored: str) -> InteractionSpec:
    """Build the spec a model following the syntax rule would send."""
    parsed = InteractionParser().parse(authored)
    buttons = parsed.get("buttons") or []
    return InteractionSpec(
        type="multi_or_text",
        prompt="",
        options=[
            Option(display=b.get("display"), value=b.get("value")) for b in buttons
        ],
        variable=parsed.get("variable") or None,
        placeholder=parsed.get("question") or None,
    )


def test_the_question_the_learner_sees_is_the_question_the_author_wrote() -> None:
    """Every option, in order, multiple choice intact, with the author's own placeholder."""
    rendered = render_interaction(_spec_from(AUTHORED))

    parsed = InteractionParser().parse(rendered)
    assert [b["display"] for b in parsed["buttons"]] == [
        "找工作",
        "提升竞争力",
        "生活幸福",
        "好奇",
        "害怕被 AI 替代",
        "改变世界",
    ]
    assert parsed["question"] == "还有什么目的？"
    assert parsed["variable"] == "purpose"
    # Double bars: a multiple choice that renders with single bars can only take one answer.
    assert "||" in rendered


def test_a_spec_whose_options_were_rewritten_does_not_match_the_script() -> None:
    """What the failure looked like, so the shape of it stays recognisable.

    A guard against the assertion above being weakened into something a rewritten question would
    also satisfy.
    """
    rewritten = render_interaction(
        InteractionSpec(
            type="single_or_text",
            prompt="",
            options=[Option(display="还没想好")],
            variable="purpose",
            placeholder="学 AI 的目的是什么？",
        )
    )
    parsed = InteractionParser().parse(rewritten)

    assert [b["display"] for b in parsed["buttons"]] != ["找工作"]
    assert parsed["question"] != "还有什么目的？"
    assert "||" not in rewritten

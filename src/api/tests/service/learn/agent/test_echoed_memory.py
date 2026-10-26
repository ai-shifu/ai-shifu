"""Cover the removal of the model's copy of the engine's `<memory>` section from its text."""

from __future__ import annotations

import random

from flaskr.service.learn.agent.echoed_memory import EchoedMemoryFilter

# What a real lesson sent the learner, word for word, at the top of its reply.
LEAKED = (
    "<memory>\n"
    '{"key": "经验", "value": "完全没写过代码", "scope": "session"}\n'
    "</memory>\n"
    "\n"
    "好，那我们用做菜来打比方。\n"
)


def _through(text: str, seed: int) -> str:
    """Push the text through in random-sized chunks, the way a model streams it."""
    rng = random.Random(seed)  # noqa: S311 -- chunk sizes, not secrets
    echo_filter = EchoedMemoryFilter()
    out: list[str] = []
    index = 0
    while index < len(text):
        step = rng.randint(1, 6)
        out.append(echo_filter.feed(text[index : index + step]))
        index += step
    out.append(echo_filter.flush())
    return "".join(out)


def test_the_memory_block_a_lesson_sent_the_learner_is_removed() -> None:
    """The learner read the JSON the model wrote instead of calling `remember`."""
    for seed in range(50):
        assert _through(LEAKED, seed) == "好，那我们用做菜来打比方。\n", f"seed {seed}"


def test_a_block_on_one_line_is_removed_too() -> None:
    text = '<memory>{"key": "a", "value": "b"}</memory>\n讲课。\n'
    for seed in range(30):
        assert _through(text, seed) == "讲课。\n", f"seed {seed}"


def test_a_block_later_in_the_turn_is_removed_and_the_text_around_it_kept() -> None:
    text = "第一段。\n<memory>\n{}\n</memory>\n第二段。\n"
    for seed in range(30):
        assert _through(text, seed) == "第一段。\n第二段。\n", f"seed {seed}"


def test_text_without_a_block_is_left_exactly_as_it_is() -> None:
    text = "<b>粗体</b> 和 <mem 不是标签。\n\n  缩进行\n```py\nx = 1\n```\n`code` 行\n~ 波浪\n"
    for seed in range(50):
        assert _through(text, seed) == text, f"seed {seed}"


def test_the_tag_shown_inside_code_is_kept() -> None:
    """A lesson about prompts may show the tag; in a code block it is an example, not an echo."""
    text = "看这个例子：\n```xml\n<memory>\n{}\n</memory>\n```\n"
    for seed in range(30):
        assert _through(text, seed) == text, f"seed {seed}"


def test_the_tag_mid_sentence_is_kept() -> None:
    text = "模型会看到 <memory> 这一段。\n"
    for seed in range(30):
        assert _through(text, seed) == text, f"seed {seed}"


def test_a_block_that_never_closes_is_released_rather_than_swallowing_the_lesson() -> (
    None
):
    text = "<memory>\n还有后面的课。\n"
    for seed in range(30):
        assert _through(text, seed) == text, f"seed {seed}"


def test_text_goes_out_as_it_arrives_rather_than_at_the_end_of_the_line() -> None:
    """Holding every line to its end would stall the lesson's streaming for no reason."""
    echo_filter = EchoedMemoryFilter()
    assert echo_filter.feed("好，那我们") == "好，那我们"


def test_a_closing_fence_split_across_chunks_still_closes_the_code() -> None:
    """Otherwise the code never ends, and a block written after it is taken for an example."""
    for fence in ("```", "~~~"):
        text = f"{fence}\nexample\n{fence}\n<memory>\n{{}}\n</memory>\nNext\n"
        for seed in range(30):
            assert _through(text, seed) == f"{fence}\nexample\n{fence}\nNext\n", (
                f"{fence} seed {seed}"
            )


def test_the_tag_in_indented_code_is_kept() -> None:
    """Four spaces of indent is a code block in Markdown: the lesson is showing the format."""
    text = "    <memory>\n    {}\n    </memory>\nNext\n"
    for seed in range(30):
        assert _through(text, seed) == text, f"seed {seed}"


def test_a_backtick_line_with_a_backtick_after_it_is_not_a_fence() -> None:
    """CommonMark: a backtick fence's info string cannot contain a backtick."""
    text = "``` `not a fence`\n<memory>\n{}\n</memory>\nNext\n"
    for seed in range(30):
        assert _through(text, seed) == "``` `not a fence`\nNext\n", f"seed {seed}"


def test_a_block_that_ends_the_turn_without_a_newline_is_removed() -> None:
    for text in (
        '讲课。\n<memory>{"key": "a"}</memory>',
        '讲课。\n<memory>\n{"key": "a"}\n</memory>',
    ):
        for seed in range(30):
            assert _through(text, seed) == "讲课。\n", f"{text!r} seed {seed}"

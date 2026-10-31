"""Keep repeated slide layouts intact when a continuation changes their contents."""

import json
from collections.abc import AsyncIterator

import pytest
from markdownflow import LessonPager
from markdownflow.engine import ContentDelta, Engine, SegmentStart
from markdownflow.engine.engine import _after_the_repeat
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

pytestmark = pytest.mark.anyio

_OVERVIEW = (
    '<div style="width:100%; min-height:100vh; display:flex; '
    'flex-direction:column; background:#fffaf4; padding:1em;">\n'
    '<div class="layout">\n'
    '<div class="title">Three steps</div>\n'
    '<div style="display:grid; grid-template-columns:repeat(3,1fr);">\n'
    '<div class="step">See the thought</div>\n'
    '<div class="step">Evaluate the thought</div>\n'
    '<div class="step">Transform the thought</div>\n'
    "</div>\n</div>\n</div>\n"
    "<style>.step { padding:1em; } .active { background:#c98a5b; }</style>\n"
)
_HIGHLIGHTED = _OVERVIEW.replace('class="step"', 'class="step active"', 1)
_RECAP = "We have now introduced all three steps in the thought-changing process.\n"
_NEXT = "Now focus on noticing your own thought.\n"


@pytest.mark.parametrize("listen_mode", [False, True])
@pytest.mark.parametrize("chunk_size", [1, 37, 4096])
@pytest.mark.parametrize("recap", ["", _RECAP], ids=["no-recap", "prose-recap"])
async def test_continuation_keeps_a_highlighted_slide_as_one_element(
    listen_mode: bool, chunk_size: int, recap: str
) -> None:
    """A shared page header is layout, even after a genuinely repeated prose recap."""
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        nonlocal calls
        calls += 1
        text = recap + (_OVERVIEW if calls == 1 else _HIGHLIGHTED + _NEXT)
        for start in range(0, len(text), chunk_size):
            yield text[start : start + chunk_size]

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session(
        "Show the three steps, then show the same slide with the first step highlighted.",
        listen_mode=listen_mode,
    )
    _ = [event async for event in engine.run_turn(session)]
    events = [event async for event in engine.run_turn(session)]
    displayed = "".join(
        event.text for event in events if isinstance(event, ContentDelta)
    )

    assert displayed == _HIGHLIGHTED + _NEXT
    assert events[-1].reason == "end"
    assert session.finished is False

    pager = LessonPager(clean_markers=True)
    elements: dict[tuple[int, str], str] = {}
    for content, kind, number in pager.add(displayed) + pager.flush():
        key = (number, kind)
        elements[key] = elements.get(key, "") + content
    assert [content for (_, kind), content in elements.items() if kind == "html"] == [
        _HIGHLIGHTED
    ]
    if listen_mode:
        visuals = [
            event.visual.content
            for event in events
            if isinstance(event, SegmentStart) and event.visual is not None
        ]
        assert visuals == [_HIGHLIGHTED]


@pytest.mark.parametrize("listen_mode", [False, True])
async def test_a_highlighted_slide_after_an_unscripted_pause_keeps_its_layout(
    listen_mode: bool,
) -> None:
    """The same-turn repeat guard also retains the complete updated visual."""
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _OVERVIEW
            yield {
                0: DeltaToolCall(
                    name="interact",
                    json_args=json.dumps({"type": "confirm", "prompt": "Continue?"}),
                    tool_call_id="unscripted-pause",
                )
            }
        else:
            for character in _HIGHLIGHTED + _NEXT:
                yield character

    engine = Engine(FunctionModel(stream_function=model), pauses_from_notation=True)
    session = await engine.new_session(
        "Show the three steps, then highlight the first step without pausing.",
        listen_mode=listen_mode,
    )
    events = [event async for event in engine.run_turn(session)]
    displayed = "".join(
        event.text for event in events if isinstance(event, ContentDelta)
    )

    assert displayed == _OVERVIEW + _HIGHLIGHTED + _NEXT
    assert calls == 2
    assert events[-1].reason == "end"
    assert session.finished is False


@pytest.mark.parametrize("marker", ["===", "!==="])
@pytest.mark.parametrize("chunk_size", [1, 4096])
@pytest.mark.parametrize("kind", ["html", "code"])
async def test_continuation_keeps_inline_mdf_wrapped_visuals_complete(
    marker: str, chunk_size: int, kind: str
) -> None:
    """The trim boundary must recognize the same inline wrappers as the display pager."""
    original = (
        _OVERVIEW.split("<style>", 1)[0].rstrip("\n")
        if kind == "html"
        else "```python\n# Shared setup for two examples with a changed value.\nvalue = 1\n```"
    )
    updated = (
        original.replace('class="step"', 'class="step active"', 1)
        if kind == "html"
        else original.replace("value = 1", "value = 2")
    )
    first = f"{marker}{original}===\n"
    next_visual = f"{marker}{updated}===\n"
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        nonlocal calls
        calls += 1
        text = _RECAP + (first if calls == 1 else next_visual + _NEXT)
        for start in range(0, len(text), chunk_size):
            yield text[start : start + chunk_size]

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session(
        "Show both examples with their complete structure."
    )
    _ = [event async for event in engine.run_turn(session)]
    events = [event async for event in engine.run_turn(session)]
    displayed = "".join(
        event.text for event in events if isinstance(event, ContentDelta)
    )

    assert displayed == next_visual + _NEXT
    assert events[-1].reason == "end"
    assert session.finished is False
    pager = LessonPager(clean_markers=True)
    elements: dict[int, str] = {}
    for content, stream_type, number in pager.add(displayed) + pager.flush():
        if stream_type == kind:
            elements[number] = elements.get(number, "") + content
    assert list(elements.values()) == [updated + "\n"]


@pytest.mark.parametrize(
    "visual",
    [
        _OVERVIEW,
        "```html\n" + _OVERVIEW + "```\n",
        "```python\n# A shared setup line that is longer than the repeat threshold.\n"
        "value = 1\n```\n",
        "| First thought | Second thought |\n| --- | --- |\n"
        "| A repeated row with enough text for the repeat threshold | Evaluate |\n",
    ],
    ids=["html", "fenced-html", "code", "table"],
)
def test_a_repeated_visual_before_new_narration_keeps_its_complete_source(
    visual: str,
) -> None:
    """Only the prose recap can be removed; a repeated visual remains a complete unit."""
    said = "".join((_RECAP + visual).split())
    assert _after_the_repeat([_RECAP + visual + _NEXT], said) == visual + _NEXT


def test_an_unfinished_table_row_is_not_cut_inside() -> None:
    """A held row without its closing bar yet still starts a table."""
    said = "".join((_RECAP + "| Step 1. Read the chapter | Done |\n").split())
    row = "| Step 1. Review the notes"
    assert _after_the_repeat([_RECAP, row], said) == row


def test_an_unfinished_prose_line_is_still_trimmed() -> None:
    """Only a table-like line is protected; repeated prose without a newline is cut."""
    recap = _RECAP.rstrip("\n")
    said = "".join((recap + " That was the last step.").split())
    assert _after_the_repeat([recap + " Now try it"], said) == " Now try it"

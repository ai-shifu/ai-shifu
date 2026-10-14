"""Exercise the 2.0 host through the existing element stream and history contract."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import run_agent
from flaskr.service.learn.agent.engine.events import (
    ContentDelta,
    InteractionRequest,
    TurnDone,
)
from flaskr.service.learn.agent.engine.interaction import InteractionSpec, Option
from flaskr.service.learn.const import ROLE_TEACHER
from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    ElementDTO,
    ElementType,
    GeneratedType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.listen_elements import (
    ListenElementRunAdapter,
    get_listen_element_record,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
from markdown_flow.formatter.stream import StreamFormatter

from tests.service.learn.agent import test_run_agent as host_fixture

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask


calls = host_fixture.calls


LESSON = (
    "# Visual lesson\n\n"
    "Intro narration.\n\n"
    '<div class="slide">\n  <p>Slide one</p>\n---\n</div>\n'
    "<style>.slide { color: red; }</style>\n"
    "<script>window.ready = true;</script>\n\n"
    "More narration.\n\n"
    "![diagram](https://example.com/diagram.png)\n\n"
    '```python\nprint("hello")\n```\n\n'
    "| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
    "```mermaid\ngraph LR\n  A --> B\n```\n\n"
    "Final narration."
)


class _Voice:
    """Replace the remote synthesis provider while keeping real audio binding."""

    def __init__(self, _app: Flask, **kwargs: object) -> None:
        self.outline_bid = str(kwargs["outline_bid"])
        self.generated_block_bid = str(kwargs["generated_block_bid"])
        self.text_by_number: dict[int, str] = {}

    def speak(
        self, text: str, *, stream_type: str = "text", stream_number: int = 0
    ) -> list[RunMarkdownFlowDTO]:
        if stream_type == "text" and text.strip():
            self.text_by_number[stream_number] = (
                self.text_by_number.get(stream_number, "") + text
            )
        return []

    def finish(self) -> Iterator[RunMarkdownFlowDTO]:
        for position, number in enumerate(self.text_by_number):
            yield RunMarkdownFlowDTO(
                outline_bid=self.outline_bid,
                generated_block_bid=self.generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url=f"https://example.com/audio/{number}.mp3",
                    audio_bid=f"audio-{number}",
                    duration_ms=1000,
                    position=position,
                    stream_element_number=number,
                    stream_element_type="text",
                ),
            )


def _reference_shape(text: str) -> list[tuple[str, str]]:
    """Use the 1.0 formatter directly, independent of the 2.0 pager."""
    formatter = StreamFormatter()
    grouped: dict[tuple[int, str], str] = {}
    for piece in formatter.process(text) + formatter.flush():
        key = (piece.number, str(piece.type))
        grouped[key] = grouped.get(key, "") + str(piece.content or "")
    return [
        (kind, content.strip())
        for (_, kind), content in grouped.items()
        if content.strip()
    ]


def _shape(elements: list[ElementDTO]) -> list[tuple[str, str]]:
    return [
        (element.element_type.value, element.content.strip())
        for element in elements
        if element.content.strip()
    ]


def _adapt_and_reload(
    app: Flask,
    events: list[RunMarkdownFlowDTO],
) -> tuple[list[ElementDTO], list[ElementDTO]]:
    generated_block_bid = next(
        event.generated_block_bid for event in events if event.generated_block_bid
    )
    with app.app_context():
        with unit_of_work():
            db.session.add_all(
                [
                    LearnProgressRecord(
                        progress_record_bid=host_fixture.PROGRESS,
                        shifu_bid=host_fixture.SHIFU,
                        outline_item_bid=host_fixture.OUTLINE,
                        user_bid=host_fixture.USER,
                        status=LEARN_STATUS_IN_PROGRESS,
                        block_position=0,
                    ),
                    LearnGeneratedBlock(
                        generated_block_bid=generated_block_bid,
                        progress_record_bid=host_fixture.PROGRESS,
                        user_bid=host_fixture.USER,
                        block_bid="script-block",
                        outline_item_bid=host_fixture.OUTLINE,
                        shifu_bid=host_fixture.SHIFU,
                        type=0,
                        role=ROLE_TEACHER,
                        generated_content="".join(
                            str(event.content)
                            for event in events
                            if event.type == GeneratedType.CONTENT
                        ),
                        position=0,
                        block_content_conf="",
                        status=1,
                    ),
                ]
            )
        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=host_fixture.SHIFU,
            outline_bid=host_fixture.OUTLINE,
            user_bid=host_fixture.USER,
            persist_only_final=True,
        )
        with unit_of_work():
            messages = list(adapter.process(events))
        latest: dict[str, ElementDTO] = {}
        for message in messages:
            if message.type == "element":
                element = message.content
                assert isinstance(element, ElementDTO)
                latest[element.element_bid] = element
        streamed = sorted(latest.values(), key=lambda item: item.element_index)
        rows = (
            LearnGeneratedElement.query.filter_by(
                generated_block_bid=generated_block_bid,
                event_type="element",
                status=1,
                deleted=0,
            )
            .order_by(LearnGeneratedElement.element_index.asc())
            .all()
        )
        assert rows
        assert all(row.is_final for row in rows)
        assert len(rows) == len(latest)
        record = get_listen_element_record(
            app,
            shifu_bid=host_fixture.SHIFU,
            outline_bid=host_fixture.OUTLINE,
            user_bid=host_fixture.USER,
            preview_mode=False,
        )
        assert _shape(record.elements) == _shape(streamed)
        assert all(element.is_final for element in record.elements)
        return streamed, record.elements


@pytest.fixture
def format_environment(
    app: Flask | None, monkeypatch: pytest.MonkeyPatch, calls: list
) -> Flask:
    """Keep host writes stubbed, but use real element storage and history queries."""
    if app is None:
        pytest.skip("App fixture disabled")
    suffix = uuid.uuid4().hex
    for name in ("USER", "SHIFU", "OUTLINE", "PROGRESS"):
        monkeypatch.setattr(host_fixture, name, f"{name.lower()}-{suffix}")
    monkeypatch.setattr(run_agent, "LessonVoice", _Voice)
    monkeypatch.setattr(
        "flaskr.service.learn.agent.routing.uses_agent_engine", lambda _bid: False
    )
    assert calls == []
    return app


@pytest.mark.parametrize("mode", ["read", "classroom", "listen"])
@pytest.mark.parametrize("chunk_width", [1, 17, len(LESSON)])
def test_all_modes_reuse_formatted_elements_and_persist_visuals(
    format_environment: Flask, mode: str, chunk_width: int
) -> None:
    engine = host_fixture._Engine(
        [
            ContentDelta(text=LESSON[index : index + chunk_width])
            for index in range(0, len(LESSON), chunk_width)
        ]
        + [TurnDone(reason="end")]
    )
    # Reading and classroom both request listen=False; formatting is independent of audio.
    events = host_fixture._run(engine, app=format_environment, listen=mode == "listen")
    streamed, history = _adapt_and_reload(format_environment, events)
    expected = _reference_shape(LESSON)
    assert {kind for kind, _ in expected} >= {
        "title",
        "text",
        "html",
        "img",
        "code",
        "tables",
        "mermaid",
    }
    assert _shape(streamed) == expected
    assert _shape(history) == expected
    for element in streamed + history:
        is_text = element.element_type == ElementType.TEXT
        assert element.is_renderable is (not is_text)
        assert element.is_marker is (not is_text)
        assert element.is_speakable is is_text
        assert bool(element.audio_url) is (mode == "listen" and is_text)
    html = next(
        element for element in history if element.element_type == ElementType.HTML
    )
    assert "<style>" in html.content
    assert "<script>" in html.content
    assert "\n---\n" in html.content


@pytest.mark.parametrize("listen", [False, True])
def test_html_in_question_prompt_uses_the_same_formatter(
    format_environment: Flask, listen: bool
) -> None:
    narration = "Compare the examples.\n\n"
    prompt = (
        '<div class="choices"><p>First or second?</p></div>\n'
        "<style>.choices { color: blue; }</style>\n\n"
        "Which example do you prefer?"
    )
    engine = host_fixture._Engine(
        [
            ContentDelta(text=narration),
            InteractionRequest(
                id="comparison",
                spec=InteractionSpec(
                    type="single",
                    prompt=prompt,
                    options=[Option(display="First"), Option(display="Second")],
                ),
            ),
            TurnDone(reason="interaction"),
        ]
    )
    events = host_fixture._run(engine, app=format_environment, listen=listen)
    streamed, history = _adapt_and_reload(format_environment, events)
    content = [
        element
        for element in history
        if element.element_type != ElementType.INTERACTION
    ]
    assert _shape(content) == _reference_shape(narration + prompt)
    assert history[-1].element_type == ElementType.INTERACTION
    assert history[-1].content == "?[First | Second]"
    assert _shape(streamed) == _shape(history)


@pytest.mark.parametrize("opening", ["<div>", "<svg>", "```python"])
@pytest.mark.parametrize("listen", [False, True])
@pytest.mark.parametrize("echo_question", [False, True])
def test_question_after_unclosed_visual_is_independently_shown_and_spoken(
    format_environment: Flask, opening: str, listen: bool, echo_question: bool
) -> None:
    prompt = "Which example do you prefer?"
    narration = opening + "\n" + (prompt if echo_question else "Unfinished visual")
    engine = host_fixture._Engine(
        [
            ContentDelta(text=narration),
            InteractionRequest(
                id="comparison",
                spec=InteractionSpec(
                    type="single",
                    prompt=prompt,
                    options=[Option(display="First"), Option(display="Second")],
                ),
            ),
            TurnDone(reason="interaction"),
        ]
    )
    events = host_fixture._run(engine, app=format_environment, listen=listen)
    streamed, history = _adapt_and_reload(format_environment, events)
    for elements in (streamed, history):
        assert len(elements) == 3
        assert elements[0].content == narration
        question = elements[1]
        assert question.element_type == ElementType.TEXT
        assert question.content == prompt
        assert question.is_speakable is True
        assert bool(question.audio_url) is listen
        assert elements[2].element_type == ElementType.INTERACTION
        assert elements[0].element_bid != question.element_bid

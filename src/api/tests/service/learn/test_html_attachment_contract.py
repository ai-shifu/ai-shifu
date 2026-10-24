"""Keep formatter HTML attachments on their original streamed and stored element."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn.learn_dtos import (
    ElementType,
    GeneratedType,
    RunMarkdownFlowDTO,
)
from markdownflow.engine.events import ContentDelta, TurnDone

from tests.service.learn.agent import test_element_format as format_fixture
from tests.service.learn.agent import test_run_agent as host_fixture

if TYPE_CHECKING:
    from flask import Flask


calls = host_fixture.calls
format_environment = format_fixture.format_environment


@pytest.mark.parametrize("mode", ["read", "classroom", "listen"])
@pytest.mark.parametrize("chunk_width", [1, 17, 1000])
@pytest.mark.parametrize(
    "attachment",
    [
        "<style>.card { color: red; }</style>\n",
        "<script>window.ready = true;</script>\n",
        '<link rel="stylesheet" href="https://example.com/card.css">\n',
    ],
    ids=["style", "script", "link"],
)
def test_html_attachment_after_narration_updates_original_element(
    format_environment: Flask,
    mode: str,
    chunk_width: int,
    attachment: str,
) -> None:
    lesson = '<div class="card">Card</div>\n---\nText.\n' + attachment
    engine = host_fixture._Engine(
        [
            ContentDelta(text=lesson[index : index + chunk_width])
            for index in range(0, len(lesson), chunk_width)
        ]
        + [TurnDone(reason="end")]
    )
    events = host_fixture._run(engine, app=format_environment, listen=mode == "listen")
    parts = [
        part
        for event in events
        if event.type == GeneratedType.CONTENT
        for part in event.get_mdflow_stream_parts()
    ]
    assert [(kind, number) for _, kind, number in parts] == [
        ("html", 0),
        ("text", 1),
        ("text", 1),
        ("html", 0),
    ]

    streamed, history = format_fixture._adapt_and_reload(format_environment, events)
    expected = format_fixture._reference_shape(lesson)
    assert format_fixture._shape(streamed) == expected
    assert format_fixture._shape(history) == expected
    for elements in (streamed, history):
        assert [element.element_type for element in elements] == [
            ElementType.HTML,
            ElementType.TEXT,
        ]
        assert elements[0].content == '<div class="card">Card</div>\n' + attachment
        assert elements[0].is_renderable
        assert not elements[0].is_speakable
        assert bool(elements[1].audio_url) is (mode == "listen")


@pytest.mark.parametrize("stream_type", ["img", "text"])
def test_non_html_interrupted_slot_still_starts_a_new_element(
    format_environment: Flask, stream_type: str
) -> None:
    generated_block_bid = f"generated-{host_fixture.OUTLINE}"
    other_type = "text" if stream_type == "img" else "img"
    pieces = [
        ("First\n", stream_type, 0),
        ("Between\n", other_type, 1),
        ("Second\n", stream_type, 0),
    ]
    events = [
        RunMarkdownFlowDTO(
            outline_bid=host_fixture.OUTLINE,
            generated_block_bid=generated_block_bid,
            type=GeneratedType.CONTENT,
            content=content,
        ).set_mdflow_stream_parts([(content, kind, number)])
        for content, kind, number in pieces
    ]
    events.append(
        RunMarkdownFlowDTO(
            outline_bid=host_fixture.OUTLINE,
            generated_block_bid=generated_block_bid,
            type=GeneratedType.BREAK,
            content="",
        )
    )
    streamed, history = format_fixture._adapt_and_reload(format_environment, events)
    for elements in (streamed, history):
        assert format_fixture._shape(elements) == [
            (kind, content.strip()) for content, kind, _ in pieces
        ]
        assert elements[0].element_bid != elements[2].element_bid

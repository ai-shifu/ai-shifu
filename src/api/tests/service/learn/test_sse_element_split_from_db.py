"""Replay deterministic persisted lessons through the complete listen SSE adapter."""

import json
import uuid

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.const import ROLE_TEACHER
from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    GeneratedType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.listen_element_rows import _element_from_row
from flaskr.service.learn.listen_elements import ListenElementRunAdapter
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.learn.routes import _to_sse_data_line
from flaskr.service.shifu.consts import BLOCK_TYPE_MDCONTENT_VALUE
from flaskr.service.tts.pipeline import build_av_segmentation_contract

LESSONS = [
    pytest.param("Narration without a visual.", ["text"], id="narration"),
    pytest.param("<svg><text>Chart label</text></svg>", ["svg"], id="pure-svg"),
    pytest.param(
        '<div class="card"><strong>HTML lesson card</strong></div>',
        ["html"],
        id="pure-html",
    ),
    pytest.param(
        "<table><tr><td>First cell</td><td>Second cell</td></tr></table>",
        ["html"],
        id="html-table",
    ),
    pytest.param(
        "Before the chart.\n\n<svg><text>Chart label</text></svg>\n\nAfter the chart.",
        ["text", "svg", "text"],
        id="mixed-svg",
    ),
    pytest.param("```python\nprint('Hello learner')\n```", ["code"], id="code"),
    pytest.param(
        "| Name | Value |\n| --- | --- |\n| Item | Result |",
        ["tables"],
        id="markdown-table",
    ),
    pytest.param(
        "![Course diagram](https://example.test/diagram.png)",
        ["md_img"],
        id="markdown-image",
    ),
]


def _content(element: object) -> str:
    if element.content_text:
        return element.content_text
    return (
        "".join(item.content for item in element.payload.previous_visuals)
        if element.payload
        else ""
    )


@pytest.fixture
def persisted_lesson(app: object) -> object:
    suffix = uuid.uuid4().hex
    identity = {
        "shifu_bid": suffix,
        "outline_item_bid": f"outline-{suffix}",
        "user_bid": f"user-{suffix}",
        "progress_record_bid": f"progress-{suffix}",
    }
    with app.app_context():
        with unit_of_work():
            db.session.add(
                LearnProgressRecord(**identity, status=602, block_position=0)
            )
        yield identity
        with unit_of_work():
            LearnGeneratedElement.query.filter_by(shifu_bid=suffix).delete()
            LearnGeneratedBlock.query.filter_by(shifu_bid=suffix).delete()
            LearnProgressRecord.query.filter_by(shifu_bid=suffix).delete()


@pytest.mark.parametrize(("content", "expected_types"), LESSONS)
def test_persisted_content_round_trips_through_sse_without_losing_content(
    app: object, persisted_lesson: dict, content: str, expected_types: list[str]
) -> None:
    block_bid = uuid.uuid4().hex
    with unit_of_work():
        db.session.add(
            LearnGeneratedBlock(
                **persisted_lesson,
                generated_block_bid=block_bid,
                role=ROLE_TEACHER,
                type=BLOCK_TYPE_MDCONTENT_VALUE,
                position=0,
                generated_content=content,
                status=1,
                deleted=0,
            )
        )
    outline_bid = persisted_lesson["outline_item_bid"]
    adapter = ListenElementRunAdapter(
        app,
        shifu_bid=persisted_lesson["shifu_bid"],
        outline_bid=outline_bid,
        user_bid=persisted_lesson["user_bid"],
    )
    contract = build_av_segmentation_contract(content, block_bid)
    events = [
        RunMarkdownFlowDTO(outline_bid, block_bid, GeneratedType.CONTENT, content),
        RunMarkdownFlowDTO(
            outline_bid,
            block_bid,
            GeneratedType.AUDIO_COMPLETE,
            AudioCompleteDTO(
                "https://example.test/audio.mp3", "audio", 1000, av_contract=contract
            ),
        ),
        RunMarkdownFlowDTO(outline_bid, block_bid, GeneratedType.BREAK, ""),
        RunMarkdownFlowDTO(outline_bid, block_bid, GeneratedType.DONE, ""),
    ]
    output = list(adapter.process(events))
    assert len([event for event in output if event.type == "done"]) == 2
    assert output[-1].is_terminal is True
    assert [event.run_event_seq for event in output] == sorted(
        event.run_event_seq for event in output
    )
    snapshots = {}
    for event in output:
        line = _to_sse_data_line(event)
        assert line.startswith("data: ")
        assert line.endswith("\n\n")
        serialized = json.loads(line[6:-2])
        assert serialized["type"] == serialized["event_type"]
        if event.type != "element":
            continue
        element = event.content
        assert element.element_bid
        assert element.role == "teacher"
        assert element.element_type_code in range(201, 214)
        # The client replaces a prior snapshot by stable element business ID.
        snapshots[element.element_bid] = element
    visible = sorted(
        (element for element in snapshots.values() if _content(element)),
        key=lambda element: element.element_index,
    )
    assert [element.element_type.value for element in visible] == expected_types
    assert all(element.is_final for element in visible)
    assert "".join(
        "".join(_content(element) for element in visible).split()
    ) == "".join(content.split())
    with unit_of_work():
        db.session.flush()
    persisted = (
        LearnGeneratedElement.query.filter_by(
            generated_block_bid=block_bid, status=1, event_type="element"
        )
        .order_by(LearnGeneratedElement.element_index)
        .all()
    )
    replay = [_element_from_row(row) for row in persisted]
    assert [
        element.element_type.value for element in replay if _content(element)
    ] == expected_types
    assert [element.element_bid for element in replay if _content(element)] == [
        element.element_bid for element in visible
    ]

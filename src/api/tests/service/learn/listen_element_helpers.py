"""Shared builders for the listen-element test family.

The listen-element tests seed progress records, generated blocks and element
rows for one learner, lesson and block, then drive ``ListenElementRunAdapter``
with ``RunMarkdownFlowDTO`` events. ``ListenScope`` keeps those identifiers in
one place so each test only spells out the fields its scenario is about.
"""

from __future__ import annotations

import dataclasses
import json
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.service.learn.const import ROLE_TEACHER
from flaskr.service.learn.elements.run_adapter import (
    ListenElementRunAdapter,
    get_listen_element_record,
)
from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    AudioSegmentDTO,
    GeneratedType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

from tests.common.fixtures.model_factories import (
    make_generated_block,
    make_generated_element,
    make_progress_record,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from flask import Flask

EMPTY_PAYLOAD = json.dumps({"audio": None, "previous_visuals": []})


@pytest.fixture
def adapter_app() -> Iterator[Flask]:
    """Bare Flask app backed by an in-memory SQLite schema."""
    from flask import Flask
    from flaskr import dao

    app = Flask("test-handle-ask-adapter")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def require_app(app: object) -> None:
    if app is None:
        pytest.skip("App fixture disabled")


def reset_learn_tables() -> None:
    """Delete every element, generated block and progress row."""
    LearnGeneratedElement.query.delete()
    LearnGeneratedBlock.query.delete()
    LearnProgressRecord.query.delete()
    db.session.commit()


def add_rows(*rows: object) -> None:
    db.session.add_all(rows)
    db.session.commit()


def audio_segment(
    position: int,
    segment_index: int,
    audio_data: str,
    duration_ms: int,
    *,
    is_final: bool,
    **extra: object,
) -> dict:
    """Return an audio segment payload as the adapter serializes it."""
    return {
        "position": position,
        "segment_index": segment_index,
        "audio_data": audio_data,
        "duration_ms": duration_ms,
        "is_final": is_final,
        **extra,
    }


def subtitle_cues(*cues: tuple[str, int, int], position: int = 0) -> list[dict]:
    """Build subtitle cues from ``(text, start_ms, end_ms)`` in segment order."""
    return [
        {
            "text": text,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "segment_index": index,
            "position": position,
        }
        for index, (text, start_ms, end_ms) in enumerate(cues)
    ]


def cue_spans(element: object) -> list[tuple[int, int]]:
    return [(cue.start_ms, cue.end_ms) for cue in element.payload.audio.subtitle_cues]


def streamed_elements(
    streamed: Iterable[object], element_type: object = None
) -> list[object]:
    """Element DTOs from a streamed run, optionally of one element type."""
    return [
        item.content
        for item in streamed
        if item.type == "element"
        and (element_type is None or item.content.element_type == element_type)
    ]


@dataclasses.dataclass(frozen=True)
class ListenScope:
    """Identifiers for one learner, lesson and generated block.

    Every identifier left empty is derived from ``slug`` as ``<kind>-<slug>``.
    """

    slug: str
    user_bid: str = ""
    shifu_bid: str = ""
    outline_bid: str = ""
    progress_bid: str = ""
    generated_block_bid: str = ""
    run_session_bid: str = ""

    def __post_init__(self) -> None:
        """Derive every identifier left empty from ``slug``."""
        for attr, prefix in (
            ("user_bid", "user"),
            ("shifu_bid", "shifu"),
            ("outline_bid", "outline"),
            ("progress_bid", "progress"),
            ("generated_block_bid", "generated"),
            ("run_session_bid", "run"),
        ):
            if not getattr(self, attr):
                object.__setattr__(self, attr, f"{prefix}-{self.slug}")

    def replace(self, **changes: str) -> ListenScope:
        return dataclasses.replace(self, **changes)

    def with_block(self, generated_block_bid: str) -> ListenScope:
        return self.replace(generated_block_bid=generated_block_bid)

    # -- rows ---------------------------------------------------------------

    def progress(self, **overrides: object) -> LearnProgressRecord:
        values = {
            "progress_record_bid": self.progress_bid,
            "shifu_bid": self.shifu_bid,
            "outline_item_bid": self.outline_bid,
            "user_bid": self.user_bid,
            "status": LEARN_STATUS_IN_PROGRESS,
        }
        return make_progress_record(**{**values, **overrides})

    def block(self, **overrides: object) -> LearnGeneratedBlock:
        values = {
            "generated_block_bid": self.generated_block_bid,
            "progress_record_bid": self.progress_bid,
            "user_bid": self.user_bid,
            "block_bid": f"block-{self.slug}",
            "outline_item_bid": self.outline_bid,
            "shifu_bid": self.shifu_bid,
            "role": ROLE_TEACHER,
            "status": 1,
        }
        return make_generated_block(**{**values, **overrides})

    def element(self, **overrides: object) -> LearnGeneratedElement:
        values = {
            "progress_record_bid": self.progress_bid,
            "user_bid": self.user_bid,
            "generated_block_bid": self.generated_block_bid,
            "outline_item_bid": self.outline_bid,
            "shifu_bid": self.shifu_bid,
            "run_session_bid": self.run_session_bid,
        }
        return make_generated_element(**{**values, **overrides})

    def render(self, **overrides: object) -> LearnGeneratedElement:
        """Element row with ``change_type=render`` and an empty payload."""
        return self.element(
            **{"change_type": "render", "payload": EMPTY_PAYLOAD, **overrides}
        )

    def seed_block(self, **block_overrides: object) -> None:
        """Reset the learn tables and add this scope's progress and block rows."""
        reset_learn_tables()
        add_rows(self.progress(), self.block(**block_overrides))

    def persisted(
        self, *filters: object, order_by: tuple | None = None
    ) -> list[LearnGeneratedElement]:
        """Active element rows of this block, by ``run_event_seq`` by default."""
        return (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.generated_block_bid == self.generated_block_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
                *filters,
            )
            .order_by(*(order_by or (LearnGeneratedElement.run_event_seq.asc(),)))
            .all()
        )

    # -- run entry points ---------------------------------------------------

    def record(self, app: Flask, **kwargs: object) -> object:
        return get_listen_element_record(
            app,
            shifu_bid=self.shifu_bid,
            outline_bid=self.outline_bid,
            user_bid=self.user_bid,
            preview_mode=False,
            **kwargs,
        )

    def adapter(self, app: Flask, **kwargs: object) -> ListenElementRunAdapter:
        return ListenElementRunAdapter(
            app,
            shifu_bid=self.shifu_bid,
            outline_bid=self.outline_bid,
            user_bid=self.user_bid,
            **kwargs,
        )

    # -- run events ---------------------------------------------------------

    def _event(self, event_type: GeneratedType, content: object) -> RunMarkdownFlowDTO:
        return RunMarkdownFlowDTO(
            outline_bid=self.outline_bid,
            generated_block_bid=self.generated_block_bid,
            type=event_type,
            content=content,
        )

    def content(
        self, text: str, kind: str | None = None, number: int = 0
    ) -> RunMarkdownFlowDTO:
        """Content chunk, tagged as one MarkdownFlow stream part when ``kind`` is set."""
        event = self._event(GeneratedType.CONTENT, text)
        if kind is not None:
            event.set_mdflow_stream_parts([(text, kind, number)])
        return event

    def audio_segment(self, **fields: object) -> RunMarkdownFlowDTO:
        return self._event(GeneratedType.AUDIO_SEGMENT, AudioSegmentDTO(**fields))

    def audio_complete(self, **fields: object) -> RunMarkdownFlowDTO:
        return self._event(GeneratedType.AUDIO_COMPLETE, AudioCompleteDTO(**fields))

    def block_break(self) -> RunMarkdownFlowDTO:
        return self._event(GeneratedType.BREAK, "")

    def ask(self, question: str, anchor_element_bid: str) -> RunMarkdownFlowDTO:
        return RunMarkdownFlowDTO(
            outline_bid=self.outline_bid,
            generated_block_bid=self.generated_block_bid,
            type=GeneratedType.ASK,
            content=question,
            anchor_element_bid=anchor_element_bid,
        )

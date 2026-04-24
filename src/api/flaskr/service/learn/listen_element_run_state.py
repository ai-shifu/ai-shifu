from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from flaskr.service.learn.learn_dtos import (
    ElementAudioDTO,
    ElementType,
)


def _mdflow_new_stream_is_new(element_type: ElementType) -> bool:
    return element_type != ElementType.DIFF


@dataclass
class BlockMeta:
    progress_record_bid: str = ""
    role: str = "teacher"


@dataclass
class StreamElementState:
    number: int
    element_bid: str
    element_index: int
    element_type: ElementType
    stream_type: str = ""
    content_text: str = ""


@dataclass
class BlockState:
    generated_block_bid: str
    raw_content: str = ""
    audio_by_position: dict[int, ElementAudioDTO] = field(default_factory=dict)
    live_audio_by_position: dict[int, ElementAudioDTO] = field(default_factory=dict)
    audio_segments_by_position: dict[int, list[dict[str, Any]]] = field(
        default_factory=dict
    )
    audio_target_element_bid_by_position: dict[int, str] = field(default_factory=dict)
    pending_stream_audio_target_by_position: dict[int, tuple[int, str]] = field(
        default_factory=dict
    )
    fallback_element_bid: str | None = None
    latest_av_contract: dict[str, Any] | None = None
    stream_elements: OrderedDict[str, StreamElementState] = field(
        default_factory=OrderedDict
    )
    active_stream_element_key_by_number: dict[int, str] = field(default_factory=dict)
    last_stream_element_key: str | None = None

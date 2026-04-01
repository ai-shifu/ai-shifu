from __future__ import annotations

import json
from typing import Any

from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    AudioSegmentDTO,
    ElementAudioDTO,
    ElementPayloadDTO,
    ElementType,
    SubtitleCueDTO,
    ElementVisualDTO,
)
from flaskr.service.tts.subtitle_utils import normalize_subtitle_cues
from flaskr.service.learn.listen_element_types import _visual_type_for_element


def _payload_from_stream_element(
    element_type: ElementType,
    content: str,
    *,
    audio: ElementAudioDTO | None = None,
) -> ElementPayloadDTO:
    visual_type = _visual_type_for_element(element_type)
    previous_visuals = []
    if visual_type and content:
        previous_visuals.append(
            ElementVisualDTO(visual_type=visual_type, content=content)
        )
    return ElementPayloadDTO(audio=audio, previous_visuals=previous_visuals)


def _serialize_payload(payload: ElementPayloadDTO | None) -> str:
    if payload is None:
        return ""
    return json.dumps(payload.__json__(), ensure_ascii=False)


def _deserialize_payload(raw_payload: str) -> ElementPayloadDTO:
    if not raw_payload:
        return ElementPayloadDTO()
    try:
        payload_dict = json.loads(raw_payload)
    except Exception:
        return ElementPayloadDTO()
    audio_dict = payload_dict.get("audio")
    audio = None
    if isinstance(audio_dict, dict):
        subtitle_cues = [
            SubtitleCueDTO(**cue)
            for cue in normalize_subtitle_cues(audio_dict.get("subtitle_cues"))
        ]
        audio = ElementAudioDTO(
            audio_url=str(audio_dict.get("audio_url", "") or ""),
            audio_bid=str(audio_dict.get("audio_bid", "") or ""),
            duration_ms=int(audio_dict.get("duration_ms", 0) or 0),
            position=int(audio_dict.get("position", 0) or 0),
            subtitle_cues=subtitle_cues,
        )
    visuals = []
    for item in payload_dict.get("previous_visuals") or []:
        if not isinstance(item, dict):
            continue
        visuals.append(
            ElementVisualDTO(
                visual_type=str(item.get("visual_type", "") or ""),
                content=str(item.get("content", "") or ""),
            )
        )
    diff_payload = payload_dict.get("diff_payload")
    if not isinstance(diff_payload, list):
        diff_payload = None
    anchor_element_bid = payload_dict.get("anchor_element_bid")
    if anchor_element_bid is not None:
        anchor_element_bid = str(anchor_element_bid or "")
    ask_element_bid = payload_dict.get("ask_element_bid")
    if ask_element_bid is not None:
        ask_element_bid = str(ask_element_bid or "")
    user_input = payload_dict.get("user_input")
    if user_input is not None:
        user_input = str(user_input or "")
    asks = payload_dict.get("asks")
    if not isinstance(asks, list):
        asks = None
    return ElementPayloadDTO(
        audio=audio,
        previous_visuals=visuals,
        anchor_element_bid=anchor_element_bid,
        ask_element_bid=ask_element_bid,
        user_input=user_input,
        diff_payload=diff_payload,
        asks=asks,
    )


def _audio_segment_payload(audio_segment: AudioSegmentDTO) -> dict[str, Any]:
    return {
        "position": int(getattr(audio_segment, "position", 0) or 0),
        "segment_index": int(audio_segment.segment_index or 0),
        "audio_data": str(audio_segment.audio_data or ""),
        "duration_ms": int(audio_segment.duration_ms or 0),
        "is_final": bool(getattr(audio_segment, "is_final", False)),
    }


def _upsert_audio_segment_payload(
    audio_segments: list[dict[str, Any]] | None,
    incoming_segment: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    normalized = _clone_audio_segments(audio_segments)
    if not isinstance(incoming_segment, dict):
        return normalized

    incoming_position = int(incoming_segment.get("position", 0) or 0)
    incoming_index = int(incoming_segment.get("segment_index", 0) or 0)
    incoming_audio_data = str(incoming_segment.get("audio_data", "") or "")
    incoming_duration_ms = int(incoming_segment.get("duration_ms", 0) or 0)
    incoming_is_final = bool(incoming_segment.get("is_final", False))

    for idx, existing in enumerate(normalized):
        existing_position = int(existing.get("position", 0) or 0)
        existing_index = int(existing.get("segment_index", 0) or 0)
        if existing_position != incoming_position or existing_index != incoming_index:
            continue

        merged = dict(existing)
        merged["position"] = incoming_position
        merged["segment_index"] = incoming_index
        merged["audio_data"] = incoming_audio_data or str(
            existing.get("audio_data", "") or ""
        )
        merged["duration_ms"] = int(
            incoming_duration_ms or existing.get("duration_ms", 0) or 0
        )
        merged["is_final"] = bool(existing.get("is_final", False) or incoming_is_final)
        normalized[idx] = merged
        return normalized

    normalized.append(
        {
            "position": incoming_position,
            "segment_index": incoming_index,
            "audio_data": incoming_audio_data,
            "duration_ms": incoming_duration_ms,
            "is_final": incoming_is_final,
        }
    )
    normalized.sort(
        key=lambda item: (
            int(item.get("position", 0) or 0),
            int(item.get("segment_index", 0) or 0),
        )
    )
    return normalized


def _clone_audio_segments(
    audio_segments: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    cloned: list[dict[str, Any]] = []
    for item in list(audio_segments or []):
        if not isinstance(item, dict):
            continue
        segment = dict(item)
        segment["is_final"] = bool(segment.get("is_final", False))
        cloned.append(segment)
    return cloned


def _normalize_audio_segments_for_element(
    audio_segments: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized = _clone_audio_segments(audio_segments)
    if not normalized:
        return []
    for item in normalized:
        item["is_final"] = False
    normalized[-1]["is_final"] = True
    return normalized


def _preserve_audio_segments_for_element(
    audio_segments: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return _clone_audio_segments(audio_segments)


def _prepare_audio_segments_for_element(
    audio_segments: list[dict[str, Any]] | None,
    *,
    is_final: bool,
) -> list[dict[str, Any]]:
    if is_final:
        return _normalize_audio_segments_for_element(audio_segments)
    return _preserve_audio_segments_for_element(audio_segments)


def _mark_last_audio_segment_final(
    audio_segments_by_position: dict[int, list[dict[str, Any]]],
    position: int,
) -> list[dict[str, Any]]:
    segments = audio_segments_by_position.get(position, [])
    if not segments:
        return []
    finalized_segments = [dict(item) for item in segments]
    finalized_segments[-1]["is_final"] = True
    audio_segments_by_position[position] = finalized_segments
    return finalized_segments


def _sanitize_audio_segments_for_storage(
    audio_segments: list[dict[str, Any]] | None,
    *,
    is_final: bool,
) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for item in _prepare_audio_segments_for_element(
        audio_segments,
        is_final=is_final,
    ):
        sanitized.append(
            {
                "position": int(item.get("position", 0) or 0),
                "segment_index": int(item.get("segment_index", 0) or 0),
                "audio_data": "",
                "duration_ms": int(item.get("duration_ms", 0) or 0),
                "is_final": bool(item.get("is_final", False)),
            }
        )
    return sanitized


def _pick_default_audio_position(
    audio_by_position: dict[int, ElementAudioDTO],
    audio_segments_by_position: dict[int, list[dict[str, Any]]],
) -> int | None:
    if len(audio_by_position) == 1:
        return next(iter(audio_by_position))
    if len(audio_segments_by_position) == 1:
        return next(iter(audio_segments_by_position))
    if 0 in audio_by_position or 0 in audio_segments_by_position:
        return 0
    return None


def _make_audio_payload(audio: AudioCompleteDTO) -> ElementAudioDTO:
    return ElementAudioDTO(
        audio_url=audio.audio_url or "",
        audio_bid=audio.audio_bid or "",
        duration_ms=int(audio.duration_ms or 0),
        position=int(getattr(audio, "position", 0) or 0),
        subtitle_cues=list(getattr(audio, "subtitle_cues", []) or []),
    )

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flaskr.service.learn.block_type_mapping import (
    CONTENT_LIKE_BLOCK_TYPES,
    LIKE_STATUS_MAP,
    map_generated_block_type,
)
from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    BlockType,
    LikeStatus,
)
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.tts.subtitle_utils import normalize_subtitle_cues
from flaskr.service.tts.models import AUDIO_STATUS_COMPLETED, LearnGeneratedAudio


@dataclass
class LegacyGeneratedBlockRecord:
    generated_block_bid: str
    content: str
    like_status: LikeStatus
    block_type: BlockType
    user_input: str
    audio_url: str | None = None
    audios: list[AudioCompleteDTO] | None = None

    def __json__(self):
        ret = {
            "generated_block_bid": self.generated_block_bid,
            "content": self.content,
            "block_type": self.block_type.value,
            "user_input": self.user_input,
        }
        if self.block_type == BlockType.CONTENT:
            ret["like_status"] = self.like_status.value
        if self.audio_url:
            ret["audio_url"] = self.audio_url
        if self.audios:
            ret["audios"] = [
                audio.__json__() if hasattr(audio, "__json__") else audio
                for audio in self.audios
            ]
        return ret


@dataclass
class LegacyLearnRecord:
    records: list[LegacyGeneratedBlockRecord]

    def __json__(self):
        return {
            "records": self.records,
        }


def _set_stat(stats: Any | None, field_name: str, value: int) -> None:
    if stats is not None and hasattr(stats, field_name):
        setattr(stats, field_name, int(value))


def _inc_stat(stats: Any | None, field_name: str, delta: int = 1) -> None:
    if stats is not None and hasattr(stats, field_name):
        current = int(getattr(stats, field_name, 0) or 0)
        setattr(stats, field_name, current + int(delta))


def build_legacy_record_for_progress(
    progress_record: LearnProgressRecord,
    *,
    user_bid: str | None = None,
    shifu_bid: str | None = None,
    outline_bid: str | None = None,
    include_like_status: bool = True,
    dedupe_blocks_by_bid: bool = False,
    dedupe_audio_by_block_position: bool = False,
    skip_empty_content: bool = False,
    stats: Any | None = None,
) -> LegacyLearnRecord:
    filters = [
        LearnGeneratedBlock.progress_record_bid == progress_record.progress_record_bid,
        LearnGeneratedBlock.deleted == 0,
        LearnGeneratedBlock.status == 1,
    ]
    if user_bid is not None:
        filters.append(LearnGeneratedBlock.user_bid == user_bid)
    if shifu_bid is not None:
        filters.append(LearnGeneratedBlock.shifu_bid == shifu_bid)
    if outline_bid is not None:
        filters.append(LearnGeneratedBlock.outline_item_bid == outline_bid)

    generated_blocks: list[LearnGeneratedBlock] = (
        LearnGeneratedBlock.query.filter(*filters)
        .order_by(LearnGeneratedBlock.position.asc(), LearnGeneratedBlock.id.asc())
        .all()
    )
    _set_stat(stats, "generated_blocks_total", len(generated_blocks))

    blocks_for_build = generated_blocks
    if dedupe_blocks_by_bid:
        latest_blocks_by_bid: dict[str, LearnGeneratedBlock] = {}
        for generated_block in generated_blocks:
            if generated_block.generated_block_bid in latest_blocks_by_bid:
                _inc_stat(stats, "duplicate_blocks_skipped")
            latest_blocks_by_bid[generated_block.generated_block_bid] = generated_block
        blocks_for_build = sorted(
            latest_blocks_by_bid.values(),
            key=lambda item: (int(item.position or 0), int(item.id or 0)),
        )

    generated_block_bids = [
        block.generated_block_bid
        for block in blocks_for_build
        if block.generated_block_bid
    ]

    block_audios_map: dict[str, list[AudioCompleteDTO]] = {}
    if dedupe_audio_by_block_position:
        audio_records = (
            LearnGeneratedAudio.query.filter(
                LearnGeneratedAudio.progress_record_bid
                == progress_record.progress_record_bid,
                LearnGeneratedAudio.status == AUDIO_STATUS_COMPLETED,
                LearnGeneratedAudio.deleted == 0,
            )
            .order_by(
                LearnGeneratedAudio.generated_block_bid.asc(),
                LearnGeneratedAudio.position.asc(),
                LearnGeneratedAudio.id.asc(),
            )
            .all()
        )
        _set_stat(stats, "audio_records_total", len(audio_records))

        active_block_bids = set(generated_block_bids)
        latest_audio_by_block_position: dict[tuple[str, int], LearnGeneratedAudio] = {}
        for audio_record in audio_records:
            block_bid = audio_record.generated_block_bid or ""
            position = int(getattr(audio_record, "position", 0) or 0)
            if block_bid not in active_block_bids:
                _inc_stat(stats, "orphan_audios_skipped")
                continue
            dedupe_key = (block_bid, position)
            if dedupe_key in latest_audio_by_block_position:
                _inc_stat(stats, "duplicate_audios_skipped")
            latest_audio_by_block_position[dedupe_key] = audio_record

        for (block_bid, _position), audio_record in sorted(
            latest_audio_by_block_position.items(),
            key=lambda item: (
                item[0][0],
                item[0][1],
                int(item[1].id or 0),
            ),
        ):
            block_audios_map.setdefault(block_bid, []).append(
                AudioCompleteDTO(
                    audio_url=audio_record.oss_url or "",
                    audio_bid=audio_record.audio_bid or "",
                    duration_ms=int(audio_record.duration_ms or 0),
                    position=int(getattr(audio_record, "position", 0) or 0),
                    subtitle_cues=normalize_subtitle_cues(
                        getattr(audio_record, "subtitle_cues", None)
                    ),
                )
            )
    elif generated_block_bids:
        audio_records = (
            LearnGeneratedAudio.query.filter(
                LearnGeneratedAudio.generated_block_bid.in_(generated_block_bids),
                LearnGeneratedAudio.status == AUDIO_STATUS_COMPLETED,
                LearnGeneratedAudio.deleted == 0,
            )
            .order_by(
                LearnGeneratedAudio.generated_block_bid.asc(),
                LearnGeneratedAudio.position.asc(),
                LearnGeneratedAudio.id.asc(),
            )
            .all()
        )
        for audio in audio_records:
            position = int(getattr(audio, "position", 0) or 0)
            block_audios_map.setdefault(audio.generated_block_bid, []).append(
                AudioCompleteDTO(
                    audio_url=audio.oss_url or "",
                    audio_bid=audio.audio_bid or "",
                    duration_ms=int(audio.duration_ms or 0),
                    position=position,
                    subtitle_cues=normalize_subtitle_cues(
                        getattr(audio, "subtitle_cues", None)
                    ),
                )
            )

    records: list[LegacyGeneratedBlockRecord] = []
    for generated_block in blocks_for_build:
        block_type = map_generated_block_type(
            generated_block.type,
            generated_block.role,
        )
        content = (
            generated_block.generated_content
            if block_type in CONTENT_LIKE_BLOCK_TYPES
            else generated_block.block_content_conf
        )
        if skip_empty_content and not (content or "").strip():
            _inc_stat(stats, "skipped_empty_blocks")
            continue

        block_audios = block_audios_map.get(generated_block.generated_block_bid) or []
        records.append(
            LegacyGeneratedBlockRecord(
                generated_block_bid=generated_block.generated_block_bid,
                content=content,
                like_status=(
                    LIKE_STATUS_MAP.get(generated_block.liked, LikeStatus.NONE)
                    if include_like_status
                    else LikeStatus.NONE
                ),
                block_type=block_type,
                user_input=(
                    generated_block.generated_content
                    if block_type == BlockType.INTERACTION
                    else ""
                ),
                audio_url=block_audios[0].audio_url if len(block_audios) == 1 else None,
                audios=block_audios or None,
            )
        )

    return LegacyLearnRecord(records=records)

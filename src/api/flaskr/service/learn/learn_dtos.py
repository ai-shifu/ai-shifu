from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from flaskr.common.swagger import register_schema_to_swagger
from pydantic import BaseModel, Field


@register_schema_to_swagger
class LearnStatus(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    LOCKED = "locked"

    def __json__(self):
        return self.value


@register_schema_to_swagger
class OutlineType(Enum):
    NORMAL = "normal"
    TRIAL = "trial"
    GUEST = "guest"

    def __json__(self):
        return self.value


@register_schema_to_swagger
class GeneratedType(Enum):
    CONTENT = "content"
    BREAK = "break"
    INTERACTION = "interaction"
    VARIABLE_UPDATE = "variable_update"
    OUTLINE_ITEM_UPDATE = "outline_item_update"
    DONE = "done"
    # Audio types for TTS
    AUDIO_SEGMENT = "audio_segment"
    AUDIO_COMPLETE = "audio_complete"

    def __json__(self):
        return self.value


@register_schema_to_swagger
class PreviewMode(Enum):
    PREVIEW = "preview"
    COOK = "cook"
    NORMAL = "normal"

    def __json__(self):
        return self.value


@register_schema_to_swagger
class LikeStatus(Enum):
    LIKE = "like"
    DISLIKE = "dislike"
    NONE = "none"

    def __json__(self):
        return self.value


@register_schema_to_swagger
class BlockType(Enum):
    CONTENT = "content"
    INTERACTION = "interaction"
    ERROR_MESSAGE = "error_message"
    ASK = "ask"
    ANSWER = "answer"

    def __json__(self):
        return self.value


@register_schema_to_swagger
class VariableUpdateDTO(BaseModel):
    variable_name: str = Field(..., description="variable name", required=False)
    variable_value: str = Field(..., description="variable value", required=False)

    def __init__(
        self,
        variable_name: str,
        variable_value: str,
    ):
        super().__init__(variable_name=variable_name, variable_value=variable_value)

    def __json__(self):
        return {
            "variable_name": self.variable_name,
            "variable_value": self.variable_value,
        }


@register_schema_to_swagger
class OutlineItemUpdateDTO(BaseModel):
    outline_bid: str = Field(..., description="outline item id", required=False)
    title: str = Field(..., description="outline item name", required=False)
    status: LearnStatus = Field(..., description="outline item status", required=False)
    has_children: bool = Field(
        ..., description="outline item has children", required=False
    )

    def __init__(
        self,
        outline_bid: str,
        title: str,
        status: LearnStatus,
        has_children: bool,
    ):
        super().__init__(
            outline_bid=outline_bid,
            title=title,
            status=status,
            has_children=has_children,
        )

    def __json__(self):
        return {
            "outline_bid": self.outline_bid,
            "title": self.title,
            "status": self.status.value,
            "has_children": self.has_children,
        }


@register_schema_to_swagger
class LearnShifuInfoDTO(BaseModel):
    bid: str = Field(..., description="shifu id", required=False)
    title: str = Field(..., description="shifu title", required=False)
    description: str = Field(..., description="shifu description", required=False)
    keywords: list[str] = Field(..., description="shifu keywords", required=False)
    avatar: str = Field(..., description="shifu avatar", required=False)
    price: str = Field(..., description="shifu price", required=False)
    tts_enabled: bool = Field(False, description="tts enabled", required=False)

    def __init__(
        self,
        bid: str,
        title: str,
        description: str,
        keywords: list[str],
        avatar: str,
        price: str,
        tts_enabled: bool = False,
    ):
        super().__init__(
            bid=bid,
            title=title,
            description=description,
            keywords=keywords,
            avatar=avatar,
            price=price,
            tts_enabled=tts_enabled,
        )

    def __json__(self):
        return {
            "bid": self.bid,
            "title": self.title,
            "description": self.description,
            "keywords": self.keywords,
            "avatar": self.avatar,
            "price": self.price,
            "tts_enabled": self.tts_enabled,
        }


class LearnBannerInfoDTO(BaseModel):
    title: str = Field(..., description="banner title", required=False)
    pop_up_title: str = Field(..., description="banner pop up title", required=False)
    pop_up_content: str = Field(
        ..., description="banner pop up content", required=False
    )
    pop_up_confirm_text: str = Field(
        ..., description="banner pop up confirm text", required=False
    )
    pop_up_cancel_text: str = Field(
        ..., description="banner pop up cancel text", required=False
    )

    def __init__(
        self,
        title: str,
        pop_up_title: str,
        pop_up_content: str,
        pop_up_confirm_text: str,
        pop_up_cancel_text: str,
    ):
        super().__init__(
            title=title,
            pop_up_title=pop_up_title,
            pop_up_content=pop_up_content,
            pop_up_confirm_text=pop_up_confirm_text,
            pop_up_cancel_text=pop_up_cancel_text,
        )

    def __json__(self):
        return {
            "title": self.title,
            "pop_up_title": self.pop_up_title,
            "pop_up_content": self.pop_up_content,
            "pop_up_confirm_text": self.pop_up_confirm_text,
            "pop_up_cancel_text": self.pop_up_cancel_text,
        }


@register_schema_to_swagger
class LearnOutlineItemInfoDTO(BaseModel):
    bid: str = Field(..., description="outline id", required=False)
    position: str = Field(..., description="outline position", required=False)
    title: str = Field(..., description="outline title", required=False)
    status: LearnStatus = Field(..., description="outline status", required=False)
    type: OutlineType = Field(..., description="outline type", required=False)
    is_paid: bool = Field(..., description="outline is paid", required=False)
    children: list["LearnOutlineItemInfoDTO"] = Field(
        ..., description="outline children", required=False
    )

    def __init__(
        self,
        bid: str,
        position: str,
        title: str,
        status: LearnStatus,
        type: OutlineType,
        is_paid: bool,
        children: list["LearnOutlineItemInfoDTO"],
    ):
        super().__init__(
            bid=bid,
            position=position,
            title=title,
            status=status,
            children=children,
            type=type,
            is_paid=is_paid,
        )

    def __json__(self):
        return {
            "bid": self.bid,
            "position": self.position,
            "title": self.title,
            "status": self.status.value,
            "is_paid": self.is_paid,
            "children": self.children,
            "type": self.type.value,
        }


@register_schema_to_swagger
class LearnOutlineItemsWithBannerInfoDTO(BaseModel):
    banner_info: LearnBannerInfoDTO | None = Field(
        ..., description="banner info", required=False
    )
    outline_items: list[LearnOutlineItemInfoDTO] = Field(
        ..., description="outline items", required=True
    )

    def __init__(
        self,
        banner_info: LearnBannerInfoDTO | None,
        outline_items: list[LearnOutlineItemInfoDTO],
    ):
        super().__init__(
            banner_info=banner_info,
            outline_items=outline_items,
        )

    def __json__(self):
        return {
            "banner_info": None
            if self.banner_info is None
            else self.banner_info.__json__(),
            "outline_items": self.outline_items,
        }


@register_schema_to_swagger
class AudioSegmentDTO(BaseModel):
    """DTO for streaming audio segment during TTS synthesis."""

    position: int = Field(
        default=0, description="Audio position within the block (0-based)"
    )
    segment_index: int = Field(..., description="Segment sequence number")
    audio_data: str = Field(..., description="Base64-encoded audio data")
    duration_ms: int = Field(default=0, description="Segment duration in milliseconds")
    is_final: bool = Field(
        default=False, description="Whether this is the last segment"
    )

    def __init__(
        self,
        segment_index: int,
        audio_data: str,
        duration_ms: int = 0,
        is_final: bool = False,
        position: int = 0,
    ):
        super().__init__(
            position=position,
            segment_index=segment_index,
            audio_data=audio_data,
            duration_ms=duration_ms,
            is_final=is_final,
        )

    def __json__(self):
        return {
            "position": self.position,
            "segment_index": self.segment_index,
            "audio_data": self.audio_data,
            "duration_ms": self.duration_ms,
            "is_final": self.is_final,
        }


@register_schema_to_swagger
class AudioCompleteDTO(BaseModel):
    """DTO for completed TTS audio with OSS URL."""

    position: int = Field(
        default=0, description="Audio position within the block (0-based)"
    )
    audio_url: str = Field(..., description="OSS URL of complete audio")
    audio_bid: str = Field(..., description="Audio business identifier")
    duration_ms: int = Field(..., description="Total audio duration in milliseconds")

    def __init__(
        self,
        audio_url: str,
        audio_bid: str,
        duration_ms: int,
        position: int = 0,
    ):
        super().__init__(
            position=position,
            audio_url=audio_url,
            audio_bid=audio_bid,
            duration_ms=duration_ms,
        )

    def __json__(self):
        return {
            "position": self.position,
            "audio_url": self.audio_url,
            "audio_bid": self.audio_bid,
            "duration_ms": self.duration_ms,
        }


@register_schema_to_swagger
class RunMarkdownFlowDTO(BaseModel):
    outline_bid: str = Field(..., description="outline id", required=False)
    generated_block_bid: str = Field(
        ..., description="generated block id", required=False
    )
    type: GeneratedType = Field(..., description="generated type", required=False)
    content: Union[
        str, VariableUpdateDTO, OutlineItemUpdateDTO, AudioSegmentDTO, AudioCompleteDTO
    ] = Field(..., description="generated content", required=True)

    def __init__(
        self,
        outline_bid: str,
        generated_block_bid: str,
        type: GeneratedType,
        content: Union[
            str,
            VariableUpdateDTO,
            OutlineItemUpdateDTO,
            AudioSegmentDTO,
            AudioCompleteDTO,
        ],
    ):
        super().__init__(
            outline_bid=outline_bid,
            generated_block_bid=generated_block_bid,
            type=type,
            content=content,
        )

    def __json__(self):
        return {
            "outline_bid": self.outline_bid,
            "generated_block_bid": self.generated_block_bid,
            "type": self.type.value,
            "content": self.content.__json__()
            if isinstance(self.content, BaseModel)
            else self.content,
        }


@register_schema_to_swagger
class GeneratedBlockDTO(BaseModel):
    generated_block_bid: str = Field(
        ..., description="generated block id", required=False
    )
    content: str = Field(..., description="generated content", required=False)
    like_status: LikeStatus = Field(..., description="like status", required=False)
    block_type: BlockType = Field(..., description="block type", required=False)
    user_input: str = Field(..., description="user input", required=False)
    audio_url: Optional[str] = Field(
        default=None, description="TTS audio URL for this block"
    )
    audios: Optional[List[AudioCompleteDTO]] = Field(
        default=None, description="TTS audio segments for this block"
    )

    def __init__(
        self,
        generated_block_bid: str,
        content: str,
        like_status: LikeStatus,
        block_type: BlockType,
        user_input: str,
        audio_url: Optional[str] = None,
        audios: Optional[List[AudioCompleteDTO]] = None,
    ):
        super().__init__(
            generated_block_bid=generated_block_bid,
            content=content,
            like_status=like_status,
            block_type=block_type,
            user_input=user_input,
            audio_url=audio_url,
            audios=audios,
        )

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
                audio.__json__() if isinstance(audio, BaseModel) else audio
                for audio in self.audios
            ]
        return ret


class PlaygroundPreviewRequest(BaseModel):
    content: Optional[str] = Field(
        default=None, description="Markdown-Flow document content"
    )
    block_index: int = Field(..., description="Block index to preview")
    context: Optional[List[Dict[str, str]]] = Field(
        default=None, description="Conversation context messages"
    )
    variables: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Variables to replace inside Markdown-Flow document",
    )
    user_input: Optional[Dict[str, List[str]]] = Field(
        default=None, description="User input when previewing interaction blocks"
    )
    document_prompt: Optional[str] = Field(
        default=None, description="Document level system prompt"
    )
    interaction_prompt: Optional[str] = Field(
        default=None, description="Interaction render prompt override"
    )
    interaction_error_prompt: Optional[str] = Field(
        default=None, description="Interaction error prompt override"
    )
    model: Optional[str] = Field(
        default=None, description="Target LLM model used during preview"
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="LLM temperature override used during preview",
    )

    def get_document(self) -> str:
        return self.content or ""


class PreviewSSEMessageType(Enum):
    CONTENT = "content"
    INTERACTION = "interaction"
    TEXT_END = "text_end"
    ERROR = "error"
    # Audio types for TTS (same literals as GeneratedType for consistency)
    AUDIO_SEGMENT = "audio_segment"
    AUDIO_COMPLETE = "audio_complete"

    def __json__(self):
        return self.value


class PreviewContentSSEData(BaseModel):
    mdflow: str = Field(..., description="MarkdownFlow content chunk")


class PreviewInteractionSSEData(BaseModel):
    mdflow: str = Field(..., description="Rendered interaction content")
    variable: str = Field(..., description="Target variable name for interaction")


class PreviewTextEndSSEData(BaseModel):
    mdflow: str = Field(default="", description="Text end marker payload")


class PreviewSSEMessage(BaseModel):
    generated_block_bid: str = Field(
        ..., description="client-side identifier of the block", required=True
    )
    type: PreviewSSEMessageType = Field(..., description="SSE message type")
    data: (
        PreviewContentSSEData
        | PreviewInteractionSSEData
        | PreviewTextEndSSEData
        | AudioSegmentDTO
        | AudioCompleteDTO
        | str
    )

    def __json__(self):
        payload = self.model_dump()
        payload["type"] = self.type.value
        return payload


@register_schema_to_swagger
class LearnRecordDTO(BaseModel):
    records: list[GeneratedBlockDTO] = Field(
        ..., description="generated blocks", required=False
    )
    interaction: str = Field(..., description="interaction", required=False)

    def __init__(
        self,
        records: list[GeneratedBlockDTO],
        interaction: str,
    ):
        super().__init__(records=records, interaction=interaction)

    def __json__(self):
        return {
            "records": self.records,
            "interaction": self.interaction,
        }


@register_schema_to_swagger
class RunStatusDTO(BaseModel):
    is_running: bool = Field(..., description="is running", required=False)
    running_time: int = Field(..., description="running time", required=False)

    def __init__(
        self,
        is_running: bool,
        running_time: int,
    ):
        super().__init__(is_running=is_running, running_time=running_time)

    def __json__(self):
        return {
            "is_running": self.is_running,
            "running_time": self.running_time,
        }


@register_schema_to_swagger
class GeneratedInfoDTO(BaseModel):
    position: int = Field(..., description="generated block position", required=False)
    outline_name: str = Field(..., description="outline item name", required=False)
    is_trial_lesson: bool = Field(
        ..., description="whether the outline item is a trial lesson", required=False
    )

    def __init__(
        self,
        position: int,
        outline_name: str,
        is_trial_lesson: bool,
    ):
        super().__init__(
            position=position,
            outline_name=outline_name,
            is_trial_lesson=is_trial_lesson,
        )

    def __json__(self):
        return {
            "position": self.position,
            "outline_name": self.outline_name,
            "is_trial_lesson": self.is_trial_lesson,
        }

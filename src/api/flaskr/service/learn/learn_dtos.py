from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from flaskr.common.swagger import register_schema_to_swagger
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, PrivateAttr


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
    # Internal ask event (listen adapter only, not exposed to non-listen consumers)
    ASK = "ask"

    def __json__(self):
        return self.value


@register_schema_to_swagger
class ElementType(Enum):
    HTML = "html"
    SVG = "svg"
    DIFF = "diff"
    IMG = "img"
    INTERACTION = "interaction"
    ASK = "ask"
    ANSWER = "answer"
    TABLES = "tables"
    CODE = "code"
    LATEX = "latex"
    MD_IMG = "md_img"
    MERMAID = "mermaid"
    TITLE = "title"
    TEXT = "text"

    # Legacy aliases kept for backward-compatible deserialization only.
    # New code must not produce these values.
    _SANDBOX = "sandbox"
    _PICTURE = "picture"
    _VIDEO = "video"

    def __json__(self):
        return self.value


@register_schema_to_swagger
class ElementChangeType(Enum):
    RENDER = "render"
    DIFF = "diff"

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
    av_contract: Dict[str, Any] | None = Field(
        default=None, description="AV boundary contract metadata"
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
        av_contract: Dict[str, Any] | None = None,
    ):
        super().__init__(
            position=position,
            av_contract=av_contract,
            segment_index=segment_index,
            audio_data=audio_data,
            duration_ms=duration_ms,
            is_final=is_final,
        )

    def __json__(self):
        ret = {
            "position": self.position,
            "segment_index": self.segment_index,
            "audio_data": self.audio_data,
            "duration_ms": self.duration_ms,
            "is_final": self.is_final,
        }
        if self.av_contract is not None:
            ret["av_contract"] = self.av_contract
        return ret


@register_schema_to_swagger
class AudioCompleteDTO(BaseModel):
    """DTO for completed TTS audio with OSS URL."""

    position: int = Field(
        default=0, description="Audio position within the block (0-based)"
    )
    av_contract: Dict[str, Any] | None = Field(
        default=None, description="AV boundary contract metadata"
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
        av_contract: Dict[str, Any] | None = None,
    ):
        super().__init__(
            position=position,
            av_contract=av_contract,
            audio_url=audio_url,
            audio_bid=audio_bid,
            duration_ms=duration_ms,
        )

    def __json__(self):
        ret = {
            "position": self.position,
            "audio_url": self.audio_url,
            "audio_bid": self.audio_bid,
            "duration_ms": self.duration_ms,
        }
        if self.av_contract is not None:
            ret["av_contract"] = self.av_contract
        return ret


@register_schema_to_swagger
class ElementVisualDTO(BaseModel):
    visual_type: str = Field(..., description="Visual payload type", required=False)
    content: str = Field(..., description="Visual payload content", required=False)

    def __init__(self, visual_type: str, content: str):
        super().__init__(visual_type=visual_type, content=content)

    def __json__(self):
        return {"visual_type": self.visual_type, "content": self.content}


@register_schema_to_swagger
class ElementAudioDTO(BaseModel):
    position: int = Field(
        default=0, description="Audio position within the element", required=False
    )
    audio_url: str = Field(..., description="Audio URL", required=False)
    audio_bid: str = Field(..., description="Audio business identifier", required=False)
    duration_ms: int = Field(..., description="Audio duration in ms", required=False)

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
            "position": int(self.position or 0),
            "audio_url": self.audio_url,
            "audio_bid": self.audio_bid,
            "duration_ms": int(self.duration_ms or 0),
        }


@register_schema_to_swagger
class ElementPayloadDTO(BaseModel):
    audio: ElementAudioDTO | None = Field(
        default=None, description="Final merged audio payload"
    )
    previous_visuals: List[ElementVisualDTO] = Field(
        default_factory=list, description="Visual snapshots for the element"
    )
    anchor_element_bid: str | None = Field(
        default=None,
        description="Anchor element bid for ask sidecar elements",
    )
    ask_element_bid: str | None = Field(
        default=None,
        description="Ask element bid referenced by answer sidecar elements",
    )
    user_input: str | None = Field(
        default=None,
        description="Interaction user input when available",
    )
    diff_payload: List[Dict[str, Any]] | None = Field(
        default=None, description="Optional diff payload for incremental updates"
    )
    asks: List[Dict[str, Any]] | None = Field(
        default=None,
        description="Ask Q&A pairs embedded in anchor element",
    )

    def __init__(
        self,
        audio: ElementAudioDTO | None = None,
        previous_visuals: Optional[List[ElementVisualDTO]] = None,
        anchor_element_bid: str | None = None,
        ask_element_bid: str | None = None,
        user_input: str | None = None,
        diff_payload: List[Dict[str, Any]] | None = None,
        asks: List[Dict[str, Any]] | None = None,
    ):
        super().__init__(
            audio=audio,
            previous_visuals=previous_visuals or [],
            anchor_element_bid=anchor_element_bid,
            ask_element_bid=ask_element_bid,
            user_input=user_input,
            diff_payload=diff_payload,
            asks=asks,
        )

    def __json__(self):
        ret = {
            "audio": self.audio.__json__() if self.audio is not None else None,
            "previous_visuals": [
                item.__json__() if isinstance(item, BaseModel) else item
                for item in self.previous_visuals
            ],
        }
        if self.anchor_element_bid is not None:
            ret["anchor_element_bid"] = self.anchor_element_bid
        if self.ask_element_bid is not None:
            ret["ask_element_bid"] = self.ask_element_bid
        if self.diff_payload is not None:
            ret["diff_payload"] = self.diff_payload
        if self.user_input is not None:
            ret["user_input"] = self.user_input
        if self.asks is not None:
            ret["asks"] = self.asks
        return ret


@register_schema_to_swagger
class ElementDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    run_session_bid: str | None = Field(
        default=None, description="Run session business identifier"
    )
    run_event_seq: int | None = Field(default=None, description="Run event sequence")
    event_type: str = Field(default="element", description="Element event type")
    element_bid: str = Field(..., description="Element business identifier")
    generated_block_bid: str = Field(
        default="", description="Source generated block identifier"
    )
    element_index: int = Field(..., description="Global element order index")
    role: str = Field(..., description="Element role")
    element_type: ElementType = Field(..., description="Element type")
    element_type_code: int = Field(..., description="Element type code")
    change_type: ElementChangeType | None = Field(
        default=None, description="Optional change type"
    )
    target_element_bid: str | None = Field(
        default=None, description="Diff target element identifier"
    )
    is_renderable: bool = Field(
        default=True, description="Whether this element participates in rendering"
    )
    is_new: bool = Field(
        default=True,
        description="Whether this creates a new element; false means patch to existing",
    )
    is_marker: bool = Field(
        default=False,
        description="Whether this is a forward/backward navigation anchor",
    )
    sequence_number: int = Field(
        default=0, description="Element generation sequence within the run session"
    )
    is_speakable: bool = Field(
        default=False, description="Whether this element needs TTS synthesis"
    )
    audio_url: str = Field(
        default="", description="Complete audio URL; empty until audio is finalized"
    )
    audio_segments: List[Dict[str, Any]] = Field(
        default_factory=list, description="Streaming audio segment trail"
    )
    is_navigable: int = Field(default=1, description="Navigation flag")
    is_final: bool = Field(default=False, description="Final snapshot flag")
    content: str = Field(
        default="",
        description="Element content snapshot",
        validation_alias=AliasChoices("content", "content_text"),
    )
    payload: ElementPayloadDTO | None = Field(
        default=None, description="Element payload"
    )

    @property
    def content_text(self) -> str:
        return self.content

    @content_text.setter
    def content_text(self, value: str) -> None:
        object.__setattr__(self, "content", value or "")

    _PATCH_FIELDS = (
        "is_renderable",
        "content",
        "is_speakable",
        "audio_url",
        "audio_segments",
        "payload",
        "is_navigable",
        "is_final",
        "run_session_bid",
        "run_event_seq",
        "sequence_number",
    )

    def apply_patch(self, patch: "ElementDTO") -> None:
        for field_name in self._PATCH_FIELDS:
            setattr(self, field_name, getattr(patch, field_name))

    def __json__(self):
        ret = {
            "event_type": self.event_type,
            "element_bid": self.element_bid,
            "generated_block_bid": self.generated_block_bid,
            "element_index": int(self.element_index or 0),
            "role": self.role,
            "element_type": self.element_type.value,
            "element_type_code": int(self.element_type_code or 0),
            "is_renderable": self.is_renderable,
            "is_new": self.is_new,
            "is_marker": self.is_marker,
            "sequence_number": int(self.sequence_number or 0),
            "is_speakable": self.is_speakable,
            "audio_url": self.audio_url or "",
            "audio_segments": self.audio_segments,
            "is_navigable": int(self.is_navigable or 0),
            "is_final": bool(self.is_final),
            "content": self.content or "",
            "payload": self.payload.__json__() if self.payload is not None else None,
        }
        if self.run_session_bid is not None:
            ret["run_session_bid"] = self.run_session_bid
        if self.run_event_seq is not None:
            ret["run_event_seq"] = int(self.run_event_seq)
        if self.change_type is not None:
            ret["change_type"] = self.change_type.value
        if self.target_element_bid:
            ret["target_element_bid"] = self.target_element_bid
        return ret


@register_schema_to_swagger
class RunElementSSEMessageDTO(BaseModel):
    type: str = Field(..., description="Run event type")
    event_type: str = Field(..., description="Run event type mirror")
    generated_block_bid: str | None = Field(
        default=None, description="Source generated block identifier"
    )
    run_session_bid: str | None = Field(
        default=None, description="Run session business identifier"
    )
    run_event_seq: int | None = Field(default=None, description="Run event sequence")
    is_terminal: bool | None = Field(
        default=None,
        description="Whether this event marks the terminal end of the run stream",
    )
    content: Union[
        str,
        ElementDTO,
        VariableUpdateDTO,
        OutlineItemUpdateDTO,
        AudioSegmentDTO,
        AudioCompleteDTO,
    ] = Field(..., description="Run event content")

    def __json__(self):
        ret = {
            "type": self.type,
            "event_type": self.event_type,
            "content": self.content.__json__()
            if isinstance(self.content, BaseModel)
            else self.content,
        }
        if self.generated_block_bid is not None:
            ret["generated_block_bid"] = self.generated_block_bid
        if self.run_session_bid is not None:
            ret["run_session_bid"] = self.run_session_bid
        if self.run_event_seq is not None:
            ret["run_event_seq"] = int(self.run_event_seq)
        if self.is_terminal is not None:
            ret["is_terminal"] = bool(self.is_terminal)
        return ret


@register_schema_to_swagger
class RunMarkdownFlowDTO(BaseModel):
    _mdflow_stream_parts: list[tuple[str, str, int]] = PrivateAttr(default_factory=list)

    outline_bid: str = Field(..., description="outline id", required=False)
    generated_block_bid: str = Field(
        ..., description="generated block id", required=False
    )
    type: GeneratedType = Field(..., description="generated type", required=False)
    content: Union[
        str,
        VariableUpdateDTO,
        OutlineItemUpdateDTO,
        AudioSegmentDTO,
        AudioCompleteDTO,
    ] = Field(..., description="generated content", required=True)
    anchor_element_bid: str = Field(
        default="",
        description="Anchor element bid for ASK events",
    )

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
        anchor_element_bid: str = "",
    ):
        super().__init__(
            outline_bid=outline_bid,
            generated_block_bid=generated_block_bid,
            type=type,
            content=content,
            anchor_element_bid=anchor_element_bid,
        )

    def set_mdflow_stream_parts(
        self, parts: list[tuple[str, str, int]] | None
    ) -> "RunMarkdownFlowDTO":
        normalized_parts: list[tuple[str, str, int]] = []
        for item in parts or []:
            if not isinstance(item, tuple) or len(item) != 3:
                continue
            content, stream_type, stream_number = item
            content_text = str(content or "")
            stream_type_text = str(stream_type or "")
            if not content_text or not stream_type_text:
                continue
            try:
                normalized_number = int(stream_number)
            except (TypeError, ValueError):
                continue
            normalized_parts.append((content_text, stream_type_text, normalized_number))
        self._mdflow_stream_parts = normalized_parts
        return self

    def get_mdflow_stream_parts(self) -> list[tuple[str, str, int]]:
        return list(self._mdflow_stream_parts)

    def __json__(self):
        ret = {
            "outline_bid": self.outline_bid,
            "generated_block_bid": self.generated_block_bid,
            "type": self.type.value,
            "content": self.content.__json__()
            if isinstance(self.content, BaseModel)
            else self.content,
        }
        if self.anchor_element_bid:
            ret["anchor_element_bid"] = self.anchor_element_bid
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
    visual_mode: bool = Field(
        default=False,
        description="Whether to enable MarkdownFlow visual mode for preview",
    )

    def get_document(self) -> str:
        return self.content or ""


@register_schema_to_swagger
class LearnElementRecordDTO(BaseModel):
    elements: List[ElementDTO] = Field(
        default_factory=list, description="Listen-mode final element snapshots"
    )
    events: Optional[List[RunElementSSEMessageDTO]] = Field(
        default=None, description="Optional listen-mode event stream replay"
    )

    def __init__(
        self,
        elements: Optional[List[ElementDTO]] = None,
        events: Optional[List[RunElementSSEMessageDTO]] = None,
    ):
        super().__init__(elements=elements or [], events=events)

    def __json__(self):
        ret = {
            "elements": [
                item.__json__() if isinstance(item, BaseModel) else item
                for item in self.elements
            ]
        }
        if self.events is not None:
            ret["events"] = [
                item.__json__() if isinstance(item, BaseModel) else item
                for item in self.events
            ]
        return ret


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

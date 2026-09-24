"""Shifu dtos.

This module contains dtos for shifu.

Author: yfge
Date: 2025-08-07
"""

from typing import Any, Literal

from flask import Flask
from flaskr.common.swagger import register_schema_to_swagger
from flaskr.service.shifu.models import (
    DraftOutlineItem,
)
from pydantic import BaseModel, Field


def resolve_demo_course_for_language(
    app: Flask, language: str | None
) -> dict[str, object]:
    """Resolve demo course for language."""
    from flaskr.service.shifu.demo_courses import (
        resolve_demo_course_for_language as _resolve_demo_course_for_language,
    )

    return _resolve_demo_course_for_language(app, language)


def get_demo_course_title_language(shifu_bid: str) -> str | None:
    """Expose the configured guide title language across service boundaries."""
    from flaskr.service.shifu.demo_courses import (
        get_demo_course_title_language as _get_demo_course_title_language,
    )

    return _get_demo_course_title_language(shifu_bid)


def get_demo_course_content_language(shifu_bid: str) -> str | None:
    """Expose the configured guide output language across service boundaries."""
    from flaskr.service.shifu.demo_courses import (
        get_demo_course_content_language as _get_demo_course_content_language,
    )

    return _get_demo_course_content_language(shifu_bid)


@register_schema_to_swagger
class ShifuDto(BaseModel):
    """Shifu dto."""

    bid: str = Field(..., description="shifu id")
    name: str = Field(..., description="shifu name")
    description: str = Field(..., description="shifu description")
    avatar: str = Field(..., description="shifu avatar")
    state: int = Field(..., description="shifu state")
    is_favorite: bool = Field(..., description="is favorite")
    archived: bool = Field(..., description="is archived")
    can_manage_archive: bool = Field(
        default=False,
        description="whether current user can archive/unarchive",
    )
    can_manage_permissions: bool = Field(
        default=False,
        description="whether current user can manage shared permissions",
    )
    created_user_bid: str = Field("", description="owner user business id")
    is_guide_course: bool = Field(
        default=False,
        description="whether this course is the built-in guide course",
    )

    def __init__(
        self,
        shifu_id: str,
        shifu_name: str,
        shifu_description: str,
        shifu_avatar: str,
        shifu_state: int,
        is_favorite: bool,
        archived: bool,
        can_manage_archive: bool = False,
        can_manage_permissions: bool = False,
        created_user_bid: str = "",
        is_guide_course: bool = False,
    ) -> None:
        """Build the shifu payload."""
        super().__init__(
            bid=shifu_id,
            name=shifu_name,
            description=shifu_description,
            avatar=shifu_avatar,
            state=shifu_state,
            is_favorite=is_favorite,
            archived=archived,
            can_manage_archive=can_manage_archive,
            can_manage_permissions=can_manage_permissions,
            created_user_bid=created_user_bid or "",
            is_guide_course=is_guide_course,
        )

    def __json__(self) -> dict:
        """Return the shifu as JSON-compatible data."""
        return {
            "bid": self.bid,
            "name": self.name,
            "description": self.description,
            "avatar": self.avatar,
            "state": self.state,
            "is_favorite": self.is_favorite,
            "archived": self.archived,
            "can_manage_archive": self.can_manage_archive,
            "can_manage_permissions": self.can_manage_permissions,
            "created_user_bid": self.created_user_bid,
            "is_guide_course": self.is_guide_course,
        }


@register_schema_to_swagger
class ShifuDetailDto(BaseModel):
    """Shifu detail dto."""

    bid: str = Field(..., description="shifu id")
    name: str = Field(..., description="shifu name")
    description: str = Field(..., description="shifu description")
    avatar: str = Field(..., description="shifu avatar")
    keywords: list[str] = Field(..., description="shifu keywords")
    model: str = Field(..., description="shifu model")
    temperature: float = Field(..., description="shifu temperature")
    price: float = Field(..., description="shifu price")
    preview_url: str = Field(..., description="shifu preview url")
    url: str = Field(..., description="shifu url")
    system_prompt: str = Field(..., description="shifu system prompt")
    readonly: bool = Field(..., description="is shifu readonly")
    archived: bool = Field(..., description="is shifu archived")
    can_manage_archive: bool = Field(
        default=False,
        description="whether current user can archive/unarchive",
    )
    can_publish: bool = Field(
        default=False, description="whether current user can publish"
    )
    created_user_bid: str = Field("", description="owner user business id")
    # TTS Configuration
    tts_enabled: bool = Field(default=False, description="TTS enabled")
    tts_provider: str = Field(
        "",
        description="TTS provider: minimax, volcengine, volcengine_http, baidu, aliyun",
    )
    tts_model: str = Field("", description="TTS model/resource ID")
    tts_voice_id: str = Field("", description="TTS voice ID")
    tts_speed: float = Field(
        1.0, description="TTS speech speed (provider-specific range)"
    )
    tts_pitch: int = Field(
        0,
        description="TTS pitch adjustment (provider-specific range)",
    )
    tts_emotion: str = Field("", description="TTS emotion setting")
    default_listen_mode_enabled: bool = Field(
        default=False,
        description="Default learner mode to listen when TTS is enabled",
    )
    use_learner_language: bool = Field(
        default=False,
        description="Use learner language for AI output",
    )
    ask_enabled_status: int = Field(
        5101,
        description="Ask mode status: 5101=default, 5102=disabled, 5103=enabled",
    )
    model_display_name: str = Field("", description="Configured main model label")
    ask_model_display_name: str = Field(
        "", description="Configured text follow-up model label"
    )
    model_fallback: bool = Field(
        default=False,
        description="Whether the main selection currently falls back to model 1",
    )
    ask_model_fallback: bool = Field(
        default=False,
        description="Whether the text follow-up selection falls back to model 1",
    )
    ask_model: str = Field(
        "",
        description="Ask model (maps to ask_llm)",
    )
    ask_temperature: float = Field(
        0.0,
        description="Ask model temperature",
    )
    ask_system_prompt: str = Field(
        "",
        description="Ask model system prompt",
    )
    ask_provider_config: dict[str, Any] = Field(
        default_factory=dict,
        description='Ask provider config, e.g. {"provider":"llm","mode":"provider_then_llm","config":{}}',
    )
    follow_up_mode: Literal["text", "live_voice"] = Field(
        default="text",
        description="Resolved follow-up interaction mode",
    )

    def __init__(
        self,
        shifu_id: str,
        shifu_name: str,
        shifu_description: str,
        shifu_avatar: str,
        shifu_keywords: list[str],
        shifu_model: str,
        shifu_temperature: float,
        shifu_price: float,
        shifu_preview_url: str,
        shifu_url: str,
        shifu_system_prompt: str,
        readonly: bool,
        archived: bool,
        can_manage_archive: bool = False,
        can_publish: bool = False,
        created_user_bid: str = "",
        tts_enabled: bool = False,
        tts_provider: str = "",
        tts_model: str = "",
        tts_voice_id: str = "",
        tts_speed: float = 1.0,
        tts_pitch: int = 0,
        tts_emotion: str = "",
        default_listen_mode_enabled: bool = False,
        use_learner_language: bool = False,
        ask_enabled_status: int = 5101,
        ask_model: str = "",
        ask_temperature: float = 0.0,
        ask_system_prompt: str = "",
        ask_provider_config: dict[str, object] | None = None,
        follow_up_mode: Literal["text", "live_voice"] = "text",
        model_display_name: str = "",
        ask_model_display_name: str = "",
        model_fallback: bool = False,
        ask_model_fallback: bool = False,
    ) -> None:
        """Build the shifu detail payload."""
        super().__init__(
            bid=shifu_id,
            name=shifu_name,
            description=shifu_description,
            avatar=shifu_avatar,
            keywords=shifu_keywords,
            model=shifu_model,
            temperature=shifu_temperature,
            price=shifu_price,
            preview_url=shifu_preview_url,
            url=shifu_url,
            system_prompt=shifu_system_prompt,
            readonly=readonly,
            archived=archived,
            can_manage_archive=can_manage_archive,
            can_publish=can_publish,
            created_user_bid=created_user_bid or "",
            tts_enabled=tts_enabled,
            tts_provider=tts_provider,
            tts_model=tts_model,
            tts_voice_id=tts_voice_id,
            tts_speed=tts_speed,
            tts_pitch=tts_pitch,
            tts_emotion=tts_emotion,
            default_listen_mode_enabled=default_listen_mode_enabled,
            use_learner_language=use_learner_language,
            ask_enabled_status=ask_enabled_status,
            ask_model=ask_model,
            ask_temperature=ask_temperature,
            ask_system_prompt=ask_system_prompt,
            ask_provider_config=ask_provider_config or {},
            follow_up_mode=follow_up_mode,
            model_display_name=model_display_name,
            ask_model_display_name=ask_model_display_name,
            model_fallback=model_fallback,
            ask_model_fallback=ask_model_fallback,
        )

    def __json__(self) -> dict:
        """Return the shifu detail as JSON-compatible data."""
        return {
            "bid": self.bid,
            "name": self.name,
            "description": self.description,
            "avatar": self.avatar,
            "keywords": self.keywords,
            "model": self.model,
            "price": self.price,
            "preview_url": self.preview_url,
            "url": self.url,
            "temperature": self.temperature,
            "system_prompt": self.system_prompt,
            "readonly": self.readonly,
            "archived": self.archived,
            "can_manage_archive": self.can_manage_archive,
            "can_publish": self.can_publish,
            "created_user_bid": self.created_user_bid,
            "tts_enabled": self.tts_enabled,
            "tts_provider": self.tts_provider,
            "tts_model": self.tts_model,
            "tts_voice_id": self.tts_voice_id,
            "tts_speed": self.tts_speed,
            "tts_pitch": self.tts_pitch,
            "tts_emotion": self.tts_emotion,
            "default_listen_mode_enabled": self.default_listen_mode_enabled,
            "use_learner_language": self.use_learner_language,
            "ask_enabled_status": self.ask_enabled_status,
            "ask_model": self.ask_model,
            "ask_temperature": self.ask_temperature,
            "ask_system_prompt": self.ask_system_prompt,
            "ask_provider_config": self.ask_provider_config,
            "follow_up_mode": self.follow_up_mode,
            "model_display_name": self.model_display_name,
            "ask_model_display_name": self.ask_model_display_name,
            "model_fallback": self.model_fallback,
            "ask_model_fallback": self.ask_model_fallback,
        }


@register_schema_to_swagger
class SimpleOutlineDto(BaseModel):
    """Simple outline dto."""

    bid: str = Field(..., description="outline id")
    position: str = Field(..., description="outline position")
    name: str = Field(..., description="outline name")
    children: list["SimpleOutlineDto"] = Field(..., description="outline children")
    type: str | None = Field(None, description="outline type (trial,normal,guest)")
    is_hidden: bool | None = Field(None, description="outline hidden flag")

    def __init__(
        self,
        bid: str,
        position: str,
        name: str,
        children: list,
        type: str | None = None,  # noqa: A002 - serialized DTO field name
        is_hidden: bool | None = None,
    ) -> None:
        """Build the simple outline payload."""
        normalized_children: list[SimpleOutlineDto] = []
        if children:
            for child in children:
                if isinstance(child, SimpleOutlineDto):
                    normalized_children.append(child)
                elif isinstance(child, dict):
                    normalized_children.append(
                        SimpleOutlineDto(
                            child.get("bid"),
                            child.get("position", ""),
                            child.get("name", ""),
                            child.get("children", []),
                            child.get("type"),
                            child.get("is_hidden"),
                        )
                    )
        super().__init__(
            bid=bid,
            position=position,
            name=name,
            children=normalized_children,
            type=type,
            is_hidden=is_hidden,
        )

    def __json__(self) -> dict:
        """Return the simple outline as JSON-compatible data."""
        return {
            "bid": self.bid,
            "position": self.position,
            "name": self.name,
            "children": self.children,
            "type": self.type,
            "is_hidden": self.is_hidden,
        }


# new outline tree node class, for handling DraftOutlineItem
# written by yfge
# date: 2025-07-13
# version: 1.0.0
# description: this class is used to handle DraftOutlineItem
# usage:
# 1. create a new ShifuOutlineTreeNode
# 2. add a child to the node
# 3. remove a child from the node
class ShifuOutlineTreeNode:
    """Shifu outline tree node."""

    def __init__(self, outline_item: DraftOutlineItem) -> None:
        """Build a tree node from a draft outline item."""
        self.outline = outline_item
        self.children = []
        if outline_item:
            self.outline_id = outline_item.outline_item_bid
            self.position = outline_item.position
        else:
            self.outline_id = ""
            self.position = ""
        self.parent_node = None

    def add_child(self, child: "ShifuOutlineTreeNode") -> None:
        """Add a child to the node."""
        self.children.append(child)
        child.parent_node = self

    def remove_child(self, child: "ShifuOutlineTreeNode") -> None:
        """Remove a child from the node."""
        child.parent_node = None
        self.children.remove(child)

    def get_new_position(self) -> str:
        """Get the new position of the node."""
        if not self.parent_node:
            return self.position
        return (
            self.parent_node.get_new_position()
            + f"{self.parent_node.children.index(self) + 1:02d}"
        )


@register_schema_to_swagger
class OutlineDto(BaseModel):
    """Outline dto."""

    bid: str = Field(..., description="outline id")
    position: str = Field(..., description="outline no")
    name: str = Field(..., description="outline name")
    description: str = Field(..., description="outline desc")
    type: str = Field(..., description="outline type (trial,normal)")
    index: int = Field(..., description="outline index")
    system_prompt: str = Field(..., description="outline system prompt")
    is_hidden: bool = Field(..., description="outline is hidden")

    def __init__(
        self,
        bid: str | None = None,
        position: str | None = None,
        name: str | None = None,
        description: str | None = None,
        type: str | None = None,  # noqa: A002 - serialized DTO field name
        index: int | None = None,
        system_prompt: str | None = None,
        is_hidden: bool | None = None,
    ) -> None:
        """Build the outline payload."""
        super().__init__(
            bid=bid,
            position=position,
            name=name,
            description=description,
            type=type,
            index=index,
            system_prompt=system_prompt,
            is_hidden=is_hidden,
        )

    def __json__(self) -> dict:
        """Return the outline as JSON-compatible data."""
        return {
            "bid": self.bid,
            "position": self.position,
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "index": self.index,
            "system_prompt": self.system_prompt,
            "is_hidden": self.is_hidden,
        }


@register_schema_to_swagger
class ReorderOutlineItemDto:
    """Reorder outline item dto."""

    bid: str
    children: list["ReorderOutlineItemDto"]

    def __init__(self, bid: str, children: list["ReorderOutlineItemDto"]) -> None:
        """Init reorder outline item dto."""
        self.bid = bid
        self.children = children

    def __json__(self) -> dict:
        """Return the reorder outline item as JSON-compatible data."""
        return {
            "bid": self.bid,
            "children": self.children,
        }


@register_schema_to_swagger
class ReorderOutlineDto:
    """Reorder outline dto."""

    outlines: list[ReorderOutlineItemDto]


@register_schema_to_swagger
class MdflowDTOParseResult(BaseModel):
    """Represent the MarkdownFlow DTO parse result API payload."""

    variables: list[str] = Field(..., description="variables")
    blocks_count: int = Field(..., description="blocks count")

    def __init__(self, variables: list[str], blocks_count: int) -> None:
        """Capture parsed MarkdownFlow variables and block count."""
        super().__init__(variables=variables, blocks_count=blocks_count)

    def __json__(self) -> dict:
        """Return parsed MarkdownFlow metadata as JSON-compatible data."""
        return {
            "variables": self.variables,
            "blocks_count": self.blocks_count,
        }

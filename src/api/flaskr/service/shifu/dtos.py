"""
Shifu dtos

This module contains dtos for shifu.

Author: yfge
Date: 2025-08-07
"""

from flaskr.common.swagger import register_schema_to_swagger
from flaskr.service.shifu.models import (
    DraftOutlineItem,
)
from typing import Any
from pydantic import BaseModel, Field


@register_schema_to_swagger
class ShifuDto(BaseModel):
    """
    Shifu dto
    """

    bid: str = Field(..., description="shifu id", required=False)
    name: str = Field(..., description="shifu name", required=False)
    description: str = Field(..., description="shifu description", required=False)
    avatar: str = Field(..., description="shifu avatar", required=False)
    state: int = Field(..., description="shifu state", required=False)
    is_favorite: bool = Field(..., description="is favorite", required=False)
    archived: bool = Field(..., description="is archived", required=False)

    def __init__(
        self,
        shifu_id: str,
        shifu_name: str,
        shifu_description: str,
        shifu_avatar: str,
        shifu_state: int,
        is_favorite: bool,
        archived: bool,
        **kwargs,
    ):
        super().__init__(
            bid=shifu_id,
            name=shifu_name,
            description=shifu_description,
            avatar=shifu_avatar,
            state=shifu_state,
            is_favorite=is_favorite,
            archived=archived,
        )

    def __json__(self):
        return {
            "bid": self.bid,
            "name": self.name,
            "description": self.description,
            "avatar": self.avatar,
            "is_favorite": self.is_favorite,
            "archived": self.archived,
        }


@register_schema_to_swagger
class ShifuDetailDto(BaseModel):
    """
    Shifu detail dto
    """

    bid: str = Field(..., description="shifu id", required=False)
    name: str = Field(..., description="shifu name", required=False)
    description: str = Field(..., description="shifu description", required=False)
    avatar: str = Field(..., description="shifu avatar", required=False)
    keywords: list[str] = Field(..., description="shifu keywords", required=False)
    model: str = Field(..., description="shifu model", required=False)
    temperature: float = Field(..., description="shifu temperature", required=False)
    price: float = Field(..., description="shifu price", required=False)
    preview_url: str = Field(..., description="shifu preview url", required=False)
    url: str = Field(..., description="shifu url", required=False)
    system_prompt: str = Field(..., description="shifu system prompt", required=False)
    readonly: bool = Field(..., description="is shifu readonly", required=False)
    archived: bool = Field(..., description="is shifu archived", required=False)
    can_manage_archive: bool = Field(
        False, description="whether current user can archive/unarchive", required=False
    )
    can_publish: bool = Field(
        False, description="whether current user can publish", required=False
    )
    created_user_bid: str = Field(
        "", description="owner user business id", required=False
    )
    # TTS Configuration
    tts_enabled: bool = Field(False, description="TTS enabled", required=False)
    tts_provider: str = Field(
        "",
        description="TTS provider: minimax, volcengine, volcengine_http, baidu, aliyun",
        required=False,
    )
    tts_model: str = Field("", description="TTS model/resource ID", required=False)
    tts_voice_id: str = Field("", description="TTS voice ID", required=False)
    tts_speed: float = Field(
        1.0, description="TTS speech speed (provider-specific range)", required=False
    )
    tts_pitch: int = Field(
        0,
        description="TTS pitch adjustment (provider-specific range)",
        required=False,
    )
    tts_emotion: str = Field("", description="TTS emotion setting", required=False)
    use_learner_language: bool = Field(
        False,
        description="Use learner language for AI output",
        required=False,
    )
    ask_enabled_status: int = Field(
        5101,
        description="Ask mode status: 5101=default, 5102=disabled, 5103=enabled",
        required=False,
    )
    ask_model: str = Field(
        "",
        description="Ask model (maps to ask_llm)",
        required=False,
    )
    ask_temperature: float = Field(
        0.0,
        description="Ask model temperature",
        required=False,
    )
    ask_system_prompt: str = Field(
        "",
        description="Ask model system prompt",
        required=False,
    )
    ask_provider_config: dict[str, Any] = Field(
        default_factory=dict,
        description='Ask provider config, e.g. {"provider":"llm","mode":"provider_then_llm","config":{}}',
        required=False,
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
        use_learner_language: bool = False,
        ask_enabled_status: int = 5101,
        ask_model: str = "",
        ask_temperature: float = 0.0,
        ask_system_prompt: str = "",
        ask_provider_config: dict[str, Any] | None = None,
    ):
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
            use_learner_language=use_learner_language,
            ask_enabled_status=ask_enabled_status,
            ask_model=ask_model,
            ask_temperature=ask_temperature,
            ask_system_prompt=ask_system_prompt,
            ask_provider_config=ask_provider_config or {},
        )

    def __json__(self):
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
            "use_learner_language": self.use_learner_language,
            "ask_enabled_status": self.ask_enabled_status,
            "ask_model": self.ask_model,
            "ask_temperature": self.ask_temperature,
            "ask_system_prompt": self.ask_system_prompt,
            "ask_provider_config": self.ask_provider_config,
        }


@register_schema_to_swagger
class SimpleOutlineDto(BaseModel):
    """
    Simple outline dto
    """

    bid: str = Field(..., description="outline id", required=False)
    position: str = Field(..., description="outline position", required=False)
    name: str = Field(..., description="outline name", required=False)
    children: list["SimpleOutlineDto"] = Field(
        ..., description="outline children", required=False
    )
    type: str | None = Field(
        None, description="outline type (trial,normal,guest)", required=False
    )
    is_hidden: bool | None = Field(
        None, description="outline hidden flag", required=False
    )

    def __init__(
        self,
        bid: str,
        position: str,
        name: str,
        children: list,
        type: str | None = None,
        is_hidden: bool | None = None,
    ):
        normalized_children: list["SimpleOutlineDto"] = []
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

    def __json__(self):
        return {
            "bid": self.bid,
            "position": self.position,
            "name": self.name,
            "children": self.children,
            "type": self.type,
            "is_hidden": self.is_hidden,
        }


# new outline tree node class, for handling DraftOutlineItem
# author: yfge
# date: 2025-07-13
# version: 1.0.0
# description: this class is used to handle DraftOutlineItem
# usage:
# 1. create a new ShifuOutlineTreeNode
# 2. add a child to the node
# 3. remove a child from the node
class ShifuOutlineTreeNode:
    """
    Shifu outline tree node
    """

    def __init__(self, outline_item: DraftOutlineItem):
        self.outline = outline_item
        self.children = []
        if outline_item:
            self.outline_id = outline_item.outline_item_bid
            self.position = outline_item.position
        else:
            self.outline_id = ""
            self.position = ""
        self.parent_node = None

    def add_child(self, child: "ShifuOutlineTreeNode"):
        """
        add a child to the node
        """
        self.children.append(child)
        child.parent_node = self

    def remove_child(self, child: "ShifuOutlineTreeNode"):
        """
        remove a child from the node
        """
        child.parent_node = None
        self.children.remove(child)

    def get_new_position(self):
        """
        get the new position of the node
        """
        if not self.parent_node:
            return self.position
        else:
            return (
                self.parent_node.get_new_position()
                + f"{self.parent_node.children.index(self) + 1:02d}"
            )


@register_schema_to_swagger
class OutlineDto(BaseModel):
    """
    Outline dto
    """

    bid: str = Field(..., description="outline id", required=False)
    position: str = Field(..., description="outline no", required=False)
    name: str = Field(..., description="outline name", required=False)
    description: str = Field(..., description="outline desc", required=False)
    type: str = Field(..., description="outline type (trial,normal)", required=False)
    index: int = Field(..., description="outline index", required=False)
    system_prompt: str = Field(..., description="outline system prompt", required=False)
    is_hidden: bool = Field(..., description="outline is hidden", required=False)

    def __init__(
        self,
        bid: str = None,
        position: str = None,
        name: str = None,
        description: str = None,
        type: str = None,
        index: int = None,
        system_prompt: str = None,
        is_hidden: bool = None,
    ):
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

    def __json__(self):
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
    """
    Reorder outline item dto
    """

    bid: str
    children: list["ReorderOutlineItemDto"]

    def __init__(self, bid: str, children: list["ReorderOutlineItemDto"]):
        """
        init reorder outline item dto
        """
        self.bid = bid
        self.children = children

    def __json__(self):
        return {
            "bid": self.bid,
            "children": self.children,
        }


@register_schema_to_swagger
class ReorderOutlineDto:
    """
    Reorder outline dto
    """

    outlines: list[ReorderOutlineItemDto]


@register_schema_to_swagger
class MdflowDTOParseResult(BaseModel):
    variables: list[str] = Field(..., description="variables", required=True)
    blocks_count: int = Field(..., description="blocks count", required=True)

    def __init__(self, variables: list[str], blocks_count: int):
        super().__init__(variables=variables, blocks_count=blocks_count)

    def __json__(self):
        return {
            "variables": self.variables,
            "blocks_count": self.blocks_count,
        }

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
from flaskr.service.profile.dtos import (
    TextProfileDto,
    SelectProfileDto,
)
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

    def __init__(
        self,
        shifu_id: str,
        shifu_name: str,
        shifu_description: str,
        shifu_avatar: str,
        shifu_state: int,
        is_favorite: bool,
        **kwargs,
    ):
        super().__init__(
            bid=shifu_id,
            name=shifu_name,
            description=shifu_description,
            avatar=shifu_avatar,
            state=shifu_state,
            is_favorite=is_favorite,
        )

    def __json__(self):
        return {
            "bid": self.bid,
            "name": self.name,
            "description": self.description,
            "avatar": self.avatar,
            "is_favorite": self.is_favorite,
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

    def __init__(
        self,
        bid: str,
        position: str,
        name: str,
        children: list,
    ):
        super().__init__(
            bid=bid,
            position=position,
            name=name,
            children=(
                [
                    SimpleOutlineDto(
                        child.bid, child.position, child.name, child.children
                    )
                    for child in children
                ]
                if children
                else []
            ),
        )

    def __json__(self):
        return {
            "bid": self.bid,
            "position": self.position,
            "name": self.name,
            "children": self.children,
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
class OutlineEditDto:
    """
    Outline edit dto
    """

    outline_id: str
    outline_no: str
    outline_name: str
    outline_desc: str
    outline_type: int
    outline_level: int

    def __init__(
        self,
        outline_id: str = None,
        outline_no: str = None,
        outline_name: str = None,
        outline_desc: str = None,
        outline_type: int = None,
    ):
        """
        init outline edit dto
        """
        self.outline_id = outline_id
        self.outline_no = outline_no
        self.outline_name = outline_name
        self.outline_desc = outline_desc
        self.outline_type = outline_type
        self.outline_level = len(outline_no) // 2

    def __json__(self):
        return {
            "properties": {
                "outline_id": self.outline_id,
                "outline_no": self.outline_no,
                "outline_name": self.outline_name,
                "outline_desc": self.outline_desc,
                "outline_type": self.outline_type,
                "outline_level": self.outline_level,
            },
            "type": "outline",
        }


@register_schema_to_swagger
class BlockUpdateResultDto:
    """
    Block update result dto
    """

    data: TextProfileDto | SelectProfileDto | None
    error_message: str | None

    def __init__(
        self,
        data: TextProfileDto | SelectProfileDto | None,
        error_message: str | None = None,
    ):
        """
        init block update result dto
        """
        self.data = data
        self.error_message = error_message

    def __json__(self):
        return {
            "data": self.data,
            "error_message": self.error_message,
        }

    def __str__(self):
        return str(self.__json__())


@register_schema_to_swagger
class SaveBlockListResultDto:
    """
    Save block list result dto
    """

    blocks: list["BlockDTO"]
    error_messages: dict[str, str]

    def __init__(
        self,
        blocks: list["BlockDTO"],
        error_messages: dict[str, str],
    ):
        """
        init save block list result dto
        """
        self.blocks = blocks
        self.error_messages = error_messages

    def __json__(self):
        return {
            "blocks": self.blocks,
            "error_messages": self.error_messages,
        }

    def __str__(self):
        return str(self.__json__())


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


# new dto for block


# i18n label dto
@register_schema_to_swagger
class LabelDTO(BaseModel):
    """
    Label dto
    """

    lang: dict[str, str] = Field(
        default_factory=dict, description="label lang", required=True
    )

    def __init__(self, lang: dict[str, str], **kwargs):
        """
        init label dto
        """
        super().__init__(lang=lang)

    def __json__(self):
        """
        json label dto
        """
        return {
            "lang": self.lang,
        }


@register_schema_to_swagger
class ContentDTO(BaseModel):
    """
    Content dto
    """

    content: str = Field(..., description="content", required=True, allow_none=True)
    llm_enabled: bool = Field(..., description="llm enabled", required=True)
    llm: str = Field(..., description="llm", required=False)
    llm_temperature: float = Field(..., description="llm temperature", required=False)

    def __init__(
        self,
        content: str,
        llm_enabled: bool,
        llm: str = None,
        llm_temperature: float = None,
        **kwargs,
    ):
        """
        init content dto
        """
        super().__init__(
            content=content if content is not None else "",
            llm_enabled=llm_enabled,
            llm=llm if llm is not None else "",
            llm_temperature=llm_temperature,
        )

    def __json__(self):
        return {
            "content": self.content,
            "llm_enabled": self.llm_enabled,
            "llm": self.llm,
            "llm_temperature": self.llm_temperature,
        }


@register_schema_to_swagger
class BreakDTO(BaseModel):
    """
    Break dto
    """

    def __init__(self, **kwargs):
        """
        init break dto
        """
        super().__init__()

    def __json__(self):
        return {}


@register_schema_to_swagger
class ButtonDTO(BaseModel):
    """
    Button dto
    """

    label: LabelDTO = Field(..., description="label", required=True)

    def __init__(self, label: dict[str, str], **kwargs):
        """
        init button dto
        """
        super().__init__(label=LabelDTO(lang=label.get("lang", label)))

    def __json__(self):
        return {
            "label": self.label.__json__(),
        }


@register_schema_to_swagger
class InputDTO(BaseModel):
    """
    Input dto
    """

    placeholder: LabelDTO = Field(..., description="placeholder", required=True)
    prompt: str = Field(..., description="prompt", required=True)
    result_variable_bids: list[str] = Field(
        ..., description="result variable bids", required=True
    )
    llm: str = Field(..., description="llm", required=False)
    llm_temperature: float = Field(..., description="llm temperature", required=False)

    def __init__(
        self,
        placeholder: dict[str, str],
        prompt: str,
        result_variable_bids: list[str],
        llm: str = None,
        llm_temperature: float = None,
        **kwargs,
    ):
        """
        init input dto
        """
        super().__init__(
            placeholder=LabelDTO(lang=placeholder.get("lang", placeholder)),
            prompt=prompt,
            result_variable_bids=result_variable_bids,
            llm=llm,
            llm_temperature=llm_temperature,
        )

    def __json__(self):
        return {
            "placeholder": self.placeholder.__json__(),
            "prompt": self.prompt,
            "result_variable_bids": self.result_variable_bids,
            "llm": self.llm,
            "llm_temperature": self.llm_temperature,
        }


@register_schema_to_swagger
class OptionItemDTO(BaseModel):
    """
    Option item dto
    """

    label: LabelDTO = Field(..., description="label", type=LabelDTO, required=True)
    value: str = Field(..., description="value", required=True)

    def __init__(self, label: dict[str, str], value: str, **kwargs):
        """
        init option item dto
        """
        super().__init__(label=LabelDTO(lang=label.get("lang", label)), value=value)

    def __json__(self):
        return {
            "label": self.label.__json__(),
            "value": self.value,
        }


@register_schema_to_swagger
class OptionsDTO(BaseModel):
    """
    Options dto
    """

    result_variable_bid: str = Field(
        ..., description="result variable bid", required=True
    )
    options: list[OptionItemDTO] = Field(..., description="options", required=True)

    def __init__(self, result_variable_bid: str, options: list[dict], **kwargs):
        """
        init options dto
        """
        super().__init__(
            result_variable_bid=result_variable_bid,
            options=[OptionItemDTO(**option) for option in options],
        )

    def __json__(self):
        return {
            "result_variable_bid": self.result_variable_bid,
            "options": [option.__json__() for option in self.options],
        }


@register_schema_to_swagger
class GotoConditionDTO(BaseModel):
    """
    Goto condition dto
    """

    value: str = Field(..., description="value", required=True)
    destination_type: str = Field(..., description="destination type", required=True)
    destination_bid: str = Field(..., description="destination bid", required=True)

    def __init__(self, value: str, destination_type: str, destination_bid: str):
        """
        init goto condition dto
        """
        super().__init__(
            value=value,
            destination_type=destination_type,
            destination_bid=destination_bid,
        )

    def __json__(self):
        return {
            "value": self.value,
            "destination_type": self.destination_type,
            "destination_bid": self.destination_bid,
        }


@register_schema_to_swagger
class GotoDTO(BaseModel):
    """
    Goto dto
    """

    conditions: list[GotoConditionDTO] = Field(
        ..., description="conditions", required=True
    )

    def __init__(self, conditions: list[dict], **kwargs):
        """
        init goto dto
        """
        super().__init__(
            conditions=[GotoConditionDTO(**condition) for condition in conditions]
        )

    def __json__(self):
        return {
            "conditions": [condition.__json__() for condition in self.conditions],
        }


@register_schema_to_swagger
class PaymentDTO(BaseModel):
    """
    Payment dto
    """

    label: LabelDTO | None = Field(
        default=None, description="label", type=LabelDTO, required=False
    )

    def __init__(self, label: dict[str, str] = None, **kwargs):
        if label:
            super().__init__(label=LabelDTO(lang=label.get("lang", label)))
        else:
            super().__init__(label=None)

    def __json__(self):
        return {
            "label": self.label.__json__() if self.label else None,
        }


@register_schema_to_swagger
class LoginDTO(BaseModel):
    """
    Login dto
    """

    label: LabelDTO = Field(..., description="label", type=LabelDTO, required=True)

    def __init__(self, label: dict[str, str], **kwargs):
        """
        init login dto
        """
        super().__init__(label=LabelDTO(lang=label.get("lang", label)))

    def __json__(self):
        return {
            "label": self.label.__json__(),
        }


@register_schema_to_swagger
class CheckCodeDTO(BaseModel):
    """
    Check code dto
    """

    placeholder: LabelDTO = Field(
        ..., description="placeholder", type=LabelDTO, required=True
    )

    def __init__(self, placeholder: dict[str, str], **kwargs):
        """
        init check code dto
        """
        super().__init__(
            placeholder=LabelDTO(lang=placeholder.get("lang", placeholder))
        )

    def __json__(self):
        return {
            "placeholder": self.placeholder.__json__(),
        }


@register_schema_to_swagger
class PhoneDTO(BaseModel):
    """
    Phone dto
    """

    placeholder: LabelDTO = Field(
        ..., description="placeholder", type=LabelDTO, required=True
    )

    def __init__(self, placeholder: dict[str, str], **kwargs):
        """
        init phone dto
        """
        super().__init__(
            placeholder=LabelDTO(lang=placeholder.get("lang", placeholder))
        )

    def __json__(self):
        return {
            "placeholder": self.placeholder.__json__(),
        }


@register_schema_to_swagger
class BlockDTO(BaseModel):
    """
    Block dto
    """

    bid: str = Field(..., description="bid", required=True)
    type: str = Field(..., description="type", required=True)
    block_content: (
        ContentDTO
        | BreakDTO
        | ButtonDTO
        | InputDTO
        | OptionsDTO
        | GotoDTO
        | PaymentDTO
        | LoginDTO
        | CheckCodeDTO
        | PhoneDTO
    ) = Field(..., description="block content", required=True)
    variable_bids: list[str] = Field(..., description="variable bids", required=False)
    resource_bids: list[str] = Field(..., description="resource bids", required=False)

    def __init__(
        self,
        bid: str,
        block_content: (
            ContentDTO
            | BreakDTO
            | ButtonDTO
            | InputDTO
            | OptionsDTO
            | GotoDTO
            | PaymentDTO
            | LoginDTO
            | CheckCodeDTO
            | PhoneDTO
        ),
        variable_bids: list[str],
        resource_bids: list[str],
    ):
        """
        init block dto
        """
        super().__init__(
            bid=bid,
            type=block_content.__class__.__name__.replace("DTO", "").lower(),
            block_content=block_content,
            variable_bids=variable_bids,
            resource_bids=resource_bids,
        )

    def __json__(self):
        return {
            "bid": self.bid,
            "type": self.type,
            "properties": self.block_content.__json__(),
            "variable_bids": self.variable_bids,
            "resource_bids": self.resource_bids,
        }

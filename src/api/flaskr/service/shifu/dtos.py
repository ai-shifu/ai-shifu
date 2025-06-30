from flaskr.common.swagger import register_schema_to_swagger
from flaskr.service.common.aidtos import AIDto, SystemPromptDto
from flaskr.service.shifu.utils import OutlineTreeNode
from flaskr.service.profile.dtos import (
    TextProfileDto,
    SelectProfileDto,
)
from flaskr.service.profile.models import ProfileItem
from pydantic import BaseModel, Field


@register_schema_to_swagger
class ShifuDto(BaseModel):
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
        **kwargs
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
class ChapterDto(BaseModel):
    chapter_id: str = Field(..., description="chapter id", required=False)
    chapter_name: str = Field(..., description="chapter name", required=False)
    chapter_description: str = Field(
        ..., description="chapter description", required=False
    )
    chapter_type: int = Field(..., description="chapter type", required=False)

    def __init__(
        self,
        chapter_id: str,
        chapter_name: str,
        chapter_description: str,
        chapter_type: int,
    ):
        super().__init__(
            chapter_id=chapter_id,
            chapter_name=chapter_name,
            chapter_description=chapter_description,
            chapter_type=chapter_type,
        )

    def __json__(self):
        return {
            "chapter_id": self.chapter_id,
            "chapter_name": self.chapter_name,
            "chapter_description": self.chapter_description,
            "chapter_type": self.chapter_type,
        }


@register_schema_to_swagger
class SimpleOutlineDto(BaseModel):
    bid: str = Field(..., description="outline id", required=False)
    position: str = Field(..., description="outline position", required=False)
    name: str = Field(..., description="outline name", required=False)
    children: list["SimpleOutlineDto"] = Field(
        ..., description="outline children", required=False
    )

    def __init__(
        self,
        node: OutlineTreeNode,
    ):
        super().__init__(
            bid=node.outline_id,
            position=node.lesson_no,
            name=node.outline.lesson_name,
            children=(
                [SimpleOutlineDto(child) for child in node.children]
                if node.children
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


@register_schema_to_swagger
class UnitDto:
    unit_id: str
    unit_no: str
    unit_name: str


@register_schema_to_swagger
class OutlineDto(BaseModel):
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
class SolidContentDto:
    prompt: str
    variables: list[str]

    def __init__(self, prompt: str = None, variables: list[str] = None):
        self.prompt = prompt
        self.variables = variables if variables is not None else []

    def __json__(self):
        return {
            "properties": {
                "prompt": self.prompt,
                "variables": self.variables,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class ButtonDto:
    # type button
    button_name: str
    button_key: str

    def __init__(self, button_name: str = None, button_key: str = None):
        self.button_name = button_name
        self.button_key = button_key

    def __json__(self):
        return {
            "properties": {
                "button_name": self.button_name,
                "button_key": self.button_key,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class LoginDto(ButtonDto):
    # type login
    button_name: str
    button_key: str

    def __init__(self, button_name: str = None, button_key: str = None):
        super().__init__(button_name, button_key)
        self.button_name = button_name
        self.button_key = button_key

    def __json__(self):
        return {
            "properties": {
                "button_name": self.button_name,
                "button_key": self.button_key,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class GotoDtoItem:
    value: str
    type: str
    goto_id: str

    def __init__(self, value: str = None, type: str = None, goto_id: str = None):
        self.value = value
        self.type = type
        self.goto_id = goto_id

    def __json__(self):
        return {
            "value": self.value,
            "type": self.type,
            "goto_id": self.goto_id,
        }


@register_schema_to_swagger
class GotoSettings:
    items: list[GotoDtoItem]
    profile_key: str

    def __init__(
        self, items: list[GotoDtoItem] = None, profile_key: str = None, **kwargs
    ):
        if isinstance(items, list):
            self.items = [
                GotoDtoItem(**item) if isinstance(item, dict) else item
                for item in items
            ]
        self.profile_key = profile_key

    def __json__(self):
        return {
            "items": self.items,
            "profile_key": self.profile_key,
        }


@register_schema_to_swagger
class GotoDto(ButtonDto):
    # type goto
    button_name: str
    button_key: str
    goto_settings: GotoSettings

    def __init__(
        self,
        button_name: str = None,
        button_key: str = None,
        goto_settings: GotoSettings = None,
        **kwargs
    ):
        super().__init__(button_name, button_key)
        if isinstance(goto_settings, dict):
            self.goto_settings = GotoSettings(**goto_settings)
        else:
            self.goto_settings = goto_settings
        button_key

    def __json__(self):
        return {
            "properties": {
                "goto_settings": self.goto_settings,
                "button_name": self.button_name,
                "button_key": self.button_key,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class PaymentDto(ButtonDto):
    # type payment
    button_name: str
    button_key: str

    def __init__(self, button_name: str = None, button_key: str = None):
        super().__init__(button_name, button_key)
        self.button_name = button_name
        self.button_key = button_key

    def __json__(self):
        return {
            "properties": {
                "button_name": self.button_name,
                "button_key": self.button_key,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class EmptyDto:
    # type continue & empty

    def __init__(self):
        pass

    def __json__(self):
        return {
            "properties": {},
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class OptionDto:
    # type option
    profile_id: str
    option_name: str
    option_key: str
    profile_key: str
    buttons: list[ButtonDto]

    def __init__(
        self,
        profile_id: str = None,
        option_name: str = None,
        option_key: str = None,
        profile_key: str = None,
        buttons: list = None,
        **kwargs
    ):
        self.option_name = option_name
        self.option_key = option_key
        self.profile_key = profile_key
        self.profile_id = profile_id
        self.buttons = []
        if isinstance(buttons, list):
            self.buttons = [
                (
                    ButtonDto(**button.get("properties"))
                    if isinstance(button, dict)
                    else button
                )
                for button in buttons
            ]

    def __json__(self):
        return {
            "properties": {
                "profile_id": self.profile_id,
                "option_name": self.option_name,
                "option_key": self.option_key,
                "profile_key": self.profile_key,
                "buttons": self.buttons,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class InputDto:
    # type text input
    input_name: str
    input_key: str
    input_placeholder: str

    def __init__(
        self,
        text_input_name: str = None,
        text_input_key: str = None,
        text_input_placeholder: str = None,
    ):
        self.text_input_name = text_input_name
        self.text_input_key = text_input_key
        self.text_input_placeholder = text_input_placeholder

    def __json__(self):
        return {
            "properties": {
                "text_input_name": self.text_input_name,
                "text_input_key": self.text_input_key,
                "text_input_placeholder": self.text_input_placeholder,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class TextInputDto(InputDto):
    # type text input
    profile_ids: list[str]
    prompt: AIDto
    input_name: str
    input_key: str
    input_placeholder: str

    def __init__(
        self,
        profile_ids: list[str] = None,
        input_name: str = None,
        input_key: str = None,
        input_placeholder: str = None,
        prompt: AIDto = None,
        **kwargs
    ):
        super().__init__(input_name, input_key, input_placeholder)
        self.profile_ids = profile_ids or []
        self.prompt = prompt
        self.input_name = input_name
        self.input_key = input_key
        self.input_placeholder = input_placeholder
        if isinstance(prompt, dict):
            self.prompt = AIDto(**prompt.get("properties"))
        elif isinstance(prompt, AIDto):
            self.prompt = prompt

    def __json__(self):
        return {
            "properties": {
                "profile_ids": self.profile_ids,
                "prompt": self.prompt,
                "input_name": self.input_name,
                "input_key": self.input_key,
                "input_placeholder": self.input_placeholder,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class CodeDto(InputDto):
    # type code
    input_name: str
    input_key: str
    input_placeholder: str

    def __init__(
        self,
        input_name: str = None,
        input_key: str = None,
        input_placeholder: str = None,
    ):
        super().__init__(input_name, input_key, input_placeholder)
        self.input_name = input_name
        self.input_key = input_key
        self.input_placeholder = input_placeholder

    def __json__(self):
        return {
            "properties": {
                "input_name": self.input_name,
                "input_key": self.input_key,
                "input_placeholder": self.input_placeholder,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class PhoneDto(InputDto):
    # type phone
    input_name: str
    input_key: str
    input_placeholder: str

    def __init__(
        self,
        input_name: str = None,
        input_key: str = None,
        input_placeholder: str = None,
    ):
        super().__init__(input_name, input_key, input_placeholder)
        self.input_name = input_name
        self.input_key = input_key
        self.input_placeholder = input_placeholder

    def __json__(self):
        return {
            "properties": {
                "input_name": self.input_name,
                "input_key": self.input_key,
                "input_placeholder": self.input_placeholder,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class BlockDto:
    block_id: str
    block_no: str
    block_name: str
    block_desc: str
    block_type: int
    block_index: int
    block_content: AIDto | SolidContentDto
    block_ui: OptionDto | TextInputDto | ButtonDto
    profile_info: "ProfileItem" = None

    def __init__(
        self,
        block_id: str = None,
        block_no: str = None,
        block_name: str = None,
        block_desc: str = None,
        block_type: int = None,
        block_index: int = None,
        block_content: AIDto | SolidContentDto | SystemPromptDto = None,
        block_ui: OptionDto | TextInputDto | ButtonDto = None,
        input_profile_info: "ProfileItem" = None,
        **kwargs
    ):
        self.block_id = block_id
        self.block_no = block_no
        self.block_name = block_name
        self.block_desc = block_desc
        self.block_type = block_type
        self.block_index = block_index
        self.block_content = block_content
        self.block_ui = block_ui
        self.profile_info = input_profile_info

    def __json__(self):
        return {
            "properties": {
                "block_id": self.block_id,
                "block_no": self.block_no,
                "block_name": self.block_name,
                "block_desc": self.block_desc,
                "block_type": self.block_type,
                "block_index": self.block_index,
                "block_content": self.block_content,
                "block_ui": self.block_ui,
                "profile_info": self.profile_info,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class OutlineEditDto:
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
    data: TextProfileDto | SelectProfileDto | None
    error_message: str | None

    def __init__(
        self,
        data: TextProfileDto | SelectProfileDto | None,
        error_message: str | None = None,
    ):
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
    blocks: list[BlockDto]
    error_messages: dict[str, str]

    def __init__(
        self,
        blocks: list[BlockDto],
        error_messages: dict[str, str],
    ):
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
    bid: str
    children: list["ReorderOutlineItemDto"]

    def __init__(self, bid: str, children: list["ReorderOutlineItemDto"]):
        self.bid = bid
        self.children = children

    def __json__(self):
        return {
            "bid": self.bid,
            "children": self.children,
        }


@register_schema_to_swagger
class ReorderOutlineDto:
    outlines: list[ReorderOutlineItemDto]

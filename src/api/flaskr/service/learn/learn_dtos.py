from enum import Enum
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

    def __init__(
        self,
        bid: str,
        title: str,
        description: str,
        keywords: list[str],
        avatar: str,
        price: str,
    ):
        super().__init__(
            bid=bid,
            title=title,
            description=description,
            keywords=keywords,
            avatar=avatar,
            price=price,
        )

    def __json__(self):
        return {
            "bid": self.bid,
            "title": self.title,
            "description": self.description,
            "keywords": self.keywords,
            "avatar": self.avatar,
            "price": self.price,
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
class RunMarkdownFlowDTO(BaseModel):
    outline_bid: str = Field(..., description="outline id", required=False)
    generated_block_bid: str = Field(
        ..., description="generated block id", required=False
    )
    type: GeneratedType = Field(..., description="generated type", required=False)
    content: str | VariableUpdateDTO | OutlineItemUpdateDTO = Field(
        ..., description="generated content", required=True
    )

    def __init__(
        self,
        outline_bid: str,
        generated_block_bid: str,
        type: GeneratedType,
        content: str | VariableUpdateDTO | OutlineItemUpdateDTO,
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

    def __init__(
        self,
        generated_block_bid: str,
        content: str,
        like_status: LikeStatus,
        block_type: BlockType,
        user_input: str,
    ):
        super().__init__(
            generated_block_bid=generated_block_bid,
            content=content,
            like_status=like_status,
            block_type=block_type,
            user_input=user_input,
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
        return ret


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

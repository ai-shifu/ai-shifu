from flask import Flask
from flaskr.service.shifu.models import (
    ShifuLogPublishedStruct,
    ShifuLogDraftStruct,
    ShifuDraftShifu,
    ShifuDraftOutlineItem,
    ShifuPublishedShifu,
    ShifuPublishedOutlineItem,
)

from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.common import raise_error
import queue
from typing import List, Union
from pydantic import BaseModel
from decimal import Decimal
from flaskr.service.shifu.utils import get_shifu_res_url


class ShifuOutlineItemDto(BaseModel):
    bid: str
    position: str
    title: str
    type: int
    shifu_bid: str
    children: List["ShifuOutlineItemDto"]


class ShifuInfoDto(BaseModel):
    bid: str
    title: str
    description: str
    avatar: str
    price: Decimal
    outline_items: List["ShifuOutlineItemDto"]

    def __json__(self):
        return self.model_dump_json(exclude_none=True)


def get_shifu_struct(
    app: Flask, shifu_bid: str, is_preview: bool = False
) -> HistoryItem:
    with app.app_context():
        app.logger.info("get_shifu_struct:{},{}".format(shifu_bid, is_preview))
        if is_preview:
            model = ShifuLogDraftStruct
        else:
            model = ShifuLogPublishedStruct
        shifu_struct = (
            model.query.filter(
                model.shifu_bid == shifu_bid,
            )
            .order_by(
                model.id.desc(),
            )
            .first()
        )
        if not shifu_struct:
            raise_error("SHIFU.SHIFU_NOT_FOUND")
        return HistoryItem.from_json(shifu_struct.struct)


def get_shifu_outline_tree(
    app: Flask, shifu_bid: str, is_preview: bool = False
) -> ShifuInfoDto:
    with app.app_context():
        app.logger.info("get_shifu_outline_tree:{}".format(shifu_bid))
        struct: HistoryItem = get_shifu_struct(app, shifu_bid, is_preview)
        if is_preview:
            shifu_model = ShifuDraftShifu
            outline_item_model = ShifuDraftOutlineItem
        else:
            shifu_model = ShifuPublishedShifu
            outline_item_model = ShifuPublishedOutlineItem

        shifu_ids = []
        outline_item_ids = []
        q = queue.Queue()
        q.put(struct)
        while not q.empty():
            item = q.get()
            if item.type == "shifu":
                shifu_ids.append(item.id)
            elif item.type == "outline":
                outline_item_ids.append(item.id)
            if item.children:
                for child in item.children:
                    q.put(child)
        if len(shifu_ids) != 1:
            raise_error("SHIFU.SHIFU_NOT_FOUND")
        shifu: Union[ShifuDraftShifu, ShifuPublishedShifu] = shifu_model.query.filter(
            shifu_model.id.in_(shifu_ids),
        ).first()
        if not shifu:
            raise_error("SHIFU.SHIFU_NOT_FOUND")
        outline_items = outline_item_model.query.filter(
            outline_item_model.id.in_(outline_item_ids),
        ).all()
        app.logger.info(f"outline_items: len={len(outline_items)}")
        outline_items_map = {i.id: i for i in outline_items}

        shifu_info = ShifuInfoDto(
            bid=shifu.shifu_bid,
            title=shifu.title,
            description=shifu.description,
            avatar=get_shifu_res_url(shifu.avatar_res_bid),
            price=shifu.price,
            outline_items=[],
        )

        def recurse_outline_item(item: HistoryItem) -> ShifuOutlineItemDto:
            if item.type == "outline":
                outline_item: Union[
                    ShifuDraftOutlineItem, ShifuPublishedOutlineItem
                ] = outline_items_map.get(item.id, None)
                if not outline_item:
                    app.logger.error(f"outline_item not found: {item.id}")

                if outline_item and outline_item.hidden == 0:
                    outline_item_dto = ShifuOutlineItemDto(
                        bid=outline_item.outline_item_bid,
                        position=outline_item.position,
                        title=outline_item.title,
                        type=outline_item.type,
                        shifu_bid=shifu.shifu_bid,
                        children=[],
                    )
                    if item.children:
                        for child in item.children:
                            if child.type == "outline":
                                ret = recurse_outline_item(child)
                                if ret:
                                    outline_item_dto.children.append(ret)
                    return outline_item_dto
            return None

        outline_items = [recurse_outline_item(i) for i in struct.children]
        shifu_info.outline_items = [i for i in outline_items if i]
        app.logger.info(f"shifu_info: {shifu_info.__json__()}")
        return shifu_info


def get_shifu_dto(app: Flask, shifu_bid: str, is_preview: bool = False) -> ShifuInfoDto:
    if is_preview:
        shifu_model = ShifuDraftShifu
    else:
        shifu_model = ShifuPublishedShifu
    shifu: Union[ShifuDraftShifu, ShifuPublishedShifu] = (
        shifu_model.query.filter(
            shifu_model.shifu_bid == shifu_bid,
            shifu_model.deleted == 0,
        )
        .order_by(
            shifu_model.id.desc(),
        )
        .first()
    )
    if not shifu:
        raise_error("SHIFU.SHIFU_NOT_FOUND")
    return ShifuInfoDto(
        bid=shifu.shifu_bid,
        title=shifu.title,
        description=shifu.description,
        avatar=get_shifu_res_url(shifu.avatar_res_bid),
        price=shifu.price,
        outline_items=[],
    )


def get_default_shifu_dto(app: Flask, is_preview: bool = False) -> ShifuInfoDto:
    if is_preview:
        shifu_model = ShifuDraftShifu
    else:
        shifu_model = ShifuPublishedShifu
    shifu: Union[ShifuDraftShifu, ShifuPublishedShifu] = (
        shifu_model.query.filter(
            shifu_model.deleted == 0,
        )
        .order_by(
            shifu_model.id.asc(),
        )
        .first()
    )
    if not shifu:
        raise_error("SHIFU.SHIFU_NOT_FOUND")
    return ShifuInfoDto(
        bid=shifu.shifu_bid,
        title=shifu.title,
        description=shifu.description,
        avatar=get_shifu_res_url(shifu.avatar_res_bid),
        price=shifu.price,
        outline_items=[],
    )


def get_outline_item_dto(
    app: Flask, outline_item_bid: str, is_preview: bool = False
) -> ShifuOutlineItemDto:
    if is_preview:
        outline_item_model = ShifuDraftOutlineItem
    else:
        outline_item_model = ShifuPublishedOutlineItem
    outline_item: Union[ShifuDraftOutlineItem, ShifuPublishedOutlineItem] = (
        outline_item_model.query.filter(
            outline_item_model.outline_item_bid == outline_item_bid,
            outline_item_model.deleted == 0,
        )
        .order_by(
            outline_item_model.id.desc(),
        )
        .first()
    )
    if not outline_item:
        raise_error("SHIFU.OUTLINE_ITEM_NOT_FOUND")
    return ShifuOutlineItemDto(
        bid=outline_item.outline_item_bid,
        position=outline_item.position,
        title=outline_item.title,
        type=outline_item.type,
        shifu_bid=outline_item.shifu_bid,
        children=[],
    )
